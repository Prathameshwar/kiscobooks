"""Platform-owned policy over global ISO materializations; no remote write calls."""

from __future__ import annotations

from typing import Any

from billing_platform.db import unfiltered
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.reference.contracts import (
    CatalogData,
    CountryData,
    CurrencyData,
    LanguageData,
    StateData,
)
from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.domain.india_states import gst_state_codes
from identity.models import (
    Company,
    CompanyAddress,
    CompanyCurrencyAllowance,
    Country,
    Currency,
    Language,
    ReferenceChange,
    State,
    Tenant,
)
from identity.schemas.reference_management import ReferenceDetail
from identity.services.audit import record

MODELS: dict[str, Any] = {
    "country": Country,
    "state": State,
    "currency": Currency,
    "language": Language,
}
PROTECTED = {
    "country": ["code", "iso3", "numeric_code"],
    "state": ["code", "country_code", "tax_jurisdiction_code"],
    "currency": [
        "code",
        "numeric_code",
        "minor_unit",
        "symbol",
        "major_unit_name",
        "minor_unit_name",
        "minor_unit_name_plural",
    ],
    "language": ["code", "iso3"],
}
SERVICES = ("catalog", "accounting")


async def sync_ready(db: AsyncSession, row: ReferenceRevision) -> bool:
    if row.change_id is None:
        return True
    cursors = {
        state.service: state.cursor for state in await db.scalars(select(ReferenceSyncState))
    }
    change_id = row.change_id
    return all(
        cursor is not None and cursor >= change_id
        for cursor in (cursors.get(service) for service in SERVICES)
    )


async def detail(db: AsyncSession, row: ReferenceRevision) -> ReferenceDetail:
    return ReferenceDetail(
        **{
            key: getattr(row, key)
            for key in [
                "id",
                "code",
                "name",
                "parent_code",
                "is_active",
                "version",
                "source",
                "updated_at",
            ]
        },
        data=TypeAdapter(CatalogData).validate_python({"kind": row.kind, **row.payload}),
        sync_ready=await sync_ready(db, row),
        protected_fields=PROTECTED[row.kind] if row.version or row.source == "seed" else ["code"],
    )


async def load(db: AsyncSession, kind: str, code: str) -> ReferenceRevision:
    row = await db.scalar(
        select(ReferenceRevision)
        .where(ReferenceRevision.kind == kind, ReferenceRevision.code == code)
        .with_for_update()
    )
    if row is None:
        raise NotFoundError("reference record not found")
    model = MODELS[kind]
    await db.scalar(select(model).where(model.code == code).with_for_update())
    return row


async def validate_parent(db: AsyncSession, data: CatalogData) -> None:
    if isinstance(data, CountryData | StateData):
        model: Any
        model, code, field = (
            (Currency, data.default_currency_code, "default_currency_code")
            if isinstance(data, CountryData)
            else (Country, data.country_code, "country_code")
        )
        parent = await db.scalar(select(model).where(model.code == code).with_for_update())
        if parent is None or not parent.is_active:
            raise ValidationFailedError(
                "choose an active parent reference", fields={field: "unknown or inactive selection"}
            )
        revision = await db.scalar(
            select(ReferenceRevision).where(
                ReferenceRevision.kind == model.__tablename__, ReferenceRevision.code == code
            )
        )
        if revision is not None and revision.is_custom and not await sync_ready(db, revision):
            raise ConflictError("the selected reference is still synchronizing; retry shortly")
    if isinstance(data, StateData) and data.tax_jurisdiction_code is not None:
        if data.tax_jurisdiction_code == "00":
            raise ValidationFailedError(
                "invalid GST jurisdiction",
                fields={"tax_jurisdiction_code": "enter an assigned GST state code"},
            )
        duplicate = await db.scalar(
            select(State.code)
            .where(
                State.country_code == "IN",
                State.tax_jurisdiction_code == data.tax_jurisdiction_code,
                State.code != data.code,
            )
            .limit(1)
        )
        if duplicate is not None:
            raise ConflictError("this GST jurisdiction code is already assigned")
    if isinstance(data, CountryData | LanguageData):
        model = MODELS[data.kind]
        iso3 = data.iso3
        if await db.scalar(
            select(model.code).where(model.iso3 == iso3, model.code != data.code).limit(1)
        ):
            raise ConflictError("this ISO alpha-3 code is already assigned")
    if isinstance(data, CountryData | CurrencyData):
        model = MODELS[data.kind]
        if await db.scalar(
            select(model.code)
            .where(model.numeric_code == data.numeric_code, model.code != data.code)
            .limit(1)
        ):
            raise ConflictError("this ISO numeric code is already assigned")


async def persist(
    db: AsyncSession,
    actor: Actor,
    data: CatalogData,
    *,
    current: ReferenceRevision | None = None,
    reason: str | None = None,
    action: str = "created",
) -> ReferenceRevision:
    if isinstance(data, StateData) and data.country_code == "IN":
        expected = gst_state_codes().get(data.code)
        if expected is None:
            raise ValidationFailedError(
                "choose an official Indian state or union territory",
                fields={"code": "use an installed Indian state reference; restore it if archived"},
            )
        if data.tax_jurisdiction_code not in (None, expected):
            raise ValidationFailedError(
                "Indian states must use their official, fixed GST state code",
                fields={"tax_jurisdiction_code": "use the official GST mapping for this state"},
            )
        data = data.model_copy(update={"tax_jurisdiction_code": expected})
    await validate_parent(db, data)
    model = MODELS[data.kind]
    native = await db.get(model, data.code)
    if current is None and native is not None:
        raise ConflictError("a record with this code already exists; codes cannot be reused")
    values = data.model_dump(exclude={"kind"})
    if current is None:
        current = ReferenceRevision(
            id=uuid7(),
            kind=data.kind,
            code=data.code,
            source="operator",
            version=0,
            payload={},
            is_custom=True,
        )
        db.add(current)
        native = model(**values)
        db.add(native)
    else:
        if native is None:
            raise ConflictError("reference materialization requires repair")
        for key in PROTECTED[data.kind]:
            if key != "code" and current.payload.get(key) != values.get(key):
                raise ValidationFailedError(
                    "protected reference fields cannot be changed",
                    fields={key: "this value is permanent after creation"},
                )
        for key, value in values.items():
            setattr(native, key, value)
    change_id = uuid7()
    latest = await db.scalar(
        select(ReferenceChange.id).order_by(ReferenceChange.id.desc()).limit(1)
    )
    if latest is not None and change_id <= latest:
        # The installation lock orders commits even when owner replica clocks differ.
        import uuid

        change_id = uuid.UUID(int=latest.int + 1)
    current.name, current.is_active, current.source = data.name, data.is_active, "operator"
    current.parent_code = values.get("country_code", values.get("default_currency_code"))
    current.version += 1
    current.payload, current.change_id = values, change_id
    current.updated_by, current.updated_at = actor.user_id, utcnow()
    if current.created_by is None:
        current.created_by = actor.user_id
    db.add(
        ReferenceChange(
            id=change_id, kind=data.kind, code=data.code, version=current.version, payload=values
        )
    )
    record(
        db,
        actor,
        action=f"platform.reference_{action}",
        entity="reference_revision",
        entity_id=current.id,
        changes={"kind": data.kind, "code": data.code, "version": current.version},
        reason=reason,
        category="admin",
    )
    # The immutable journal above is the transactional reference-delivery outbox.
    # Consumers checkpoint its UUIDv7 entries locally before acknowledging them.
    await db.flush()
    return current


async def archive_allowed(db: AsyncSession, row: ReferenceRevision) -> None:
    # Existing active defaults must remain editable and usable; disclose no tenant names.
    with unfiltered():
        conditions = {
            "country": Tenant.default_country_code == row.code,
            "state": Tenant.default_state_code == row.code,
            "currency": Tenant.default_currency_code == row.code,
            "language": Tenant.default_locale == row.code,
        }
        if await db.scalar(
            select(Tenant.id).where(conditions[row.kind], Tenant.status == "active").limit(1)
        ):
            raise ConflictError(
                "this reference is used by an active tenant; change its default first"
            )
        if row.kind in {"country", "state", "currency"}:
            condition = {
                "country": Company.country_code == row.code,
                "state": Company.state_code == row.code,
                "currency": or_(
                    Company.base_currency == row.code, Company.reporting_currency == row.code
                ),
            }[row.kind]
            if await db.scalar(
                select(Company.id).where(condition, Company.status == "active").limit(1)
            ):
                raise ConflictError(
                    "this reference is used by an active company and cannot be archived"
                )
        if row.kind in {"country", "state"}:
            address_field = (
                CompanyAddress.country_code if row.kind == "country" else CompanyAddress.state_code
            )
            if await db.scalar(
                select(CompanyAddress.id)
                .join(Company, Company.id == CompanyAddress.company_id)
                .where(
                    address_field == row.code,
                    CompanyAddress.is_active.is_(True),
                    Company.status == "active",
                )
                .limit(1)
            ):
                raise ConflictError("this reference is used by an active company address")
        if row.kind == "currency" and await db.scalar(
            select(CompanyCurrencyAllowance.id)
            .join(Company, Company.id == CompanyCurrencyAllowance.company_id)
            .where(
                CompanyCurrencyAllowance.currency_code == row.code,
                CompanyCurrencyAllowance.is_active.is_(True),
                Company.status == "active",
            )
            .limit(1)
        ):
            raise ConflictError("this currency is allowed for an active company")
    if row.kind == "country" and await db.scalar(
        select(State.code).where(State.country_code == row.code, State.is_active.is_(True)).limit(1)
    ):
        raise ConflictError("archive this country's active states first")
    if row.kind == "currency" and await db.scalar(
        select(Country.code)
        .where(Country.default_currency_code == row.code, Country.is_active.is_(True))
        .limit(1)
    ):
        raise ConflictError("this currency is the default of an active country")

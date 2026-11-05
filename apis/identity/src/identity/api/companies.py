"""Company CRUD, its display config, feature toggles, visibility, and field-set.

Every handler does the two-step authorization CLAUDE.md §5.2 requires: the endpoint
gate (``current.require``) and then the object-level scope check
(``current.require_scope`` against the company's own ``ScopePath``). Holding
``company.read`` somewhere is never enough to read company B — the scope check is what
stops it, and it is a separate call precisely so it cannot be forgotten.

Money-shaping settings are frozen after the first posting by
``company_immutability`` (422, every actor), feature toggles obey the dependency graph
and the lock ratchet in ``company_features`` (409 when a feature is off), and every
mutation stages an audit event on the outbox inside the request's own transaction
(CLAUDE.md invariants 8 and 10).
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.authz import ScopePath, has_permission
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.features import FEATURES, required_closure
from billing_platform.features import get as feature_catalogue_entry
from billing_platform.field_policy import denied_fields
from billing_platform.ids import uuid7
from billing_platform.jurisdiction import profile
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload, jsonable
from identity.api.auth import Actor, actor
from identity.api.common import load_company as _load_company
from identity.api.dependencies import session
from identity.api.field_access import CompanyAccess
from identity.api.listing import cursor_codec, keyset_page
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.domain.company_features import (
    OFFERED_FEATURES,
    FeatureState,
    assert_disable_allowed,
    plan_enable,
)
from identity.domain.company_immutability import IMMUTABLE_AFTER_POSTING, assert_update_allowed
from identity.domain.company_scope import scoped_company_ids
from identity.domain.field_registry import COMPANY_ENTITY_TYPE
from identity.models import (
    COMPANY_STATUSES,
    VISIBILITIES,
    BusinessCategory,
    BusinessRole,
    Company,
    CompanyFeature,
    CompanyLicence,
    CompanyStatutoryId,
    CompanyTaxRegistration,
    Country,
    Currency,
    State,
    StoreFormat,
    User,
)
from identity.schemas.base import PageMeta
from identity.schemas.company import (
    ClassificationChoice,
    CompanyClassifications,
    CompanyCreate,
    CompanyDetail,
    CompanyListItem,
    CompanyPage,
    CompanySetupReadiness,
    CompanyUpdate,
    DisplayConfig,
    FeatureActionRequest,
    FeatureCatalogue,
    FeatureCatalogueItem,
    FeatureList,
    FeatureView,
    FieldSet,
    SetupFeature,
)
from identity.services.authz_cache import schedule_invalidation
from identity.services.catalog_enrollment import enroll_created_company
from identity.services.company_owner import grant_company_creator
from identity.services.session_context import may_work_in

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")

#: Which read permission guards each entity's ``field-set``. Only company is
#: registered today; an unregistered entity is a 404, not a blank form.
_FIELD_SET_READ_PERMISSION = {COMPANY_ENTITY_TYPE: "company.read"}

_LIST_SORTS = frozenset({"updated_at", "display_name", "code"})


async def _assert_references_exist(
    db: AsyncSession,
    *,
    country_code: str,
    state_code: str,
    base_currency: str,
    reporting_currency: str | None,
    default_tax_system: str,
    current: Company | None = None,
) -> None:
    """Validate selections on both create and update; retain historical inactive codes."""
    from identity.services.reference_availability import lock_configuration, require_delivered

    await lock_configuration(db)

    selections: list[tuple[str, str | None, type[Currency] | type[Country] | type[State]]] = [
        ("currency", base_currency, Currency),
        ("currency", reporting_currency, Currency),
        ("country", country_code, Country),
        ("state", state_code, State),
    ]
    for kind, code, reference_model in selections:
        if code is not None:
            await db.scalar(
                select(reference_model).where(reference_model.code == code).with_for_update()
            )
            if current is None or code not in {
                current.country_code,
                current.state_code,
                current.base_currency,
                current.reporting_currency,
            }:
                await require_delivered(db, kind, code)
    country = await db.get(Country, country_code)
    retained_country = current is not None and current.country_code == country_code
    if country is None or (not country.is_active and not retained_country):
        raise ValidationFailedError(
            "invalid country", fields={"country_code": "unknown or inactive country"}
        )
    state = await db.scalar(
        select(State).where(State.country_code == country_code, State.code == state_code)
    )
    retained_state = retained_country and current is not None and current.state_code == state_code
    if state is None or (not state.is_active and not retained_state):
        raise ValidationFailedError(
            "invalid state", fields={"state_code": "not an active subdivision of this country"}
        )
    for name, code in (
        ("base_currency", base_currency),
        ("reporting_currency", reporting_currency),
    ):
        if code is None:
            continue
        currency = await db.get(Currency, code)
        retained = current is not None and getattr(current, name) == code
        if currency is None or (not currency.is_active and not retained):
            raise ValidationFailedError(
                "invalid currency", fields={name: "unknown or inactive currency"}
            )
    # Code-backed jurisdiction support is narrower than the ISO country catalogue.
    jurisdiction = profile(country_code)
    if default_tax_system not in jurisdiction.tax_systems_by_key():
        raise ValidationFailedError(
            "invalid tax system", fields={"default_tax_system": "not offered in this country"}
        )
    if current is not None and not retained_country:
        # The company lock serializes this check with statutory writes. Existing
        # jurisdiction-specific rows must never be reinterpreted by changing country.
        for model in (CompanyLicence, CompanyTaxRegistration, CompanyStatutoryId):
            if await db.scalar(select(model.id).where(model.company_id == current.id).limit(1)):
                raise ValidationFailedError(
                    "country cannot change while statutory records exist",
                    fields={"country_code": "already used by company statutory records"},
                )


async def _validate_classifications(
    db: AsyncSession,
    incoming: dict[str, Any],
    *,
    current: Company | None = None,
) -> None:
    for field, model in (
        ("business_category_code", BusinessCategory),
        ("store_format_code", StoreFormat),
    ):
        code = incoming.get(field)
        if code is None or (current is not None and code == getattr(current, field)):
            continue
        row = await db.get(model, code)
        if row is None or not row.is_active:
            raise ValidationFailedError(
                "invalid business classification",
                fields={field: "unknown or inactive code"},
            )
    codes = set(incoming.get("business_roles", []))
    if current is not None:
        codes -= set(current.business_roles)
    if codes:
        found = set(
            await db.scalars(
                select(BusinessRole.code).where(
                    BusinessRole.code.in_(codes),
                    BusinessRole.is_active.is_(True),
                )
            )
        )
        if codes != found:
            raise ValidationFailedError(
                "invalid business roles",
                fields={"business_roles": "unknown or inactive code"},
            )


@router.get("/company-features", response_model=FeatureCatalogue)
async def list_feature_catalogue(current: Actor = Depends(actor)) -> FeatureCatalogue:
    """What a company may be given — the code catalogue, not any company's state.

    A company's own flags are ``GET /companies/{id}/features``. This is the catalogue
    itself: no tenant data, no company, no database, so no object scope applies and the
    same answer serves every caller in the installation.
    """
    # Same company-setup gate as the classifications: a reader who may create or read a
    # company may see what a company could do.
    if not current.permissions & {"company.create", "company.read", "company.update"}:
        current.require("company.read")
    items = []
    for offer in OFFERED_FEATURES:
        entry = feature_catalogue_entry(offer.key)
        items.append(
            FeatureCatalogueItem(
                key=offer.key,
                label=offer.label,
                description=offer.description,
                requires=list(entry.requires),
                tax_systems=sorted(entry.tax_systems),
                locks=entry.locks_on is not None,
            )
        )
    return FeatureCatalogue(items=items)


@router.get("/company-classifications", response_model=CompanyClassifications)
async def list_company_classifications(
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyClassifications:
    # Global reference data contains no tenant/company facts; no object scope applies.
    if not current.permissions & {"company.create", "company.read", "company.update"}:
        current.require("company.read")
    choices = {}
    for key, model in (
        ("business_categories", BusinessCategory),
        ("business_roles", BusinessRole),
        ("store_formats", StoreFormat),
    ):
        rows = await db.scalars(
            select(model)
            .where(model.is_active.is_(True))
            .order_by(
                model.sort_order,
                model.code,
            )
        )
        choices[key] = [ClassificationChoice.model_validate(row) for row in rows]
    return CompanyClassifications(**choices)


@router.post("/companies", response_model=CompanyDetail, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    current.require("company.create")
    # Creating a company is a tenant-level act: the grant must reach the whole tenant.
    current.require_scope("company.create", target=ScopePath())
    from identity.services.company_setup import enroll, identity, replay

    command_key, request_hash = identity(current, body, idempotency_key)
    previous = await replay(db, current, command_key, request_hash)
    if previous is not None:
        return (await CompanyAccess.load(db, current)).response(
            previous, CompanyDetail, status_code=201
        )
    await _assert_references_exist(
        db,
        country_code=body.country_code,
        state_code=body.state_code,
        base_currency=body.base_currency,
        reporting_currency=body.reporting_currency,
        default_tax_system=body.default_tax_system,
    )
    if body.parent_company_id is not None and await db.get(Company, body.parent_company_id) is None:
        raise ValidationFailedError(
            "unknown parent company", fields={"parent_company_id": "not found in this tenant"}
        )
    # A duplicate `code` is said out loud, with the field on it.
    #
    # `uq_company_tenant_id_code` still backstops the race, but it arrives as the generic
    # IntegrityError envelope — the constraint name is an internal identifier and cannot be
    # returned (CLAUDE.md §5.8). Two different 409s from this one route then read the same:
    # a taken code, which a caller can resolve by choosing another, and an unseeded role
    # catalogue, which it cannot. Clients now generate the code rather than ask for one
    # (docs/company.md §4.1), so telling the two apart is what decides whether a retry is
    # worth making. Tenant filtering is session-level, so this reads only this tenant's rows.
    if await db.scalar(select(Company.id).where(Company.code == body.code).limit(1)) is not None:
        raise ConflictError(
            "a company with this code already exists.", fields={"code": "already in use"}
        )
    await _validate_classifications(db, body.model_dump())
    now = utcnow()
    row = Company(
        id=uuid7(),
        tenant_id=current.tenant_id,
        status="active",
        first_posted_at=None,
        custom_fields=None,
        visibility_changed_at=None,
        visibility_changed_by=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
        **body.model_dump(exclude={"custom_fields", "setup", "initial_tax_registration"}),
    )
    access = await CompanyAccess.load(db, current)
    access.assert_write(
        row, body.model_dump(exclude={"setup", "initial_tax_registration"}), creating=True
    )
    from billing_platform.field_policy import denied_fields

    from identity.services.customization import prepare_values

    readable = set(access.custom_keys) | set(row.__table__.columns.keys())
    hidden = denied_fields(
        {"custom_field:" + key for key in access.custom_keys} | readable,
        rules=access.rules(ScopePath(company_id=row.id), access.values(row)),
        access="read",
        target=ScopePath(company_id=row.id),
    )
    readable -= {key.removeprefix("custom_field:") for key in hidden}
    row.custom_fields = (
        await prepare_values(
            db, row, body.custom_fields, creating=True, readable=frozenset(readable)
        )
        or None
    )
    db.add(row)
    await db.flush()
    if body.initial_tax_registration is not None:
        # Tenant-level company.create authorizes setup on this newly created company
        # only. No caller-supplied company/address/jurisdiction can redirect the write.
        from identity.services.company_tax_registration import create_initial_registration

        await create_initial_registration(db, current, row, body.initial_tax_registration)
    await grant_company_creator(db, current, row.id)
    await enroll_created_company(db, current, row)
    await enroll(db, current, row, body, command_key, request_hash)
    schedule_invalidation(request, current.tenant_id, current.user_id)
    emit(
        db,
        aggregate_type="company",
        aggregate_id=row.id,
        event_type="company.created",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=row.id,
            action="company.created",
            entity_type="company",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    return access.response(row, CompanyDetail, status_code=201)


@router.get("/companies/{company_id}", response_model=CompanyDetail)
async def get_company(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> JSONResponse:
    current.require("company.read")
    row = await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return (await CompanyAccess.load(db, current)).response(row, CompanyDetail)


@router.patch("/companies/{company_id}", response_model=CompanyDetail)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    current.require("company.update")
    row = await _load_company(db, company_id, for_update=True)
    current.require_scope("company.update", target=ScopePath(company_id=company_id))

    incoming = body.model_dump(exclude_unset=True)
    expected = incoming.pop("expected_updated_at", None)
    if expected is not None and expected != row.updated_at:
        raise ConflictError("This company changed since you loaded it. Reload it before saving.")
    if row.status != "active":
        raise ConflictError("Only active companies can be edited.")
    if incoming.keys() & {"fiscal_year_start_month", "fiscal_year_start_day"}:
        from identity.domain.company_calendar import validate_fiscal_anchor

        try:
            validate_fiscal_anchor(
                incoming.get("fiscal_year_start_month", row.fiscal_year_start_month),
                incoming.get("fiscal_year_start_day", row.fiscal_year_start_day),
            )
        except ValueError as exc:
            raise ValidationFailedError(
                str(exc), fields={"fiscal_year_start_day": str(exc)}
            ) from exc
    if "custom_fields" in incoming and incoming["custom_fields"] is None:
        raise ValidationFailedError(
            "custom fields cannot be null; clear individual keys explicitly"
        )
    access = await CompanyAccess.load(db, current)
    access.assert_write(row, incoming)
    await _validate_classifications(db, incoming, current=row)
    from billing_platform.field_policy import denied_fields

    from identity.services.customization import prepare_values

    readable = set(access.custom_keys) | set(row.__table__.columns.keys())
    hidden = denied_fields(
        {"custom_field:" + key for key in access.custom_keys} | readable,
        rules=access.rules(ScopePath(company_id=row.id), access.values(row)),
        access="read",
        target=ScopePath(company_id=row.id),
    )
    readable -= {key.removeprefix("custom_field:") for key in hidden}
    custom = await prepare_values(
        db,
        row,
        incoming.get("custom_fields", {}),
        creating=False,
        readable=frozenset(readable),
        native_changes={key: value for key, value in incoming.items() if key != "custom_fields"},
    )
    if custom != (row.custom_fields or {}) or "custom_fields" in incoming:
        incoming["custom_fields"] = custom
    current_values = {key: getattr(row, key) for key in incoming}
    # 422 for every actor if a frozen field would actually change (not merely be
    # present unchanged). Enforced on the diff, in domain/, with no actor parameter.
    from identity.services.posting import guard_edit

    await guard_edit(db, row, incoming)
    assert_update_allowed(current_values, incoming, first_posted_at=row.first_posted_at)
    reference_fields = {
        "country_code",
        "state_code",
        "base_currency",
        "reporting_currency",
        "default_tax_system",
    }
    if incoming.keys() & reference_fields:
        await _assert_references_exist(
            db,
            country_code=incoming.get("country_code", row.country_code),
            state_code=incoming.get("state_code", row.state_code),
            base_currency=incoming.get("base_currency", row.base_currency),
            reporting_currency=incoming.get("reporting_currency", row.reporting_currency),
            default_tax_system=incoming.get("default_tax_system", row.default_tax_system),
            current=row,
        )

    changes: dict[str, dict[str, Any]] = {}
    for name, value in incoming.items():
        before = getattr(row, name)
        if before != value:
            changes[name] = {"from": jsonable(before), "to": jsonable(value)}
            setattr(row, name, value)
    if changes:
        row.updated_at = utcnow()
        row.updated_by = current.user_id
        emit(
            db,
            aggregate_type="company",
            aggregate_id=row.id,
            event_type="company.updated",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                company_id=company_id,
                action="company.updated",
                entity_type="company",
                entity_id=row.id,
                actor_user_id=current.user_id,
                category="admin",
                changes=changes,
            ),
        )
        await db.flush()
    return (await CompanyAccess.load(db, current)).response(row, CompanyDetail)


@router.get("/companies", response_model=CompanyPage)
async def list_companies(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    company_status: str | None = Query(None, alias="status", enum=sorted(COMPANY_STATUSES)),
    include_unlisted: bool = False,
    q: str | None = Query(None, min_length=2, max_length=100),
    sort: str = "-updated_at",
    custom_field: str | None = Query(None, max_length=60),
    custom_value: str | None = Query(None, max_length=4096),
) -> CompanyPage | JSONResponse:
    current.require("company.read")
    if company_status is not None and company_status not in COMPANY_STATUSES:
        raise ValidationFailedError("invalid filter", fields={"status": "unknown value"})
    access = await CompanyAccess.load(db, current)
    query_fields = {sort.lstrip("-")}
    if not include_unlisted:
        query_fields.add("visibility")
    if company_status:
        query_fields.add("status")
    if q:
        query_fields.update({"code", "display_name", "legal_name"})
    access.assert_query(query_fields)
    statement = select(Company)
    if custom_field is not None or custom_value is not None:
        if custom_field is None or custom_value is None:
            raise ValidationFailedError("custom_field and custom_value must be provided together")
        access.assert_query({"custom_field:" + custom_field})
        from identity.services.custom_query import company_custom_filter

        statement = statement.where(await company_custom_filter(db, custom_field, custom_value))

    # Object-scope on a list (CLAUDE.md §5.2): a tenant-wide reader sees every company;
    # a company-scoped reader sees only the companies their grants name. Without this a
    # company-A clerk could enumerate company B's existence and metadata.
    allowed = scoped_company_ids(current.grants, "company.read", on_date=utcnow().date())
    if allowed is not None:
        if not allowed:
            return CompanyPage(items=[], page=PageMeta(next_cursor=None, has_more=False))
        statement = statement.where(Company.id.in_(allowed))

    if company_status:
        statement = statement.where(Company.status == company_status)
    if not include_unlisted:
        # Unlisted is a display preference: kept out of the switcher-style list by
        # default, still reachable by id and still in tenant-wide reports (invariant 17).
        statement = statement.where(Company.visibility == "listed")
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            or_(
                Company.code.like(f"{escaped}%", escape="\\"),
                Company.display_name.like(f"{escaped}%", escape="\\"),
                Company.legal_name.like(f"{escaped}%", escape="\\"),
            )
        )

    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=Company,
        projection=CompanyListItem,
        extra_columns=access.condition_columns,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=_LIST_SORTS,
        default="-updated_at",
        codec=cursor_codec(request, "companies", authority_version=access.fingerprint),
    )
    return JSONResponse(
        {
            "items": [access.project(row, CompanyListItem) for row in rows],
            "page": PageMeta(next_cursor=next_cursor, has_more=has_more).model_dump(),
        }
    )


@router.get("/companies/{company_id}/display-config", response_model=DisplayConfig)
async def get_display_config(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    """How this company's amounts and dates are written. Not a company detail.

    Readable by ``company.read`` **or** by anyone who may work in this company
    (``session_context.may_work_in``). A clerk who raises invoices here has to render its
    figures the way the company states them — ``12,34,567.89`` and ``dd-MM-yyyy``, from
    config and never from the browser's locale (CLAUDE.md §4). Refusing them these
    sixteen formatting values would not protect anything: it would make the console fall
    back to a different format for the same company, which is how two people read one
    invoice differently.
    """
    # Authorized before the row is loaded, so a refusal cannot be told apart from a
    # company that does not exist — the order the `company.read` endpoint gate had.
    if not has_permission(
        current.grants,
        "company.read",
        target=ScopePath(company_id=company_id),
        on_date=utcnow().date(),
    ) and not await may_work_in(db, current, company_id):
        raise PermissionDeniedError("this action requires company.read")
    access = await CompanyAccess.load(db, current)
    cache = getattr(request.app.state, "company_display_cache", None)

    async def authoritative() -> dict[str, object]:
        if cache is None:
            row = await _load_company(db, company_id)
            user = await db.get(User, current.user_id)
        else:
            # Read both sources in one statement and refresh existing ORM identities.
            # Authentication may have retained older rows before a concurrent commit;
            # those values must never populate the key for the new source versions.
            sources = (
                await db.execute(
                    select(Company, User)
                    .outerjoin(User, User.id == current.user_id)
                    .where(Company.id == company_id)
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            if sources is None:
                raise NotFoundError("company not found")
            row, user = sources
        from identity.services.display import resolve_display

        values = resolve_display(row, user)
        return access.project(row, DisplayConfig, values=values)

    if cache is None:
        return JSONResponse(await authoritative())

    # A cache hit performs one narrow source-version read. The full company and user
    # rows are loaded only on a miss. ``CompanyAccess`` remains live on every request,
    # so a new deny or changed conditional policy selects a different fingerprint
    # before Redis is consulted.
    user_version = select(User.updated_at).where(User.id == current.user_id).scalar_subquery()
    condition_columns = access.condition_columns
    versions = (
        await db.execute(
            select(
                Company.updated_at,
                user_version.label("user_updated_at"),
                *(getattr(Company, name) for name in sorted(condition_columns - {"updated_at"})),
            ).where(Company.id == company_id)
        )
    ).one_or_none()
    if versions is None:
        raise NotFoundError("company not found")
    target = ScopePath(company_id=company_id)
    forbidden = denied_fields(
        DisplayConfig.model_fields,
        rules=access.rules(target, {name: versions._mapping[name] for name in condition_columns}),
        access="read",
        target=target,
    )
    from identity.services.company_display_cache import display_key

    key = display_key(
        tenant_id=current.tenant_id,
        company_id=company_id,
        user_id=current.user_id,
        company_version=versions.updated_at,
        user_version=versions.user_updated_at,
        access_fingerprint=access.fingerprint,
    )
    values = await cache.resolve(key, authoritative)
    # Redis cannot widen the live projection even if a schema-valid cached value
    # was corrupted to include a field denied for this actor and company.
    return JSONResponse({name: value for name, value in values.items() if name not in forbidden})


@router.get("/entities/{entity_type}/field-set", response_model=FieldSet)
async def get_field_set(
    entity_type: str,
    company_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FieldSet:
    from identity.services.field_metadata import company_field_set

    return await company_field_set(db, current, entity_type, company_id)


async def _feature_rows(db: AsyncSession, company_id: uuid.UUID) -> list[CompanyFeature]:
    statement = select(CompanyFeature).where(CompanyFeature.company_id == company_id)
    return list((await db.scalars(statement)).all())


def _feature_state_map(rows: list[CompanyFeature]) -> dict[str, FeatureState]:
    return {
        r.feature_key: FeatureState(
            is_enabled=r.is_enabled, locked_at=r.locked_at, lock_reason=r.lock_reason
        )
        for r in rows
    }


def _assert_feature_change(company: Company, body: FeatureActionRequest | None) -> None:
    if company.status != "active":
        raise ConflictError("Only active companies can change configuration.")
    if (
        body
        and body.expected_updated_at is not None
        and body.expected_updated_at != company.updated_at
    ):
        raise ConflictError(
            "This company changed since your review. Reload configuration before saving."
        )


@router.get("/companies/{company_id}/features", response_model=FeatureList)
async def list_features(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> FeatureList:
    current.require("company.read")
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    rows = await _feature_rows(db, company_id)
    return FeatureList(
        enabled=sorted(r.feature_key for r in rows if r.is_enabled),
        features=[
            FeatureView(
                feature_key=r.feature_key,
                is_enabled=r.is_enabled,
                locked=r.locked_at is not None,
                locked_at=r.locked_at,
            )
            for r in sorted(rows, key=lambda r: r.feature_key)
        ],
    )


@router.get("/companies/{company_id}/setup-readiness", response_model=CompanySetupReadiness)
async def setup_readiness(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> CompanySetupReadiness:
    """Identity-owned setup facts; downstream execution readiness belongs to its owner."""
    current.require("company.read")
    company = await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    protected = (await CompanyAccess.load(db, current)).project(company, CompanyDetail)
    required = {"status", "updated_at", "first_posted_at", "default_tax_system"}
    if not required <= protected.keys():
        raise PermissionDeniedError("company setup inputs are not readable")
    rows = {row.feature_key: row for row in await _feature_rows(db, company_id)}
    enabled = {key for key, row in rows.items() if row.is_enabled}
    features = []
    for key, definition in sorted(FEATURES.items()):
        row = rows.get(key)
        dependencies = set(required_closure(key)) - {key}
        active = row is not None and row.is_enabled
        tax_system_supported = (
            not definition.tax_systems or company.default_tax_system in definition.tax_systems
        )
        consistent = dependencies <= enabled and tax_system_supported
        inconsistent = (active and not consistent) or (
            row is not None and row.locked_at is not None and not active
        )
        features.append(
            SetupFeature(
                feature_key=key,
                state="INCONSISTENT" if inconsistent else "ENABLED" if active else "DISABLED",
                required_features=sorted(dependencies),
                missing_prerequisites=sorted(dependencies - enabled),
                tax_system_supported=tax_system_supported,
                locked_at=row.locked_at if row else None,
                lock_reason=row.lock_reason if row else None,
                source_updated_at=row.updated_at if row else None,
            )
        )
    return CompanySetupReadiness(
        company_id=company.id,
        company_status=company.status,
        company_updated_at=company.updated_at,
        first_posted_at=company.first_posted_at,
        frozen_company_fields=(sorted(IMMUTABLE_AFTER_POSTING) if company.first_posted_at else []),
        features=features,
    )


@router.post("/companies/{company_id}/features/{feature_key}/enable", response_model=FeatureView)
async def enable_feature(
    company_id: uuid.UUID,
    feature_key: str,
    body: FeatureActionRequest | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FeatureView:
    current.require("company.update")
    company = await _load_company(db, company_id, for_update=True)
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    _assert_feature_change(company, body)
    rows = await _feature_rows(db, company_id)
    by_key = {r.feature_key: r for r in rows}
    # Dependencies close upward: enabling expiry_tracking enables batch_tracking and
    # inventory too, in that order. A ValidationFailedError here (422) means the
    # feature is not offerable for this company's tax system.
    to_enable = plan_enable(
        feature_key, rows=_feature_state_map(rows), tax_system=company.default_tax_system
    )
    now = utcnow()
    for key in to_enable:
        existing = by_key.get(key)
        if existing is None:
            db.add(
                CompanyFeature(
                    id=uuid7(),
                    tenant_id=current.tenant_id,
                    company_id=company_id,
                    feature_key=key,
                    is_enabled=True,
                    enabled_at=now,
                    enabled_by=current.user_id,
                    disabled_at=None,
                    disabled_by=None,
                    locked_at=None,
                    lock_reason=None,
                )
            )
        else:
            existing.is_enabled = True
            existing.enabled_at = now
            existing.enabled_by = current.user_id
            existing.disabled_at = None
            existing.disabled_by = None
    if to_enable:
        company.updated_at = now
        company.updated_by = current.user_id
        emit(
            db,
            aggregate_type="company",
            aggregate_id=company_id,
            event_type="company.feature_enabled",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                company_id=company_id,
                action="company.feature_enabled",
                entity_type="company_feature",
                entity_id=company_id,
                actor_user_id=current.user_id,
                category="admin",
                changes={"enabled": {"from": None, "to": list(to_enable)}},
                reason=body.reason if body else None,
            ),
        )
    await db.flush()
    final = {r.feature_key: r for r in await _feature_rows(db, company_id)}.get(feature_key)
    return FeatureView(
        feature_key=feature_key,
        is_enabled=final.is_enabled if final else True,
        locked=bool(final and final.locked_at is not None),
        locked_at=final.locked_at if final else None,
    )


@router.post("/companies/{company_id}/features/{feature_key}/disable", response_model=FeatureView)
async def disable_feature(
    company_id: uuid.UUID,
    feature_key: str,
    body: FeatureActionRequest | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FeatureView:
    current.require("company.update")
    company = await _load_company(db, company_id, for_update=True)
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    _assert_feature_change(company, body)

    from identity.services.posting import guard_disable

    await guard_disable(db, company_id, feature_key)
    rows = await _feature_rows(db, company_id)
    # 422 if a dependent is still on; ImmutableFieldError (422) if the ratchet has
    # locked it — a feature that has shaped posted data can never be turned off.
    assert_disable_allowed(feature_key, rows=_feature_state_map(rows))
    by_key = {r.feature_key: r for r in rows}
    target = by_key.get(feature_key)
    now = utcnow()
    if target is not None and target.is_enabled:
        company.updated_at = now
        company.updated_by = current.user_id
        target.is_enabled = False
        target.disabled_at = now
        target.disabled_by = current.user_id
        emit(
            db,
            aggregate_type="company",
            aggregate_id=company_id,
            event_type="company.feature_disabled",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                company_id=company_id,
                action="company.feature_disabled",
                entity_type="company_feature",
                entity_id=company_id,
                actor_user_id=current.user_id,
                category="admin",
                changes={feature_key: {"from": True, "to": False}},
                reason=body.reason if body else None,
            ),
        )
        await db.flush()
    return FeatureView(
        feature_key=feature_key,
        is_enabled=False,
        locked=False,
        locked_at=None,
    )


@router.post("/companies/{company_id}/visibility", response_model=CompanyDetail)
async def set_visibility(
    company_id: uuid.UUID,
    body: FeatureActionRequest | None = None,
    visibility: str = Query(...),
    requires_step_up: bool | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    """Change a company's visibility — a display preference, but the change itself is a
    ``security`` audit event (invariant 17, company.md §6). Never removes audit rows or
    hides data from an authorized reader; it only keeps the company out of switchers."""
    current.require("company.visibility.manage")
    row = await _load_company(db, company_id)
    current.require_scope("company.visibility.manage", target=ScopePath(company_id=company_id))
    if visibility not in VISIBILITIES:
        raise ValidationFailedError(
            "unknown visibility", fields={"visibility": f"one of {', '.join(sorted(VISIBILITIES))}"}
        )
    incoming: dict[str, Any] = {"visibility": visibility}
    if requires_step_up is not None:
        incoming["requires_step_up"] = requires_step_up
    (await CompanyAccess.load(db, current)).assert_write(row, incoming)
    now = utcnow()
    changes: dict[str, dict[str, Any]] = {}
    if row.visibility != visibility:
        changes["visibility"] = {"from": row.visibility, "to": visibility}
        row.visibility = visibility
    if requires_step_up is not None and row.requires_step_up != requires_step_up:
        changes["requires_step_up"] = {"from": row.requires_step_up, "to": requires_step_up}
        row.requires_step_up = requires_step_up
    if changes:
        row.visibility_changed_at = now
        row.visibility_changed_by = current.user_id
        row.updated_at = now
        row.updated_by = current.user_id
        emit(
            db,
            aggregate_type="company",
            aggregate_id=row.id,
            event_type="company.visibility_changed",
            tenant_id=current.tenant_id,
            payload=audit_payload(
                company_id=company_id,
                action="company.visibility_changed",
                entity_type="company",
                entity_id=row.id,
                actor_user_id=current.user_id,
                category="security",
                changes=changes,
                reason=body.reason if body else None,
            ),
        )
        await db.flush()
    return (await CompanyAccess.load(db, current)).response(row, CompanyDetail)

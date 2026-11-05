"""Scoped prepared-identity commands and lean directories; no physical effects."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import (
    FilterColumn,
    Page,
    SortColumn,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.stock_tracking import normalized, validate_dates, validate_identifiers
from accounting.events.audit_contract import audit_event
from accounting.models.masters import Party, Record
from accounting.models.stock_tracking import (
    StockLot,
    StockTrackingEvent,
    StockUnit,
    StockUnitIdentifier,
)
from accounting.resources import Resource
from accounting.schemas import stock_tracking as s
from accounting.stock_resources import BATCH, SERIAL, STOCK_SAFE_FIELDS
from accounting.tasks.access import authority_fingerprint, authorize, readable, rules, writable
from accounting.tasks.commands import setup_lock

Action = Literal["prepare", "correct", "hold", "release", "retire", "reactivate"]


def command_identity(
    access: Access,
    spec: Resource,
    body: BaseModel,
    key: str,
    action: Action,
    object_id: uuid.UUID | None = None,
) -> CommandIdentity:
    return CommandIdentity(
        access.actor.tenant_id,
        access.context.company_id,
        access.actor.user_id,
        f"accounting.{spec.name}.{action}",
        key,
        {
            "body": body.model_dump(mode="json", exclude_unset=True),
            "id": str(object_id) if object_id else None,
        },
    )


def values(row: Record, spec: Resource) -> dict[str, Any]:
    return {key: getattr(row, key) for key in spec.detail.model_fields if hasattr(row, key)}


def assert_feature(access: Access, spec: Resource) -> None:
    needed = {"inventory", "batch_tracking" if spec is BATCH else "serial_tracking"}
    if not needed <= access.context.features:
        raise ConflictError("enable the applicable company inventory/tracking features first")


async def identifiers(
    db: AsyncSession, access: Access, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if not ids:
        return result
    rows = await db.execute(
        select(
            StockUnitIdentifier.unit_id,
            StockUnitIdentifier.identifier_type,
            StockUnitIdentifier.slot,
            StockUnitIdentifier.value,
        )
        .where(
            StockUnitIdentifier.company_id == access.context.company_id,
            StockUnitIdentifier.unit_id.in_(ids),
        )
        .order_by(
            StockUnitIdentifier.unit_id,
            StockUnitIdentifier.identifier_type,
            StockUnitIdentifier.slot,
        )
        .limit(3201)
    )
    for unit, kind, slot, value in rows:
        result.setdefault(unit, []).append({"identifier_type": kind, "slot": slot, "value": value})
    if sum(map(len, result.values())) > 3200:
        raise ConflictError("identifier page exceeds its validated bound")
    return result


async def detail(
    db: AsyncSession, access: Access, spec: Resource, object_id: uuid.UUID
) -> BaseModel:
    authorize(access, spec, "read")
    row = await company_object(db, spec.model, object_id, company_id=access.context.company_id)
    native = values(row, spec)
    allowed = readable(access, spec, native)
    data = {
        key: value
        for key, value in native.items()
        if key in allowed or key in {"id", "company_id", "created_at", "updated_at"}
    }
    if spec is SERIAL and "identifiers" in allowed:
        data["identifiers"] = (await identifiers(db, access, [row.id])).get(row.id, [])
    data["operational_ready"] = False
    return spec.detail.model_validate(data)


async def listing(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    query: s.BatchQuery | s.SerialQuery,
    secret: bytes,
) -> Page[Any]:
    authorize(access, spec, "read")
    allowed = readable(access, spec)
    schema: type[s.BatchListItem] | type[s.SerialListItem] = (
        s.BatchListItem if spec is BATCH else s.SerialListItem
    )
    model = spec.model
    selected = {key for key in schema.model_fields if key in allowed and hasattr(model, key)} | {
        "id"
    }
    statement = select(*(getattr(model, key) for key in sorted(selected))).where(
        model.company_id == access.context.company_id
    )
    filters = query.model_dump(
        exclude={
            "q",
            "sort",
            "cursor",
            "limit",
            "expires_before",
            "never_received",
            "receipt_eligible",
            "source_movement_id",
        },
        exclude_none=True,
    )
    statement = apply_filters(
        statement,
        filters,
        filters={key: FilterColumn(key, getattr(model, key)) for key in filters},
        readable=allowed,
    )
    if isinstance(query, s.SerialQuery) and (
        query.never_received or query.receipt_eligible or query.source_movement_id
    ):
        from accounting.models.stock import StockMovement, StockMovementUnit, StockUnitPosition
        from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POSITION

        authorize(access, STOCK_POSITION, "read")
        if not {"item_id", "quantity"} <= readable(access, STOCK_POSITION):
            raise PermissionDeniedError(
                "stock participation must be readable for receipt selection"
            )
        membership = select(StockMovementUnit.id).where(
            StockMovementUnit.company_id == access.context.company_id,
            StockMovementUnit.unit_id == StockUnit.id,
        )
        if query.source_movement_id:
            authorize(access, STOCK_MOVEMENT, "read")
            if not {"item_id", "quantity", "position_id"} <= readable(access, STOCK_MOVEMENT):
                raise PermissionDeniedError("original stock dimensions must be readable")
            await company_object(
                db, StockMovement, query.source_movement_id, company_id=access.context.company_id
            )
            statement = statement.where(
                membership.where(StockMovementUnit.movement_id == query.source_movement_id).exists()
            )
        elif query.receipt_eligible:
            if not {"status", "is_held"} <= allowed:
                raise PermissionDeniedError("serial eligibility fields must be readable")
            used = (
                select(StockUnitPosition.id)
                .where(
                    StockUnitPosition.company_id == access.context.company_id,
                    StockUnitPosition.unit_id == StockUnit.id,
                    StockUnitPosition.position_id.is_not(None)
                    | StockUnitPosition.origin_id.is_not(None),
                )
                .exists()
            )
            statement = statement.where(
                ~used, StockUnit.status == "ACTIVE", StockUnit.is_held.is_(False)
            )
        else:
            statement = statement.where(~membership.exists())
    if isinstance(query, s.BatchQuery) and query.expires_before:
        if "expires_on" not in allowed:
            raise PermissionDeniedError("expiry is not readable")
        statement = statement.where(StockLot.expires_on <= query.expires_before)
    if query.q:
        term = normalized(query.q, maximum=200)
        if spec is BATCH:
            statement = apply_search(
                statement,
                term,
                columns={"code": StockLot.normalized_code},
                readable=allowed,
                minimum_length=1,
            )
        else:
            if "identifiers" not in allowed:
                raise PermissionDeniedError("serial identifiers are not readable for search")
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            statement = statement.where(
                select(StockUnitIdentifier.id)
                .where(
                    StockUnitIdentifier.company_id == access.context.company_id,
                    StockUnitIdentifier.unit_id == StockUnit.id,
                    StockUnitIdentifier.normalized_value.startswith(escaped, escape="\\"),
                )
                .exists()
            )
    columns = {"id": SortColumn(model.id, "uuid")}
    supported = {("id",), ("-id",)}
    if spec is BATCH:
        columns["code"] = SortColumn(StockLot.code, "text")
        columns["expires_on"] = SortColumn(StockLot.expires_on, "date", nullable=True)
        supported |= {("code",), ("-code",), ("expires_on",), ("-expires_on",)}
    terms = resolve_sort(
        query.sort, default="-id", columns=columns, readable=allowed, supported=frozenset(supported)
    )
    codec = CursorCodec(
        secret,
        context=canonical_json(
            {
                "resource": spec.name,
                "tenant": str(access.actor.tenant_id),
                "company": str(access.context.company_id),
                "actor": str(access.actor.user_id),
                "authority": authority_fingerprint(access),
                "query": query.model_dump(mode="json", exclude={"cursor"}),
            }
        ).decode(),
    )
    page = await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=codec,
        project=lambda row: schema.model_validate(dict(row)),
    )
    if spec is SERIAL and "identifiers" in allowed:
        grouped = await identifiers(db, access, [row.id for row in page.items])
        page = page.model_copy(
            update={
                "items": [
                    row.model_copy(
                        update={
                            "identifiers": [
                                s.IdentifierInput.model_validate(value)
                                for value in grouped.get(row.id, [])
                            ]
                        }
                    )
                    for row in page.items
                ]
            }
        )
    return page


async def command(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    spec: Resource,
    body: s.BatchPrepare | s.SerialPrepare | s.BatchCorrect | s.ExpectedVersion,
    key: str,
    action: Action,
    object_id: uuid.UUID | None = None,
    source: s.TrackingSource | None = None,
) -> CommandResult[BaseModel]:
    if access.actor.impersonation_id:
        raise PermissionDeniedError("support sessions are read only")
    company = access.context.company_id
    needed = "hold" if action in {"hold", "release"} else "manage"

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        authorize(access, spec, "read")
        authorize(access, spec, needed)
        if action in {"prepare", "reactivate"}:
            assert_feature(access, spec)
        policy_values = {"status": "ACTIVE", "is_held": False, **body.model_dump()}
        policy_id = object_id or (uuid.UUID(receipt["id"]) if receipt else None)
        if policy_id:
            current_row = await company_object(db, spec.model, policy_id, company_id=company)
            policy_values = {**values(current_row, spec), **body.model_dump()}
        assert_fields_writable(
            {"reason"},
            rules=rules(access, spec, policy_values),
            target=ScopePath(company_id=company),
        )
        if receipt:
            row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
            native = values(row, spec)
            if spec is SERIAL:
                native["identifiers"] = (await identifiers(db, access, [row.id])).get(row.id, [])
            assert_fields_writable(
                set(receipt["changed"]),
                rules=rules(access, spec, native),
                target=ScopePath(company_id=company),
            )
            # Re-evaluate current write policies over the exact committed change.
            writable(
                access,
                spec,
                {k: v for k, v in native.items() if k not in receipt["changed"]},
                native,
            )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        before: dict[str, Any] = {}
        row: Any
        if action == "prepare":
            if (
                source is None
                or not isinstance(body, s.BatchPrepare | s.SerialPrepare)
                or source.company_id != company
                or source.item_id != body.item_id
            ):
                raise ConflictError("verified current product tracking facts are required")
            if not (source.lot_tracking if spec is BATCH else source.serial_tracking):
                raise ConflictError("the product's published profile does not enable this tracking")
            if spec is BATCH and isinstance(body, s.BatchPrepare):
                validate_dates(source, body.manufactured_on, body.expires_on)
                if body.expires_on is not None and "expiry_tracking" not in access.context.features:
                    raise ValidationFailedError(
                        "Enable expiry tracking before entering expiry dates"
                    )
                if body.mrp_amount is not None and (
                    body.mrp_currency != access.context.base_currency
                    or body.mrp_unit_id != source.base_unit_id
                ):
                    raise ValidationFailedError(
                        "Initial batch MRP requires the company currency and verified base unit"
                    )
                if body.source_party_id:
                    access.actor.require_scope(
                        "accounting.party.read", target=ScopePath(company_id=company)
                    )
                    party = await company_object(
                        db, Party, body.source_party_id, company_id=company
                    )
                    if party.status != "ACTIVE":
                        raise ConflictError("source party must be active")
                authored = body.model_dump(exclude={"reason"}, exclude_none=True)
                writable(access, spec, {}, authored | {"status": "ACTIVE", "is_held": False})
                row = StockLot(
                    id=uuid7(),
                    tenant_id=access.actor.tenant_id,
                    company_id=company,
                    created_by=access.actor.user_id,
                    updated_by=access.actor.user_id,
                    row_version=1,
                    **authored,
                    normalized_code=normalized(body.code, maximum=100),
                    namespace_key=str(body.source_party_id) if body.source_party_id else "INTERNAL",
                    status="ACTIVE",
                    is_held=False,
                    source_facts=source.model_dump(mode="json"),
                )
            elif spec is SERIAL and isinstance(body, s.SerialPrepare):
                if source.lot_tracking and body.lot_id is None:
                    raise ValidationFailedError(
                        "a batch is required by this product's tracking profile",
                        fields={"lot_id": "Select a batch for this SKU."},
                    )
                if not source.lot_tracking and body.lot_id is not None:
                    raise ValidationFailedError("this product does not use batch tracking")
                if body.lot_id:
                    authorize(access, BATCH, "read")
                    lot = await company_object(
                        db, StockLot, body.lot_id, company_id=company, lock=True
                    )
                    if lot.item_id != body.item_id or lot.status != "ACTIVE":
                        raise ConflictError(
                            "batch must be a current prepared record for the same SKU"
                        )
                prepared = validate_identifiers(source, body.identifiers)
                authored = body.model_dump(exclude={"reason"}, exclude_none=True)
                writable(access, spec, {}, authored | {"status": "ACTIVE", "is_held": False})
                row = StockUnit(
                    id=uuid7(),
                    tenant_id=access.actor.tenant_id,
                    company_id=company,
                    created_by=access.actor.user_id,
                    updated_by=access.actor.user_id,
                    row_version=1,
                    item_id=body.item_id,
                    lot_id=body.lot_id,
                    status="ACTIVE",
                    is_held=False,
                    source_facts=source.model_dump(mode="json"),
                )
                db.add(row)
                await db.flush()
                for value, normalized_value, namespace in prepared:
                    db.add(
                        StockUnitIdentifier(
                            id=uuid7(),
                            tenant_id=access.actor.tenant_id,
                            company_id=company,
                            row_version=1,
                            created_by=access.actor.user_id,
                            updated_by=access.actor.user_id,
                            unit_id=row.id,
                            identifier_type=value.identifier_type,
                            namespace_key=namespace,
                            slot=value.slot,
                            value=value.value.strip(),
                            normalized_value=normalized_value,
                            normalization_version=1,
                        )
                    )
            else:
                raise ValidationFailedError("tracking preparation input differs from its resource")
            changed = set(authored) | {"status", "is_held"}
            db.add(row)
        else:
            if object_id is None or not isinstance(body, s.ExpectedVersion):
                raise ValidationFailedError("record identity and current version are required")
            row = await company_object(db, spec.model, object_id, company_id=company, lock=True)
            if row.row_version != body.expected_version:
                raise ConflictError("record has changed; reload before retrying")
            before = values(row, spec)
            update: dict[str, Any]
            if action == "correct" and isinstance(body, s.BatchCorrect) and spec is BATCH:
                from accounting.models.stock import StockMovement, StockPosition

                used = await db.scalar(
                    select(StockMovement.id)
                    .join(
                        StockPosition,
                        StockMovement.position_id == StockPosition.id,
                    )
                    .where(
                        StockMovement.company_id == company,
                        StockPosition.company_id == company,
                        StockPosition.lot_id == row.id,
                    )
                    .limit(1)
                )
                if used:
                    raise ConflictError(
                        "batch dates are used by posted stock; "
                        "a controlled stock correction is required"
                    )
                source_rules = s.TrackingSource.model_validate(row.source_facts)
                update = body.model_dump(exclude={"reason", "expected_version"}, exclude_unset=True)
                if not update:
                    raise ValidationFailedError("at least one date correction is required")
                validate_dates(
                    source_rules,
                    update.get("manufactured_on", row.manufactured_on),
                    update.get("expires_on", row.expires_on),
                )
            elif action in {"hold", "release"}:
                update = {"is_held": action == "hold"}
            elif action in {"retire", "reactivate"}:
                if action == "retire":
                    from accounting.models.stock import (
                        StockBalance,
                        StockPosition,
                        StockUnitPosition,
                    )

                    if spec is BATCH:
                        on_hand = await db.scalar(
                            select(StockBalance.id)
                            .join(
                                StockPosition,
                                StockBalance.position_id == StockPosition.id,
                            )
                            .where(
                                StockBalance.company_id == company,
                                StockPosition.company_id == company,
                                StockPosition.lot_id == row.id,
                                StockBalance.quantity > 0,
                            )
                            .limit(1)
                        )
                    else:
                        on_hand = await db.scalar(
                            select(StockUnitPosition.id)
                            .where(
                                StockUnitPosition.company_id == company,
                                StockUnitPosition.unit_id == row.id,
                                StockUnitPosition.position_id.is_not(None),
                            )
                            .limit(1)
                        )
                    if on_hand:
                        raise ConflictError(
                            "move or reverse the remaining stock "
                            "before retiring this tracking record"
                        )
                update = {"status": "RETIRED" if action == "retire" else "ACTIVE"}
                if action == "reactivate" and spec is SERIAL and row.lot_id:
                    lot = await company_object(db, StockLot, row.lot_id, company_id=company)
                    if lot.status != "ACTIVE":
                        raise ConflictError("reactivate the associated batch first")
            else:
                raise ValidationFailedError("unsupported tracking action")
            changed = writable(access, spec, before, before | update)
            if not changed:
                return CommandReceipt(200, {"id": str(row.id), "changed": []})
            if row.row_version >= 2**31 - 1:
                raise ConflictError("record version is exhausted")
            for field, value in update.items():
                setattr(row, field, value)
            row.row_version += 1
            row.updated_at, row.updated_by = utcnow(), access.actor.user_id
        await db.flush()
        safe = STOCK_SAFE_FIELDS

        def evidence_value(value: Any) -> Any:
            return (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value)
                if isinstance(value, uuid.UUID | Decimal)
                else value
            )

        evidence = {
            field: {
                "from": evidence_value(before.get(field)),
                "to": evidence_value(getattr(row, field, None)),
            }
            if field in safe
            else {"changed": True}
            for field in sorted(changed)
        }
        db.add(
            StockTrackingEvent(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=company,
                row_version=1,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
                target_id=row.id,
                resource="BATCH" if spec is BATCH else "SERIAL",
                action=action.upper(),
                reason=body.reason,
                evidence=evidence,
            )
        )
        event = audit_event(spec.name, action)
        emit(
            db,
            tenant_id=access.actor.tenant_id,
            aggregate_type="accounting." + spec.name,
            aggregate_id=row.id,
            event_type=event,
            payload=audit_payload(
                action=event,
                category="admin",
                entity_type="accounting." + spec.name,
                entity_id=row.id,
                actor_user_id=access.actor.user_id,
                company_id=company,
                changes=evidence,
                reason=body.reason,
            ),
        )
        return CommandReceipt(
            201 if action == "prepare" else 200, {"id": str(row.id), "changed": sorted(changed)}
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return await detail(db, access, spec, uuid.UUID(receipt["id"]))

    try:
        return await execute_idempotent(
            factory,
            command_identity(access, spec, body, key, action, object_id),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    except IntegrityError as exc:
        raise ConflictError(
            "tracking identity or identifier already exists in its namespace"
        ) from exc

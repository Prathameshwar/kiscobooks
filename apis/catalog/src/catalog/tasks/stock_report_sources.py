"""Bounded immutable company master cuts using the existing definition lease."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from billing_platform.idempotency import canonical_json
from reporting_contract.inventory import Group, Location, Replenishment
from reporting_contract.inventory import Item as ItemEvidence
from sqlalchemy import JSON, LargeBinary, String, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroup, ItemGroupParent
from catalog.models.product_definitions import (
    FamilyGroupAssignment,
    ItemUnitBinding,
    ItemUnitRevision,
)
from catalog.models.products import Item, ProductFamily
from catalog.models.projections import CompanyProjection
from catalog.models.stock_source import StockSourceFence
from catalog.models.tax import ItemInventoryProfile
from catalog.models.units import UnitOfMeasure
from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouse_policies import (
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from catalog.models.warehouses import Warehouse, WarehouseOperationPolicyRevision
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.stock_sources import fence_audit

MAX_RECORDS = 10000
MAX_BYTES = 4 * 1024 * 1024


async def bounded(db: AsyncSession, model: Any, company: uuid.UUID) -> list[Any]:
    width = literal(512) + func.length(cast(model.id, LargeBinary))
    for column in model.__table__.columns:
        if isinstance(column.type, JSON | String | LargeBinary):
            width = width + func.coalesce(
                func.length(cast(getattr(model, column.key), LargeBinary)), 0
            )
    size = await db.scalar(
        select(func.coalesce(func.sum(width), 0)).where(model.company_id == company)
    )
    if size is None or size > 16 * 1024 * 1024:
        raise ConflictError("Catalog stock master snapshot exceeds its memory bound")
    rows = list(
        await db.scalars(
            select(model)
            .where(model.company_id == company)
            .order_by(model.id)
            .limit(MAX_RECORDS + 1)
        )
    )
    if len(rows) > MAX_RECORDS:
        raise ConflictError("Catalog stock master snapshot exceeds its supported capacity")
    return rows


async def masters(db: AsyncSession, company: uuid.UUID, as_of: dt.date) -> list[dict[str, Any]]:
    groups = await bounded(db, WarehouseGroup, company)
    group_ids = {row.id for row in groups}
    group_parents = [
        row
        for row in await bounded(db, WarehouseGroupParent, company)
        if row.valid_from <= as_of and (row.valid_to is None or as_of <= row.valid_to)
    ]
    memberships = [
        row
        for row in await bounded(db, WarehouseGroupAssignment, company)
        if row.valid_from <= as_of and (row.valid_to is None or as_of <= row.valid_to)
    ]
    if len({row.group_id for row in group_parents}) != len(group_parents) or len(
        {row.warehouse_id for row in memberships}
    ) != len(memberships):
        raise ConflictError("Warehouse stock grouping has overlapping effective intervals")
    if any(
        row.group_id not in group_ids
        or (row.parent_group_id is not None and row.parent_group_id not in group_ids)
        for row in group_parents
    ) or any(row.group_id not in group_ids for row in memberships):
        raise ConflictError("Warehouse stock grouping references an unavailable group")
    warehouse_parents = {row.warehouse_id: row.group_id for row in memberships}
    group_parent_ids = {row.group_id: row.parent_group_id for row in group_parents}
    timezone = await db.scalar(
        select(CompanyProjection.timezone).where(CompanyProjection.company_id == company)
    )
    now, zone = utcnow(), ZoneInfo(timezone or "UTC")
    cutoff = (
        now
        if as_of >= now.astimezone(zone).date()
        else dt.datetime.combine(as_of + dt.timedelta(days=1), dt.time.min, zone).astimezone(dt.UTC)
    )
    operation_revisions = [
        row
        for row in await bounded(db, WarehouseOperationPolicyRevision, company)
        if row.effective_from <= cutoff and (row.effective_to is None or cutoff < row.effective_to)
    ]
    if len({row.warehouse_id for row in operation_revisions}) != len(operation_revisions):
        raise ConflictError("Warehouse stock operations have overlapping effective revisions")
    sale_enabled = {row.warehouse_id: row.allow_sale_issue for row in operation_revisions}
    item_policies = {row.item_id: row for row in await bounded(db, ItemWarehousePolicy, company)}
    item_permissions: dict[uuid.UUID, dict[uuid.UUID, bool]] = {}
    for permission in await bounded(db, ItemWarehousePermission, company):
        if permission.is_active:
            item_permissions.setdefault(permission.item_id, {})[permission.warehouse_id] = (
                permission.allow_sale_issue
            )
    families = {r.id: r for r in await bounded(db, ProductFamily, company)}
    units = {r.id: r for r in await bounded(db, UnitOfMeasure, company)}
    profiles = {r.item_id: r for r in await bounded(db, ItemInventoryProfile, company)}
    bindings = {r.id: r for r in await bounded(db, ItemUnitBinding, company)}
    revisions: dict[uuid.UUID, list[Any]] = {}
    for revision in await bounded(db, ItemUnitRevision, company):
        if revision.valid_from <= as_of and (
            revision.valid_to is None or as_of <= revision.valid_to
        ):
            revisions.setdefault(revision.binding_id, []).append(revision)
    policies: dict[uuid.UUID, list[Any]] = {}
    for policy in await bounded(db, ItemReplenishmentPolicy, company):
        if policy.is_active:
            policies.setdefault(policy.item_id, []).append(policy)
    assignments = [
        r
        for r in await bounded(db, FamilyGroupAssignment, company)
        if r.valid_from <= as_of and (r.valid_to is None or as_of <= r.valid_to)
    ]
    parents = [
        r
        for r in await bounded(db, ItemGroupParent, company)
        if r.valid_from <= as_of and (r.valid_to is None or as_of <= r.valid_to)
    ]
    if len({r.group_id for r in parents}) != len(parents):
        raise ConflictError("Catalog stock group hierarchy has overlapping effective parents")
    parent_map = {r.group_id: r.parent_group_id for r in parents}
    records = [
        Group(group_id=r.id, code=r.code, name=r.name, parent_id=parent_map.get(r.id)).model_dump(
            mode="json"
        )
        for r in await bounded(db, ItemGroup, company)
    ]
    records.extend(
        Location(
            location_id=r.id,
            code=r.code,
            name=r.name,
            parent_id=warehouse_parents.get(r.id),
            sale_eligible=r.is_active
            and r.kind != "INTERNAL_TRANSIT"
            and sale_enabled.get(r.id, False),
        ).model_dump(mode="json")
        for r in await bounded(db, Warehouse, company)
    )
    records.extend(
        Location(
            location_id=row.id,
            code=row.code,
            name=row.name,
            parent_id=group_parent_ids.get(row.id),
            is_group=True,
            sale_eligible=False,
        ).model_dump(mode="json")
        for row in groups
    )
    for row in await bounded(db, Item, company):
        family = families.get(row.family_id)
        if family is None:
            raise ConflictError("Catalog stock item family is unavailable")
        if family.kind != "GOODS":
            continue
        unit = units.get(row.base_unit_id)
        if unit is None:
            raise ConflictError("Catalog stock item base unit is unavailable")
        profile = profiles.get(row.id)
        replenishment = []
        for policy in policies.get(row.id, []):
            binding = bindings.get(policy.purchase_binding_id)
            current = revisions.get(policy.purchase_binding_id, [])
            if (
                binding is None
                or binding.item_id != row.id
                or len(current) != 1
                or current[0].conversion_mode != "FIXED"
            ):
                raise ConflictError(
                    "a replenishment band needs one verified fixed ordering-unit conversion"
                )
            revision = current[0]
            values: dict[str, Any] = {}
            with localcontext() as arithmetic:
                arithmetic.prec = 48
                for target, source in (
                    ("reorder_level", "reorder_quantity"),
                    ("target_level", "target_quantity"),
                    ("minimum_order", "min_order_quantity"),
                    ("maximum_order", "max_order_quantity"),
                    ("order_multiple", "order_multiple"),
                ):
                    native = getattr(policy, source)
                    if native is None:
                        values[target] = None
                        continue
                    quantity = native * Decimal(revision.numerator) / Decimal(revision.denominator)
                    if quantity != quantity.quantize(Decimal("0.0001")):
                        raise ConflictError(
                            "replenishment quantities exceed the exact base-unit storage scale"
                        )
                    values[target] = format(quantity, ".4f")
            replenishment.append(
                Replenishment(policy_id=policy.id, location_id=policy.warehouse_id, **values)
            )
        records.append(
            ItemEvidence(
                item_id=row.id,
                code=row.sku,
                name=row.name,
                unit=unit.code,
                group_ids=[r.group_id for r in assignments if r.family_id == row.family_id],
                active=row.status == "ACTIVE" and family.status == "ACTIVE",
                lot_tracked=bool(profile and profile.lot_tracking),
                serial_tracked=bool(profile and profile.serial_tracking),
                minimum_remaining_days=(profile.minimum_remaining_life_days or 0) if profile else 0,
                replenishment=replenishment,
                sale_location_mode=item_policies[row.id].selection_mode
                if row.id in item_policies
                else "ALLOW_ALL_ACTIVE",
                sale_location_permissions=item_permissions.get(row.id, {}),
            ).model_dump(mode="json")
        )
    if (
        len(records) > MAX_RECORDS
        or len(canonical_json(records, maximum_bytes=MAX_BYTES)) > MAX_BYTES
    ):
        raise ConflictError("Catalog stock master snapshot exceeds its supported capacity")
    return records


async def page(
    db: AsyncSession,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
    as_of: dt.date,
    offset: int,
    release: bool,
) -> dict[str, Any]:
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    row = await db.scalar(
        select(StockSourceFence)
        .where(StockSourceFence.company_id == company, StockSourceFence.execution_id == identity)
        .with_for_update()
    )
    fingerprint = hashlib.sha256(
        canonical_json(
            {
                "purpose": "REPORT",
                "as_of": as_of.isoformat(),
                "tenant": str(tenant),
                "company": str(company),
            }
        )
    ).hexdigest()
    if row is None:
        if offset or release:
            raise NotFoundError("Catalog stock source lease is unavailable")
        # Current classification is not certified as historical master evidence.
        if abs((utcnow().date() - as_of).days) > 1:
            raise ConflictError("a new stock master snapshot requires the current business date")
        records = await masters(db, company, as_of)
        facts = {
            "purpose": "REPORT",
            "records": records,
            "as_of": as_of.isoformat(),
            "policy_hash": hashlib.sha256(
                canonical_json(
                    {"generation": state.generation, "records": records}, maximum_bytes=MAX_BYTES
                )
            ).hexdigest(),
            "content_hash": hashlib.sha256(
                canonical_json(records, maximum_bytes=MAX_BYTES)
            ).hexdigest(),
        }
        row = StockSourceFence(
            id=identity,
            tenant_id=tenant,
            company_id=company,
            execution_id=identity,
            actor_user_id=uuid.UUID(int=0),
            request_hash=fingerprint,
            expires_at=utcnow() + dt.timedelta(minutes=5),
            facts=facts,
            created_by=None,
            updated_by=None,
        )
        db.add(row)
        fence_audit(db, row, "report_acquired")
        await db.flush()
    if row.request_hash != fingerprint or row.facts.get("purpose") != "REPORT":
        raise ConflictError("Catalog stock source lease belongs to another request")
    if row.closed_at is not None or row.expires_at <= utcnow():
        raise ConflictError("Catalog stock source lease expired; retry with a new source request")
    records = row.facts["records"]
    if offset > len(records) or offset % 200:
        raise ConflictError("Catalog stock source cursor is outside the frozen cut")
    selected = records[offset : offset + 200]
    if release:
        row.closed_at = utcnow()
        fence_audit(db, row, "report_released")
    return {
        "tenant_id": tenant,
        "company_id": company,
        "source_id": identity,
        "as_of": as_of,
        "expires_at": row.expires_at,
        "policy_hash": row.facts["policy_hash"],
        "content_hash": row.facts["content_hash"],
        "record_count": len(records),
        "offset": offset,
        "records": selected,
        "next_offset": offset + len(selected) if offset + len(selected) < len(records) else None,
    }

"""Fixed onboarding defaults; no inferred container sizes or changes to retained units."""

import uuid
from importlib.resources import files
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError
from billing_platform.exact import RationalConversion
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.units import CanonicalRelation
from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import audit_change, changes
from catalog.models import PackType, UnitConversion, UnitOfMeasure
from catalog.models.projections import CompanyFeatureProjection, CompanyProjection
from catalog.schemas.unit_defaults import StarterUnit, UnitDefaultsResult, UnitStarterPack
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.projections import require_identity_context
from catalog.tasks.unit_relations import unit_definition


def starter_pack() -> UnitStarterPack:
    return UnitStarterPack.model_validate_json(
        files("catalog.seeds").joinpath("unit_defaults_v1.json").read_text(encoding="utf-8")
    )


async def inventory_enabled(db: AsyncSession, company: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(CompanyFeatureProjection.id)
            .where(
                CompanyFeatureProjection.company_id == company,
                CompanyFeatureProjection.feature_key == "inventory",
                CompanyFeatureProjection.is_enabled.is_(True),
            )
            .limit(1)
        )
    )


def compatible(row: UnitOfMeasure, definition: StarterUnit) -> bool:
    return bool(
        row.is_active
        and row.dimension == definition.dimension
        and row.decimal_places == definition.decimal_places
        and row.quantity_increment == definition.quantity_increment
    )


async def ensure_unit_defaults(
    db: AsyncSession,
    company: uuid.UUID,
    *,
    actor: Actor | None = None,
    writes: list[dict[str, Any]] | None = None,
) -> UnitDefaultsResult:
    tenant = require_current_tenant()
    if actor is not None and actor.tenant_id != tenant:
        raise ConflictError("unit defaults authority differs from the company tenant")
    await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    pack = starter_pack()
    inventory = await inventory_enabled(db, company)
    result = UnitDefaultsResult(
        company_id=company,
        pack_version=pack.version,
        status="NOT_APPLICABLE",
        inventory_enabled=inventory,
    )
    if profile.status != "active":
        return result
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    definitions = {row.code: row for row in pack.units if inventory or not row.inventory}
    units = {
        row.code: row
        for row in await db.scalars(
            select(UnitOfMeasure)
            .where(
                UnitOfMeasure.company_id == company,
                UnitOfMeasure.code.in_(definitions),
            )
            .limit(65)
            .with_for_update()
        )
    }
    relations = (
        {
            row.from_unit_id: row
            for row in await db.scalars(
                select(UnitConversion)
                .where(
                    UnitConversion.company_id == company,
                    UnitConversion.from_unit_id.in_([u.id for u in units.values()]),
                )
                .limit(65)
            )
        }
        if units
        else {}
    )
    packs = (
        set(
            await db.scalars(
                select(PackType.code)
                .where(
                    PackType.company_id == company,
                    PackType.code.in_([p.code for p in pack.packs]),
                )
                .limit(33)
            )
        )
        if inventory
        else set()
    )
    access = ConfigurationAccess(db, actor, company) if actor else None
    changed = False

    async def create(model: type[Any], **values: Any) -> Any:
        nonlocal changed
        row = model(
            id=uuid7(),
            tenant_id=tenant,
            company_id=company,
            created_by=actor.user_id if actor else None,
            updated_by=actor.user_id if actor else None,
            **values,
        )
        entity = "catalog." + model.__tablename__
        fields = frozenset(values) - {"row_version"}
        if access:
            context = await access.context(model)
            context.assert_writable(fields, before={}, after=values)
        if actor:
            audit_change(
                db, actor, company, entity, row.id, "create", fields, before={}, after=values
            )
        else:
            event = audit_event(entity, "create")
            payload = audit_payload(
                action=event,
                category=category(entity, "create"),
                entity_type=entity,
                entity_id=row.id,
                actor_user_id=None,
                company_id=company,
                changes=changes(entity, fields, after=values, creating=True),
                reason=pack.version,
            )
            payload.update(actor_type="system", source_service="catalog")
            emit(
                db,
                aggregate_type=entity,
                aggregate_id=row.id,
                event_type=event,
                tenant_id=tenant,
                payload=payload,
            )
        db.add(row)
        await db.flush()
        if writes is not None:
            writes.append({"entity": entity, "id": str(row.id), "fields": sorted(fields)})
        changed = True
        return row

    fresh = set()
    for code, definition in definitions.items():
        if code in units:
            result.preserved_records += 1
            continue
        units[code] = await create(
            UnitOfMeasure,
            **definition.model_dump(
                exclude={
                    "inventory",
                    "canonical_code",
                    "numerator",
                    "denominator",
                }
            ),
            is_active=True,
            row_version=1,
        )
        fresh.add(code)
        result.units_created += 1

    # Roots first, independent of manifest ordering. Existing units are never
    # given a new relation: that could reinterpret retained SKU ratios/history.
    ordered = sorted(definitions.values(), key=lambda d: (d.code != d.canonical_code, d.code))
    for definition in ordered:
        source, root = units[definition.code], units[definition.canonical_code]
        if source.id in relations:
            result.preserved_records += 1
            continue
        if definition.code not in fresh:
            result.notices.append(
                f"{definition.code}: existing unit preserved without adding a conversion."
            )
            continue
        root_relation = relations.get(root.id)
        if not compatible(root, definitions[definition.canonical_code]) or (
            source.id != root.id
            and (
                root_relation is None
                or root_relation.canonical_unit_id != root.id
                or (root_relation.numerator, root_relation.denominator) != (1, 1)
            )
        ):
            result.notices.append(
                f"{definition.code}: canonical settings need review; no conversion added."
            )
            continue
        ratio = RationalConversion(definition.numerator, definition.denominator)
        CanonicalRelation(unit_definition(source), unit_definition(root), ratio)
        relation = await create(
            UnitConversion,
            from_unit_id=source.id,
            canonical_unit_id=root.id,
            numerator=ratio.numerator,
            denominator=ratio.denominator,
        )
        relations[source.id] = relation
        result.conversions_created += 1

    if inventory:
        for pack_definition in pack.packs:
            if pack_definition.code in packs:
                result.preserved_records += 1
                continue
            await create(PackType, **pack_definition.model_dump(), is_active=True, row_version=1)
            result.packs_created += 1
    if changed:
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation exhausted")
        state.generation += 1
        await db.flush()
    result.status = "READY"
    return result


async def bootstrap_unit_defaults(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    key: str,
    *,
    expected_inventory: bool | None = None,
) -> CommandResult[UnitDefaultsResult]:
    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await require_identity_context(db, company)
        target = ScopePath(company_id=company)
        permissions = ["unit.read", "unit.manage"]
        if await inventory_enabled(db, company):
            permissions += ["pack_type.read", "pack_type.manage"]
        for permission in permissions:
            actor.require_scope(permission, target=target)
        access = ConfigurationAccess(db, actor, company)
        await access.context(UnitOfMeasure, "unit.manage")
        if expected_inventory is not None and expected_inventory != await inventory_enabled(
            db, company
        ):
            # Never commit a successful receipt for an older feature snapshot.
            raise IdentitySourceUnavailableError("company inventory settings are synchronizing")
        # Replays check the exact committed writes against current row values,
        # including conditional field policies, just like ordinary master commands.
        if receipt:
            models = {
                "catalog." + model.__tablename__: model
                for model in (UnitOfMeasure, UnitConversion, PackType)
            }
            for write in receipt["_writes"]:
                model = models[write["entity"]]
                context = await access.context(model)
                row = await company_object(db, model, uuid.UUID(write["id"]), company_id=company)
                native = {key: getattr(row, key) for key in context.native.fields}
                context.assert_writable(frozenset(write["fields"]), before=native, after=native)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        writes: list[dict[str, Any]] = []
        result = await ensure_unit_defaults(db, company, actor=actor, writes=writes)
        return CommandReceipt(200, {**result.model_dump(mode="json"), "_writes": writes})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> UnitDefaultsResult:
        return UnitDefaultsResult.model_validate(
            {k: v for k, v in receipt.items() if k != "_writes"}
        )

    return await execute_idempotent(
        factory,
        CommandIdentity(
            tenant_id=actor.tenant_id,
            company_id=company,
            actor_id=actor.user_id,
            operation="catalog.units.defaults." + starter_pack().version.lower(),
            key=key,
            request={"expected_inventory": expected_inventory},
        ),
        authorize=authorize,
        mutate=mutate,
        render=render,
    )

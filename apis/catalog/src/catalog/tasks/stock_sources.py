"""Closed, company-scoped owner facts under a bounded definition lease."""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Sequence
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.company_context import verify_company_context
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
)
from billing_platform.gateway import Actor, decode_actor_context
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock_facts import StockFenceFacts, StockFenceRequest

from catalog.domain.warehouse_resolution import OPERATIONS
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.stock_source import StockSourceFence
from catalog.models.tax import ItemInventoryProfile
from catalog.models.units import UnitOfMeasure
from catalog.models.warehouse_policies import ItemWarehousePermission, ItemWarehousePolicy
from catalog.models.warehouses import CompanyWarehouseConfiguration, Warehouse, WarehouseBin
from catalog.tasks.field_context import FieldContext, load_field_context
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.warehouse_operations import open_revisions

PROFILE_FIELDS = frozenset(
    {
        "lot_tracking",
        "serial_tracking",
        "expiry_required",
        "manufacture_date_required",
        "shelf_life_days",
        "minimum_remaining_life_days",
        "issue_strategy",
        "valuation_method",
        "negative_stock_policy",
        "identifier_profile_id",
    }
)


def fence_audit(db: AsyncSession, row: StockSourceFence, action: str) -> None:
    event = "catalog.stock_source_fence." + action
    emit(
        db,
        tenant_id=row.tenant_id,
        aggregate_type="catalog.stock_source_fence",
        aggregate_id=row.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="system",
            entity_type="catalog.stock_source_fence",
            entity_id=row.id,
            actor_user_id=None,
            company_id=row.company_id,
        )
        | {"actor_type": "system"},
    )


def verified_actor(body: StockFenceRequest, secret: bytes) -> Actor:
    authority = body.authority
    actor = decode_actor_context(authority.actor_context, authority.actor_signature, secret)
    context = verify_company_context(authority.company_context, authority.company_signature, secret)
    context.assert_current(actor, body.company_id)
    if (actor.tenant_id, actor.user_id) != (body.tenant_id, body.actor_user_id):
        raise AuthenticationRequiredError("stock source authority differs from the gateway subject")
    required_namespaces = {"accounting"}
    if body.purpose == "EXECUTION":
        required_namespaces.add("vouchers")
    if actor.impersonation_id or not required_namespaces <= context.policy_namespaces:
        raise PermissionDeniedError("stock source requires complete original actor authority")
    if not utcnow() < body.authority_expires_at <= utcnow() + dt.timedelta(minutes=5):
        raise AuthenticationRequiredError("stock source authority is stale")
    actor.require_scope(
        "accounting.stock.read"
        if body.purpose == "PREVIEW"
        else "accounting.stock.reverse"
        if body.action == "REVERSE"
        else "accounting.stock.post",
        target=ScopePath(company_id=body.company_id),
    )
    if "inventory" not in context.features:
        raise ConflictError("company inventory is not enabled")
    return actor


def visible(context: FieldContext, row: Any, required: set[str] | frozenset[str]) -> None:
    values = {key: getattr(row, key) for key in context.native.fields if hasattr(row, key)}
    if not required <= context.readable(values):
        raise PermissionDeniedError("stock source fields are protected by current field policies")


def readable_label(context: FieldContext, row: Any, field: str) -> str | None:
    """A label a print shows, or None when this actor may not read it; never a refusal."""
    values = {key: getattr(row, key) for key in context.native.fields if hasattr(row, key)}
    value = getattr(row, field, None)
    return value if field in context.readable(values) and isinstance(value, str) and value else None


async def rows(db: AsyncSession, model: Any, company: Any, keys: Sequence[Any]) -> dict[Any, Any]:
    result = list(
        await db.scalars(
            select(model)
            .where(
                model.company_id == company,
                model.id.in_(keys),
            )
            .limit(len(keys) + 1)
        )
    )
    if {row.id for row in result} != set(keys):
        raise ConflictError("stock source reference is unavailable in this company")
    return {row.id: row for row in result}


async def purchase_tax(
    db: AsyncSession, actor: Actor, company: Any, item: Item, request: StockFenceRequest
) -> dict[str, Any] | None:
    """The item's complete purchase GST bundle on the stock date, as identities only.

    Resolved through the same dated ancestry as product activation, under the delegated
    user's own field access. An incomplete bundle is absent rather than guessed: Accounting
    then refuses the bill with what to assign.
    """
    from catalog.models.tax import TaxClassification, TaxRule
    from catalog.schemas.tax import ResolveInput
    from catalog.tasks.configuration_access import ConfigurationAccess
    from catalog.tasks.tax_resolution import resolve

    if not item.purchasable:
        return None
    access = ConfigurationAccess(db, actor, company)
    try:
        result = await resolve(
            access,
            ResolveInput(item_id=item.id, as_of=request.stock_date, direction="PURCHASE"),
        )
    except ConflictError:
        return None
    if (
        result.status != "COMPLETE"
        or result.classification_id is None
        or result.rule_id is None
        or result.treatment is None
    ):
        return None
    classification = await db.scalar(
        select(TaxClassification).where(
            TaxClassification.company_id == company,
            TaxClassification.id == result.classification_id,
        )
    )
    rule = await db.scalar(
        select(TaxRule).where(TaxRule.company_id == company, TaxRule.id == result.rule_id)
    )
    if classification is None or rule is None:
        return None
    return {
        "classification_id": classification.id,
        "classification_version": classification.row_version,
        "code": classification.code,
        "rule_id": rule.id,
        "rule_version": rule.row_version,
        "treatment": result.treatment,
    }


async def build(
    db: AsyncSession, actor: Actor, request: StockFenceRequest, generation: int
) -> StockFenceFacts:
    company = request.company_id
    cache: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    contexts: dict[str, FieldContext] = {}
    for entity in (
        "item",
        "product_family",
        "item_inventory_profile",
        "inventory_profile_template_revision",
        "unit_of_measure",
        "item_unit_binding",
        "item_unit_revision",
        "warehouse",
        "warehouse_bin",
        "warehouse_operation_policy_revision",
        "item_warehouse_policy",
        "item_warehouse_permission",
    ):
        contexts[entity] = await load_field_context(
            db,
            actor,
            company,
            "catalog." + entity,
            permission="accounting.stock.read"
            if request.purpose == "PREVIEW"
            else "accounting.stock.reverse"
            if request.action == "REVERSE"
            else "accounting.stock.post",
            subject_cache=cache,
        )
    context = contexts["item"]
    if "inventory" not in context.features:
        raise ConflictError("verified company source does not enable inventory")
    configuration = await db.scalar(
        select(CompanyWarehouseConfiguration).where(
            CompanyWarehouseConfiguration.company_id == company,
        )
    )
    if configuration is None:
        raise ConflictError("initialize company warehouses before posting stock")
    warehouse_ids = set(request.warehouse_ids) | {configuration.transit_warehouse_id}
    warehouses = await rows(db, Warehouse, company, tuple(warehouse_ids))
    policies = await open_revisions(db, company, tuple(warehouse_ids))
    if set(policies) != warehouse_ids:
        raise ConflictError("warehouse operation policies are incomplete")
    warehouse_facts = []
    for identity, warehouse in sorted(warehouses.items()):
        revision = policies[identity]
        location_fields = {
            "country_code",
            "state_code",
            "tax_registration_id",
            "timezone",
            "address_line1",
            "address_line2",
            "city",
            "postal_code",
        }
        visible(contexts["warehouse"], warehouse, {"kind", "is_active"} | location_fields)
        visible(contexts["warehouse_operation_policy_revision"], revision, set(OPERATIONS.values()))
        warehouse_facts.append(
            {
                "warehouse_id": identity,
                "row_version": warehouse.row_version,
                "kind": warehouse.kind,
                "is_active": warehouse.is_active,
                "department_id": warehouse.department_id,
                **{key: getattr(warehouse, key) for key in location_fields},
                "policy_revision_id": revision.id,
                "allowed_operations": tuple(
                    operation for operation, flag in OPERATIONS.items() if getattr(revision, flag)
                ),
            }
        )
    bins = await rows(db, WarehouseBin, company, request.bin_ids)
    bin_facts = []
    for identity, bin_row in sorted(bins.items()):
        visible(contexts["warehouse_bin"], bin_row, {"warehouse_id", "is_active"})
        if (
            bin_row.warehouse_id not in warehouse_ids
            or bin_row.warehouse_id == configuration.transit_warehouse_id
        ):
            raise ConflictError("stock bin is not an actual selected warehouse's bin")
        bin_facts.append(
            {
                "bin_id": identity,
                "warehouse_id": bin_row.warehouse_id,
                "row_version": bin_row.row_version,
                "is_active": bin_row.is_active,
            }
        )
    items = await rows(db, Item, company, request.item_ids)
    # Activation and stock posting are separate owner transactions. A creation
    # still in progress must not become an ordinary tradable item in that gap.
    if (
        request.purpose == "EXECUTION"
        and request.action != "REVERSE"
        and not request.opening_unit_revision_ids
    ):
        from catalog.models.simple_product_creation import SimpleProductCreation

        if await db.scalar(
            select(SimpleProductCreation.id)
            .where(
                SimpleProductCreation.company_id == company,
                SimpleProductCreation.item_id.in_(request.item_ids),
                SimpleProductCreation.status == "RUNNING",
            )
            .limit(1)
        ):
            raise ConflictError("Finish product creation before posting ordinary stock")
    families = await rows(
        db, ProductFamily, company, tuple({row.family_id for row in items.values()})
    )
    profiles = list(
        await db.scalars(
            select(ItemInventoryProfile)
            .where(
                ItemInventoryProfile.company_id == company,
                ItemInventoryProfile.item_id.in_(request.item_ids),
            )
            .limit(len(items) + 1)
        )
    )
    profiles_by_item = {row.item_id: row for row in profiles}
    if set(profiles_by_item) != set(items) or len(profiles_by_item) != len(profiles):
        raise ConflictError(
            "an activated native inventory profile is required for every stock item"
        )
    revisions = await rows(
        db,
        InventoryProfileTemplateRevision,
        company,
        tuple({row.template_revision_id for row in profiles}),
    )
    units = await rows(
        db, UnitOfMeasure, company, tuple({row.base_unit_id for row in items.values()})
    )
    bindings = list(
        await db.scalars(
            select(ItemUnitBinding)
            .where(
                ItemUnitBinding.company_id == company,
                ItemUnitBinding.item_id.in_(request.item_ids),
                ItemUnitBinding.usage_role == "BASE",
            )
            .limit(len(items) + 1)
        )
    )
    base_bindings = {row.item_id: row for row in bindings}
    if set(base_bindings) != set(items) or len(base_bindings) != len(bindings):
        raise ConflictError("exactly one native base-unit binding is required per stock item")
    unit_revisions = list(
        await db.scalars(
            select(ItemUnitRevision)
            .where(
                ItemUnitRevision.company_id == company,
                ItemUnitRevision.binding_id.in_([row.id for row in bindings]),
                ItemUnitRevision.valid_from <= request.stock_date,
                or_(
                    ItemUnitRevision.valid_to.is_(None),
                    ItemUnitRevision.valid_to >= request.stock_date,
                ),
            )
            .limit(len(items) + 1)
        )
    )
    base_rules = {row.binding_id: row for row in unit_revisions}
    if len(base_rules) != len(unit_revisions) or set(base_rules) != {row.id for row in bindings}:
        raise ConflictError("base-unit revision is missing or ambiguous for the stock date")
    product_policies = {
        row.item_id: row
        for row in await db.scalars(
            select(ItemWarehousePolicy)
            .where(
                ItemWarehousePolicy.company_id == company,
                ItemWarehousePolicy.item_id.in_(request.item_ids),
            )
            .limit(len(items) + 1)
        )
    }
    restrictions = {
        (row.item_id, row.warehouse_id): row
        for row in await db.scalars(
            select(ItemWarehousePermission)
            .where(
                ItemWarehousePermission.company_id == company,
                ItemWarehousePermission.item_id.in_(request.item_ids),
                ItemWarehousePermission.warehouse_id.in_(warehouse_ids),
            )
            .limit(len(items) * len(warehouse_ids) + 1)
        )
    }
    item_facts = []
    opening_rules = (
        await rows(db, ItemUnitRevision, company, request.opening_unit_revision_ids)
        if request.opening_unit_revision_ids
        else {}
    )
    opening_bindings = (
        await rows(
            db, ItemUnitBinding, company, tuple({row.binding_id for row in opening_rules.values()})
        )
        if opening_rules
        else {}
    )
    opening_units = (
        await rows(
            db, UnitOfMeasure, company, tuple({row.unit_id for row in opening_bindings.values()})
        )
        if opening_bindings
        else {}
    )
    opening_facts: dict[Any, list[dict[str, Any]]] = {}
    from catalog.tasks.stock_quantity_sources import quantity_facts

    if request.opening_unit_revision_ids:
        await quantity_facts(
            db,
            actor,
            request.model_copy(
                update={"quantity_unit_revision_ids": request.opening_unit_revision_ids}
            ),
            items,
            contexts,
        )
    for opening_rule in sorted(opening_rules.values(), key=lambda row: row.id):
        opening_binding = opening_bindings[opening_rule.binding_id]
        opening_unit = opening_units[opening_binding.unit_id]
        visible(
            contexts["item_unit_binding"], opening_binding, {"item_id", "unit_id", "usage_role"}
        )
        visible(
            contexts["item_unit_revision"],
            opening_rule,
            {
                "valid_from",
                "valid_to",
                "conversion_mode",
                "numerator",
                "denominator",
                "quantity_increment",
                "quantity_decimal_places",
                "fractional_entry",
            },
        )
        visible(
            contexts["unit_of_measure"],
            opening_unit,
            {
                "is_active",
                "quantity_increment",
                "decimal_places",
            },
        )
        if (
            opening_binding.item_id not in items
            or not opening_unit.is_active
            or opening_rule.quantity_increment % opening_unit.quantity_increment
            or opening_rule.valid_from > request.stock_date
            or (opening_rule.valid_to is not None and opening_rule.valid_to < request.stock_date)
        ):
            raise ConflictError("opening conversion requires this item's effective unit revision")
        opening_facts.setdefault(opening_binding.item_id, []).append(
            {
                "item_id": opening_binding.item_id,
                "unit_id": opening_unit.id,
                "revision_id": opening_rule.id,
                "conversion_mode": opening_rule.conversion_mode,
                "numerator": opening_rule.numerator,
                "denominator": opening_rule.denominator,
                "quantity_increment": str(opening_rule.quantity_increment),
                "quantity_decimal_places": min(
                    opening_unit.decimal_places, opening_rule.quantity_decimal_places
                )
                if opening_rule.fractional_entry
                else 0,
            }
        )
    quantity_units = await quantity_facts(db, actor, request, items, contexts)
    for identity, item in sorted(items.items()):
        family, profile = families[item.family_id], profiles_by_item[identity]
        revision, unit = revisions[profile.template_revision_id], units[item.base_unit_id]
        binding = base_bindings[identity]
        rule = base_rules[binding.id]
        visible(
            contexts["item"],
            item,
            {"family_id", "status", "base_unit_id", "sellable", "purchasable"},
        )
        visible(contexts["product_family"], family, {"status", "kind"})
        visible(
            contexts["item_inventory_profile"],
            profile,
            PROFILE_FIELDS | {"base_unit_id", "template_revision_id"},
        )
        visible(
            contexts["inventory_profile_template_revision"],
            revision,
            PROFILE_FIELDS | {"published_at"},
        )
        visible(
            contexts["unit_of_measure"], unit, {"quantity_increment", "decimal_places", "is_active"}
        )
        visible(contexts["item_unit_binding"], binding, {"unit_id", "usage_role"})
        visible(
            contexts["item_unit_revision"],
            rule,
            {
                "quantity_increment",
                "quantity_decimal_places",
                "fractional_entry",
                "conversion_mode",
                "numerator",
                "denominator",
            },
        )
        if (
            family.kind != "GOODS"
            or item.status == "DRAFT"
            or family.status == "DRAFT"
            or not unit.is_active
            or revision.published_at is None
            or profile.base_unit_id != item.base_unit_id
            or binding.unit_id != item.base_unit_id
        ):
            raise ConflictError("stock requires activated goods and their active native base unit")
        from catalog.tasks.configuration_access import ConfigurationAccess
        from catalog.tasks.product_stock_choice import profile_values, selection

        expected_profile = profile_values(
            revision, await selection(ConfigurationAccess(db, actor, company), identity)
        )
        if any(getattr(profile, key) != expected_profile[key] for key in PROFILE_FIELDS):
            raise ConflictError("activated inventory rules differ from their published revision")
        if (
            rule.conversion_mode != "FIXED"
            or rule.numerator != 1
            or rule.denominator != 1
            or rule.quantity_increment % unit.quantity_increment
        ):
            raise ConflictError("native base-unit quantity grid is inconsistent")
        if (
            (profile.lot_tracking and "batch_tracking" not in context.features)
            or (profile.serial_tracking and "serial_tracking" not in context.features)
            or (profile.expiry_required and "expiry_tracking" not in context.features)
        ):
            raise ConflictError("stock profile requires disabled company tracking capabilities")
        policy = product_policies.get(identity)
        if policy:
            visible(contexts["item_warehouse_policy"], policy, {"selection_mode"})
        allow_list = []
        permissions = []
        for warehouse_fact in warehouse_facts:
            warehouse_id = warehouse_fact["warehouse_id"]
            restriction = restrictions.get((identity, warehouse_id))
            allowed = warehouse_fact["allowed_operations"]
            if (
                warehouse_id != configuration.transit_warehouse_id
                and policy
                and policy.selection_mode == "ALLOW_LIST"
            ):
                if restriction is None or not restriction.is_active:
                    allowed = ()
                else:
                    visible(
                        contexts["item_warehouse_permission"],
                        restriction,
                        {"is_active", *OPERATIONS.values()},
                    )
                    allowed = tuple(
                        operation
                        for operation in allowed
                        if getattr(restriction, OPERATIONS[operation])
                    )
            if allowed:
                allow_list.append(warehouse_id)
            permissions.append({"warehouse_id": warehouse_id, "allowed_operations": allowed})
        item_facts.append(
            {
                "item_id": identity,
                "family_id": family.id,
                "item_version": item.row_version,
                "family_version": family.row_version,
                "status": item.status,
                "family_status": family.status,
                "kind": family.kind,
                "base_unit_id": item.base_unit_id,
                "quantity_increment": str(rule.quantity_increment),
                "quantity_decimal_places": min(unit.decimal_places, rule.quantity_decimal_places)
                if rule.fractional_entry
                else 0,
                "profile_id": profile.id,
                "profile_revision_id": revision.id,
                **{
                    key: getattr(profile, key) for key in PROFILE_FIELDS - {"identifier_profile_id"}
                },
                "sellable": item.sellable,
                "purchasable": item.purchasable,
                "allowed_warehouse_ids": tuple(allow_list)
                if policy and policy.selection_mode == "ALLOW_LIST"
                else None,
                "warehouse_permissions": permissions,
                "opening_units": opening_facts.get(identity, []),
                "quantity_units": quantity_units.get(identity, []),
                **(
                    {"purchase_tax": await purchase_tax(db, actor, company, item, request)}
                    if request.include_purchase_tax
                    else {}
                ),
                **(
                    {"base_unit_label": readable_label(contexts["unit_of_measure"], unit, "symbol")}
                    if request.include_labels
                    else {}
                ),
            }
        )
    now = utcnow()
    return StockFenceFacts.model_validate(
        {
            "purpose": request.purpose,
            "action": request.action,
            "tenant_id": request.tenant_id,
            "company_id": company,
            "execution_id": request.execution_id,
            "actor_user_id": actor.user_id,
            "fence_id": uuid7(),
            "stock_date": request.stock_date,
            "issued_at": now,
            "expires_at": min(now + dt.timedelta(seconds=60), request.authority_expires_at),
            "policy_generation": generation,
            "source_version": context.source_version,
            "content_hash": request.content_hash,
            "items": item_facts,
            "warehouses": warehouse_facts,
            "bins": bin_facts,
        }
    )


async def acquire(db: AsyncSession, request: StockFenceRequest, actor: Actor) -> StockFenceFacts:
    state = await company_policy_state(db, request.tenant_id, request.company_id, lock=True)
    assert state is not None
    digest = hashlib.sha256(
        canonical_json(
            request.model_dump(mode="json", exclude={"authority", "authority_expires_at"})
        )
    ).hexdigest()
    if request.purpose == "EXECUTION":
        previous = await db.scalar(
            select(StockSourceFence)
            .where(
                StockSourceFence.company_id == request.company_id,
                StockSourceFence.execution_id == request.execution_id,
            )
            .with_for_update()
        )
        if previous:
            if (
                previous.request_hash != digest
                or previous.actor_user_id != actor.user_id
                or previous.closed_at is not None
                or previous.expires_at <= utcnow()
            ):
                raise ConflictError(
                    "stock source lease differs or expired; reconcile the original execution"
                )
            return StockFenceFacts.model_validate(previous.facts)
        live = list(
            await db.scalars(
                select(StockSourceFence.id)
                .where(
                    StockSourceFence.company_id == request.company_id,
                    StockSourceFence.closed_at.is_(None),
                    StockSourceFence.expires_at > utcnow(),
                )
                .limit(8)
            )
        )
        if len(live) >= 8:
            raise IdentitySourceUnavailableError(
                "company stock source leases are busy; retry this execution"
            )
    facts = await build(db, actor, request, state.generation)
    if request.purpose == "EXECUTION":
        # Concurrent owner leases are safe: each names the same generation and all
        # Catalog definition writes wait until every bounded lease is closed.
        row = StockSourceFence(
            id=facts.fence_id,
            tenant_id=request.tenant_id,
            company_id=request.company_id,
            execution_id=request.execution_id,
            actor_user_id=actor.user_id,
            request_hash=digest,
            expires_at=facts.expires_at,
            closed_at=None,
            facts=facts.model_dump(mode="json"),
            created_by=actor.user_id,
            updated_by=actor.user_id,
        )
        db.add(row)
        fence_audit(db, row, "acquire")
        await db.flush()
    return facts

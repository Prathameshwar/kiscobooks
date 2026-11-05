"""Explicit bulk adapters call the ordinary authorized Catalog command handlers."""

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily, ProductTypeRevision, Warehouse
from catalog.models import configuration as cm
from catalog.models import pricing as pm
from catalog.models import tax as tm
from catalog.models import warehouse_policies as wpm
from catalog.models import warehouses as whm
from catalog.schemas import classification as cs
from catalog.schemas import commercial as ms
from catalog.schemas import configuration as cfg
from catalog.schemas import pricing as ps
from catalog.schemas import product_authoring as pa
from catalog.schemas import products as products_schema
from catalog.schemas import tax as ts
from catalog.schemas import tax_governance as tg
from catalog.schemas import units as us
from catalog.schemas import warehouse_groups as wgs
from catalog.schemas import warehouse_policies as wps
from catalog.schemas import warehouses as whs
from catalog.schemas.activation import ActivationCommit
from catalog.schemas.simple_products import SimpleProductCreate, SimpleProductPatch
from catalog.tasks import (
    activation,
    classification,
    commercial,
    commercial_history,
    configuration,
    pricing_commands,
    pricing_foundation,
    pricing_publication,
    pricing_references,
    product_adoption,
    product_attributes,
    product_classification,
    product_commands,
    product_units,
    products,
    tax_commands,
    tax_governance,
    unit_masters,
    unit_relations,
    warehouse_groups,
    warehouse_operations,
    warehouse_policies,
    warehouses,
)
from catalog.tasks.bulk_prices import PriceAdjustment, adjust
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import MANAGE_PERMISSIONS
from catalog.tasks.product_requirements import product_work


@dataclass
class Runtime:
    db: AsyncSession
    factory: async_sessionmaker[AsyncSession]
    actor: Actor
    company: uuid.UUID
    secret: bytes


Call = Callable[[Runtime, Any, uuid.UUID | None, str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Operation:
    model: type[Any]
    action: str
    schema: type[BaseModel]
    call: Call
    requires_target: bool
    permissions: frozenset[str]
    command_count: int = 1


OPERATIONS: dict[tuple[str, str], Operation] = {}
_model: type[Any]
_handler: Any  # Heterogeneous native handlers are paired with their Pydantic schema below.


def register(
    model: type[Any],
    action: str,
    schema: type[BaseModel],
    call: Call,
    *,
    requires_target: bool = False,
    permission: str | None = None,
    extra: tuple[str, ...] = (),
) -> None:
    key = model.__tablename__, action
    if key in OPERATIONS:
        raise RuntimeError("duplicate bulk operation")
    OPERATIONS[key] = Operation(
        model,
        action,
        schema,
        call,
        requires_target,
        frozenset((permission or MANAGE_PERMISSIONS["catalog." + model.__tablename__], *extra)),
    )


def master_call(
    spec: Any, action: Literal["create", "update", "activate", "deactivate"], *, unit: bool = False
) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        handler = unit_masters.command if unit else classification.command
        result = await handler(
            runtime.factory,
            runtime.actor,
            runtime.company,
            spec,
            key=key,
            body=body,
            action=action,
            object_id=target,
        )
        return result.value.model_dump(mode="json", exclude_unset=True)

    return call


for _spec, _update, _unit in (
    (unit_masters.UNIT, us.UnitUpdate, True),
    (unit_masters.PACK, us.PackTypeUpdate, True),
    (classification.GROUP, cs.GroupUpdate, False),
    (classification.SCHEME, cs.SchemeUpdate, False),
    (classification.CATEGORY, cs.CategoryUpdate, False),
    (commercial.BRAND, ms.BrandUpdate, False),
    (commercial.MANUFACTURER, ms.ManufacturerUpdate, False),
    (commercial.BRAND_SERIES, ms.BrandSeriesUpdate, False),
    (commercial.MANUFACTURER_SITE, ms.ManufacturerSiteUpdate, False),
    (commercial.PRODUCT_TYPE, ms.ProductTypeUpdate, False),
    (warehouse_groups.WAREHOUSE_GROUP, wgs.WarehouseGroupUpdate, False),
    (warehouse_groups.WAREHOUSE_BIN, wgs.BinUpdate, False),
):
    for _action, _schema in (
        ("CREATE", _spec.create),
        ("UPDATE", _update),
        ("ACTIVATE", us.ExpectedVersion),
        ("DEACTIVATE", us.ExpectedVersion),
    ):
        _native_action: Any = _action.lower()  # Closed registration tuple, never request text.
        register(
            _spec.model,
            _action,
            _schema,
            master_call(_spec, _native_action, unit=_unit),
            requires_target=_action != "CREATE",
        )


#: What one family hands the shared command framework: which models a receipt may resolve its
#: row against, which work type validates the write, and the key a publication costs on top of
#: manage. Stated per family rather than defaulted — a wrong default here would authorize a
#: publish with another area's key, which no test of that area would notice.
TAX_OPTIONS: dict[str, Any] = {
    "models": tm.TAX_MODELS,
    "work_type": tax_commands.TaxWork,
    "publish_permission": "tax_rule.publish",
}


def pricing_call(
    model: type[Any], handler: Any, action: str, *, options: Mapping[str, Any] | None = None
) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await pricing_commands.command(
            runtime.factory,
            runtime.actor,
            runtime.company,
            model,
            body,
            key,
            handler,
            object_id=target,
            action=action,
            **(options or {}),
        )
        return result.value.model_dump(mode="json")

    return call


for _model, _schema, _handler, _action, _target in (
    (pm.PriceLevel, ps.BootstrapInput, pricing_foundation.bootstrap, "BOOTSTRAP", False),
    (pm.PriceLevel, ps.LevelCreate, pricing_foundation.create_level, "CREATE", False),
    (pm.PriceLevel, ps.LevelPatch, pricing_foundation.update_level, "UPDATE", True),
    (pm.PricePlan, ps.PlanCreate, pricing_foundation.create_plan, "CREATE", False),
    (pm.PricePlan, ps.PlanPatch, pricing_foundation.update_plan, "UPDATE", True),
    (pm.CompanyPricingPolicy, ps.PolicyInput, pricing_foundation.create_policy, "CREATE", False),
    (pm.ItemPriceScope, ps.ScopeInput, pricing_foundation.create_scope, "CREATE", False),
    (
        pm.ItemPriceNumericRevision,
        ps.NumericInput,
        pricing_foundation.create_numeric,
        "CREATE",
        False,
    ),
    (pm.ItemPriceSeries, ps.SeriesInput, pricing_foundation.create_series, "CREATE", False),
    (pm.ItemPriceDraft, ps.DraftInput, pricing_publication.save_draft, "CREATE", False),
    (pm.ItemPriceDraft, ps.DraftReplace, pricing_publication.save_draft, "UPDATE", True),
    (pm.ItemPriceDraft, ps.PublishInput, pricing_publication.publish, "PUBLISH", True),
    (pm.ItemReferenceCost, ps.CostInput, pricing_references.create_cost, "CREATE", False),
    (pm.ItemMrp, ps.MrpInput, pricing_references.create_mrp, "CREATE", False),
    (pm.CommercialGuardRule, ps.GuardInput, pricing_references.create_guard, "CREATE", False),
    (
        pm.CommercialPolicyScope,
        ps.CommercialScopeInput,
        pricing_references.create_commercial_scope,
        "CREATE",
        False,
    ),
    (pm.DiscountCeiling, ps.DiscountInput, pricing_references.create_discount, "CREATE", False),
    (
        pm.ItemCommercialPolicy,
        ps.CommercialInput,
        pricing_references.create_commercial,
        "CREATE",
        False,
    ),
):
    register(
        _model,
        _action,
        _schema,
        pricing_call(_model, _handler, "create" if _action == "BOOTSTRAP" else _action.lower()),
        requires_target=_target,
        extra=("price_plan.publish",) if issubclass(_schema, ps.PublicationInput) else (),
    )

for _model, _schema, _handler, _action, _target in (
    (
        tm.TaxClassification,
        ts.ClassificationInput,
        tax_commands.create_classification,
        "CREATE",
        False,
    ),
    (tm.TaxCategory, ts.CategoryInput, tax_commands.create_category, "CREATE", False),
    (
        tm.TaxRuleApplicability,
        ts.ApplicabilityInput,
        tax_commands.create_applicability,
        "CREATE",
        False,
    ),
    (tm.TaxHistoryAction, tg.WithdrawalInput, tax_governance.withdraw, "PUBLISH", False),
    (tm.TaxCategory, ts.MasterPatch, tax_commands.patch_category, "UPDATE", True),
    (tm.TaxRule, ts.RuleInput, tax_commands.create_rule, "CREATE", False),
    (tm.TaxRule, ts.RulePatch, tax_commands.patch_rule, "UPDATE", True),
    (tm.TaxRateSeries, ts.SeriesInput, tax_commands.create_series, "CREATE", False),
    (tm.TaxRate, ts.RateInput, tax_commands.publish_rate, "PUBLISH", False),
    (tm.CatalogTaxScope, ts.ScopeInput, tax_commands.create_scope, "CREATE", False),
    (tm.CatalogTaxBinding, ts.BindingInput, tax_commands.publish_binding, "PUBLISH", False),
):
    register(
        _model,
        _action,
        _schema,
        pricing_call(_model, _handler, _action.lower(), options=TAX_OPTIONS),
        requires_target=_target,
        extra=("tax_rule.publish",)
        if _action == "PUBLISH" or issubclass(_schema, ps.PublicationInput)
        else (),
    )


async def configuration_call(
    runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
) -> dict[str, Any]:
    result = await configuration.command(
        runtime.factory, runtime.actor, runtime.company, body, key, object_id=target
    )
    return result.value.model_dump(mode="json", exclude_unset=True)


for _model, _action, _schema, _target in (
    (cm.ProductConfigurationScope, "CREATE", cfg.ScopeCreate, False),
    (cm.ProductConfigurationDraft, "CREATE", cfg.DraftInput, False),
    (cm.ProductConfigurationDraft, "UPDATE", cfg.DraftPatch, True),
    (cm.ProductConfigurationDraft, "PUBLISH", cfg.PublishInput, True),
):
    register(
        _model,
        _action,
        _schema,
        configuration_call,
        requires_target=_target,
        extra=("product_configuration.publish",) if _action == "PUBLISH" else (),
    )


def product_call(*, item: bool = False) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await products.command(
            runtime.factory, runtime.actor, runtime.company, body, key, object_id=target, item=item
        )
        return result.value.model_dump(mode="json", exclude_unset=True)

    return call


register(
    ProductFamily, "CREATE", products_schema.FamilyCreate, product_call(), permission="item.create"
)
register(ProductFamily, "UPDATE", products_schema.FamilyPatch, product_call(), requires_target=True)
register(Item, "UPDATE", products_schema.ItemPatch, product_call(item=True), requires_target=True)


async def simple_product_call(
    runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
) -> dict[str, Any]:
    result = await products.command(
        runtime.factory,
        runtime.actor,
        runtime.company,
        body,
        key,
        object_id=target,
        secret=runtime.secret,
    )
    return result.value.model_dump(mode="json", exclude_unset=True)


for _action, _simple_schema, _target in (
    ("CREATE", SimpleProductCreate, False),
    ("UPDATE", SimpleProductPatch, True),
):
    OPERATIONS["simple_product", _action] = Operation(
        Item,
        _action,
        _simple_schema,
        simple_product_call,
        _target,
        frozenset({"item.update" if _target else "item.create"}),
    )


def authoring_call(action: str, handler: Any, *, item: bool) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        assert target is not None

        async def invoke(work: product_commands.ProductWork, incoming: Any) -> None:
            if action == "assign_categories":
                await product_classification.assign_categories(work, incoming, runtime.secret)
            else:
                await handler(work, incoming)

        result = await product_commands.execute(
            runtime.factory,
            runtime.actor,
            runtime.company,
            target,
            body,
            key,
            action,
            invoke,
            item=item,
        )
        return result.value.model_dump(mode="json")

    return call


for _item, _action, _schema, _handler in (
    (False, "ASSIGN_GROUP", pa.GroupAssignmentInput, product_classification.assign_group),
    (
        False,
        "ASSIGN_CATEGORIES",
        pa.CategoryAssignmentInput,
        product_classification.assign_categories,
    ),
    (
        False,
        "ASSIGN_MANUFACTURER",
        pa.ManufacturerAssignmentInput,
        product_classification.assign_manufacturer,
    ),
    (False, "CONFIGURE_ATTRIBUTES", pa.FamilyAttributesInput, product_attributes.configure_family),
    (False, "CREATE_VARIANT", pa.VariantInput, product_attributes.create_variant),
    (True, "ASSIGN_ATTRIBUTES", pa.AttributeAssignmentInput, product_attributes.assign_values),
    (True, "BIND_UNIT", pa.UnitBindingInput, product_units.bind_unit),
    (True, "REVISE_UNIT", pa.UnitRevisionInput, product_units.bind_unit),
    (True, "CREATE_BARCODE", pa.BarcodeInput, product_units.add_barcode),
    (True, "BARCODE_STATE", pa.BarcodeStateInput, product_units.barcode_state),
):
    register(
        Item if _item else ProductFamily,
        _action,
        _schema,
        authoring_call(_action.lower(), _handler, item=_item),
        requires_target=True,
    )


class ReviewedProductInput(us.ExpectedVersion):
    as_of: dt.date


def reviewed_product_call(*, activate: bool, reuse_locked_review: bool = False) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        assert target is not None
        prepared = None
        if reuse_locked_review:
            from billing_platform.command_transaction import participating_session

            from catalog.tasks.policy_state import policy_state

            participant = participating_session(
                runtime.factory, runtime.actor.tenant_id, runtime.company, runtime.actor.user_id
            )
            if not activate or participant is not runtime.db:
                raise RuntimeError("activation review reuse requires the same command transaction")
            # No company mutation may interleave between this review and activation.
            await policy_state(runtime.db, runtime.actor, runtime.company, lock=True)
        work = await product_work(runtime.db, runtime.actor, runtime.company, target)
        if work.item is None or work.item.row_version != body.expected_version:
            raise ConflictError("product changed; review bulk job again")
        if activate:
            prepared = await activation.prepare(work, body.as_of, runtime.secret)
            preview, _ = prepared
            native: Any = ActivationCommit(
                expected_version=body.expected_version,
                as_of=body.as_of,
                expected_family_version=preview.expected_family_version,
                preview_token=preview.preview_token,
            )
        else:
            adoption, _ = await product_adoption.prepare(work, body.as_of, runtime.secret)
            native = pa.AdoptionCommit(
                expected_version=body.expected_version,
                as_of=body.as_of,
                preview_token=adoption.preview_token,
            )

        async def apply(current: product_commands.ProductWork, incoming: Any) -> None:
            if activate:
                await activation.activate(
                    current,
                    incoming,
                    runtime.secret,
                    prepared=prepared if reuse_locked_review else None,
                )
            else:
                await product_adoption.adopt(current, incoming, runtime.secret)

        result = await product_commands.execute(
            runtime.factory,
            runtime.actor,
            runtime.company,
            target,
            native,
            key,
            "activate" if activate else "adopt_configuration",
            apply,
            item=True,
        )
        return result.value.model_dump(mode="json")

    return call


register(
    Item,
    "ACTIVATE",
    ReviewedProductInput,
    reviewed_product_call(activate=True),
    requires_target=True,
    extra=("item.activate", "product_configuration.adopt"),
)
register(
    Item,
    "ADOPT_CONFIGURATION",
    ReviewedProductInput,
    reviewed_product_call(activate=False),
    requires_target=True,
    extra=("product_configuration.adopt",),
)


def operation(resource: str, action: str) -> Operation:
    try:
        return OPERATIONS[resource, action]
    except KeyError as exc:
        raise ValidationFailedError(
            "resource or action is not available for Catalog bulk work"
        ) from exc


async def tax_release_call(
    runtime: Runtime, body: tg.ReleaseInput, target: uuid.UUID | None, key: str
) -> dict[str, Any]:
    preview = await tax_governance.preview(
        ConfigurationAccess(runtime.db, runtime.actor, runtime.company), body, runtime.secret
    )
    native = tg.ReleaseCommit(**body.model_dump(), preview_token=preview.preview_token)

    async def handler(
        work: pricing_commands.PricingWork, incoming: tg.ReleaseCommit, object_id: uuid.UUID | None
    ) -> Any:
        return await tax_governance.publish(work, incoming, runtime.secret)

    return await pricing_call(tm.TaxRelease, handler, "publish", options=TAX_OPTIONS)(
        runtime, native, None, key
    )


register(tm.TaxRelease, "PUBLISH", tg.ReleaseInput, tax_release_call, extra=("tax_rule.publish",))


OPERATIONS["item_price", "ADJUST"] = Operation(
    pm.ItemPrice,
    "ADJUST",
    PriceAdjustment,
    adjust,
    True,
    frozenset({"price_plan.manage", "price_plan.publish"}),
    2,
)


def relation_call(spec: unit_relations.Relation) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await unit_relations.relation_command(
            runtime.factory, runtime.actor, runtime.company, spec, body, key, object_id=target
        )
        return result.value.model_dump(mode="json", exclude_unset=True)

    return call


register(
    unit_relations.CONVERSION.model,
    "CREATE",
    us.UnitConversionInput,
    relation_call(unit_relations.CONVERSION),
)
register(
    unit_relations.TAX_CODE.model,
    "CREATE",
    us.UnitTaxCodeInput,
    relation_call(unit_relations.TAX_CODE),
)
register(
    unit_relations.TAX_CODE.model,
    "CLOSE",
    us.UnitTaxCodeClose,
    relation_call(unit_relations.TAX_CODE),
    requires_target=True,
)


def dated_call(spec: classification.Classification, action: Literal["move", "assign"]) -> Call:
    """A master's dated relation: reparenting a hierarchy, or a location's primary group.

    Both append an interval and close the one in force rather than rewriting it, and both carry
    the relation's own permission on top of the master's — which is why they are one adapter and
    not part of the lifecycle loop above.
    """

    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        result = await classification.command(
            runtime.factory,
            runtime.actor,
            runtime.company,
            spec,
            key=key,
            body=body,
            action=action,
            object_id=target,
        )
        return result.value.model_dump(mode="json", exclude_unset=True)

    return call


register(
    classification.GROUP.model,
    "MOVE",
    cs.GroupReparent,
    dated_call(classification.GROUP, "move"),
    requires_target=True,
    extra=("item_group.move",),
)
register(
    classification.CATEGORY.model,
    "MOVE",
    cs.CategoryReparent,
    dated_call(classification.CATEGORY, "move"),
    requires_target=True,
)


class TypeRevisionCreate(ms.TypeRevisionInput):
    product_type_id: uuid.UUID


def type_revision_call(action: Literal["create", "update", "publish"]) -> Call:
    async def call(
        runtime: Runtime, body: Any, target: uuid.UUID | None, key: str
    ) -> dict[str, Any]:
        parent = body.product_type_id if isinstance(body, TypeRevisionCreate) else None
        if target is not None:
            revision = await company_object(
                runtime.db, ProductTypeRevision, target, company_id=runtime.company
            )
            parent = revision.product_type_id
        native_body = (
            ms.TypeRevisionInput.model_validate(body.model_dump(exclude={"product_type_id"}))
            if isinstance(body, TypeRevisionCreate)
            else body
        )
        result = await commercial_history.command(
            runtime.factory,
            runtime.actor,
            runtime.company,
            commercial_history.REVISION,
            key=key,
            body=native_body,
            action=action,
            object_id=target,
            parent_id=parent,
        )
        return result.value.model_dump(mode="json", exclude_unset=True)

    return call


register(
    commercial_history.REVISION.model, "CREATE", TypeRevisionCreate, type_revision_call("create")
)
register(
    commercial_history.REVISION.model,
    "UPDATE",
    ms.TypeRevisionUpdate,
    type_revision_call("update"),
    requires_target=True,
)
register(
    commercial_history.REVISION.model,
    "PUBLISH",
    us.ExpectedVersion,
    type_revision_call("publish"),
    requires_target=True,
    permission="product_type.publish",
)


#: Stock-location definitions (docs/catalog-warehouses.md, docs/catalog-warehouse-plan.md C10.09).
#: Every one of these is the *same* native command the route calls, so a file cannot reach a rule
#: a request cannot: the location mode gate, the reserved built-in rows, the narrowing-only
#: composition and the eight typed operation flags all hold identically here.
#:
#: Two things are deliberately absent, and their absence is the refusal:
#:
#: * **Retiring a location.** `warehouse.DEACTIVATE` is not registered. Retirement runs a
#:   coordinated fence — Catalog's own dependency checks, then a trusted consumer's clearance
#:   against the release in force (§5) — whose "no consumer has answered yet" outcome is a 503
#:   that no bulk record error code can state honestly. A file of retirements is exactly the
#:   casual bulk action the fence exists to prevent, so it stays one reviewed call per location.
#: * **The company configuration singleton.** Provisioning is derived and its four activity
#:   defaults are one reviewed company-wide action; there is no file of one row to import.
#:
#: Anything Billing owns — a balance, a count, a transfer, a lot or serial, a party — has no
#: resource here at all, so naming one is refused by `operation()` at validation rather than
#: dropped at commit (C7.11, CLAUDE.md §6.14).
LOCATION_OPTIONS: dict[str, Any] = {
    "models": warehouse_operations.POLICY_MODELS,
    "work_type": warehouse_operations.WarehouseWork,
    "publish_permission": "warehouse.publish",
}
ITEM_LOCATION_OPTIONS: dict[str, Any] = {
    "models": warehouse_policies.POLICY_MODELS,
    "work_type": warehouse_policies.ItemPolicyWork,
    # The manage key, not a publish key: nothing here posts or numbers anything, and the
    # location's own reviewed policy stays the ceiling (`api/warehouse_policies.py`).
    "publish_permission": "item_warehouse_policy.manage",
}
REPLENISHMENT_OPTIONS: dict[str, Any] = {
    **ITEM_LOCATION_OPTIONS,
    "work_type": warehouse_policies.ItemReplenishmentWork,
}

for _action, _schema in (
    ("CREATE", whs.WarehouseCreate),
    ("UPDATE", whs.WarehouseUpdate),
    ("ACTIVATE", us.ExpectedVersion),
):
    _native_action = _action.lower()
    register(
        Warehouse,
        _action,
        _schema,
        master_call(warehouses.WAREHOUSE, _native_action),
        requires_target=_action != "CREATE",
    )

register(
    warehouse_groups.WAREHOUSE_GROUP.model,
    "MOVE",
    wgs.WarehouseGroupReparent,
    dated_call(warehouse_groups.WAREHOUSE_GROUP, "move"),
    requires_target=True,
    extra=("warehouse_group.move",),
)
#: A location's dated primary group. It grants nothing: a group confers no access to its member
#: stores, so this needs authority over the location *and* over the grouping, and neither is
#: implied by the other (docs/catalog-warehouses.md §3).
register(
    Warehouse,
    "ASSIGN",
    wgs.PrimaryGroupInput,
    dated_call(warehouses.WAREHOUSE, "assign"),
    requires_target=True,
    extra=("warehouse_group.manage",),
)
#: The location is the target and the revision is what gets written, so the row addresses the
#: store by its own exact code or id while the command's model — and therefore its audit entity
#: and manage key — remains the revision's.
register(
    Warehouse,
    "PUBLISH_OPERATION_POLICY",
    whs.OperationPolicyInput,
    pricing_call(
        whm.WarehouseOperationPolicyRevision,
        warehouse_operations.publish_policy,
        "publish",
        options=LOCATION_OPTIONS,
    ),
    requires_target=True,
    extra=("warehouse.publish",),
)
#: Addressed by SKU, which is what a spreadsheet of stocking rules actually holds. Both state
#: the product's policy whole, exactly as the PUT does: an omitted location is dropped and an
#: omitted band retired, so a partial file cannot leave half a reviewed policy standing.
register(
    Item,
    "SET_WAREHOUSE_POLICY",
    wps.ItemWarehousePolicyInput,
    pricing_call(
        wpm.ItemWarehousePolicy,
        warehouse_policies.set_policy,
        "update",
        options=ITEM_LOCATION_OPTIONS,
    ),
    requires_target=True,
    permission="item_warehouse_policy.manage",
)
register(
    Item,
    "SET_REPLENISHMENT_POLICY",
    wps.ItemReplenishmentPolicyInput,
    pricing_call(
        wpm.ItemReplenishmentPolicy,
        warehouse_policies.set_replenishment,
        "update",
        options=REPLENISHMENT_OPTIONS,
    ),
    requires_target=True,
    permission="item_warehouse_policy.manage",
)

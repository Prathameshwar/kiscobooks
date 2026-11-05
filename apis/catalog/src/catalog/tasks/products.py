"""Draft family/SKU aggregate commands using existing authority, custom fields and receipts."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.products import validate_structure
from catalog.domain.units import QuantityRule
from catalog.models.classification import CatalogPolicyState
from catalog.models.commercial import Brand, BrandSeries, ProductType, ProductTypeRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.units import UnitOfMeasure
from catalog.schemas.products import (
    FamilyCreate,
    FamilyDetail,
    FamilyListItem,
    FamilyPatch,
    FamilyQuery,
    ItemDetail,
    ItemListItem,
    ItemPatch,
    ItemQuery,
    ProductCreated,
)
from catalog.schemas.simple_products import SimpleProductCreate, SimpleProductPatch
from catalog.tasks.classification import audit_change, validate_custom
from catalog.tasks.custom_fields import reserve_claims
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.field_indexes import apply_custom_filters, index_values
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state

ProductRow = ProductFamily | Item

if TYPE_CHECKING:
    from catalog.schemas.advanced_product_creation import AdvancedDefinitionCreate


def native(row: ProductRow, context: FieldContext) -> dict[str, Any]:
    return {
        **{key: getattr(row, key) for key in context.native.fields},
        **{"custom_field:" + key: value for key, value in (row.custom_fields or {}).items()},
    }


def detail(row: ProductRow, context: FieldContext, generation: int) -> BaseModel:
    values = native(row, context)
    readable = context.readable(values)
    schema = FamilyDetail if isinstance(row, ProductFamily) else ItemDetail
    return schema.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "policy_generation": generation,
            **{
                key: value
                for key, value in values.items()
                if key in readable and not key.startswith("custom_field:")
            },
            "custom_fields": {
                key: value
                for key, value in (row.custom_fields or {}).items()
                if "custom_field:" + key in readable
            },
        }
    )


def require_fields(context: FieldContext, fields: set[str]) -> None:
    if not fields <= context.readable():
        raise PermissionDeniedError("product validation requires readable structural fields")


async def references(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    family: ProductFamily,
    item: Item | None = None,
) -> None:
    type_context = await load_field_context(db, actor, company, "catalog.product_type_revision")
    require_fields(type_context, {"published_at", "kind", "unit_dimensions", "product_type_id"})
    revision = await company_object(
        db, ProductTypeRevision, family.product_type_revision_id, company_id=company
    )
    owner_context = await load_field_context(db, actor, company, "catalog.product_type")
    require_fields(owner_context, {"is_active"})
    owner = await company_object(db, ProductType, revision.product_type_id, company_id=company)
    if revision.published_at is None or not owner.is_active:
        raise ConflictError("products require an active type with a published revision")
    if revision.kind not in {family.kind, "BOTH"}:
        raise ConflictError("product kind does not match its type revision")
    if family.series_id is not None and family.brand_id is None:
        raise ConflictError("series requires its brand")
    if family.brand_id is not None:
        brand_context = await load_field_context(db, actor, company, "catalog.brand")
        require_fields(brand_context, {"is_active"})
        brand = await company_object(db, Brand, family.brand_id, company_id=company)
        if not brand.is_active:
            raise ConflictError("product brand is inactive")
    if family.series_id is not None:
        series_context = await load_field_context(db, actor, company, "catalog.brand_series")
        require_fields(series_context, {"is_active", "brand_id"})
        series = await company_object(db, BrandSeries, family.series_id, company_id=company)
        if series.brand_id != family.brand_id:
            raise PermissionDeniedError("series belongs to another brand")
        if not series.is_active:
            raise ConflictError("product series is inactive")
    if item is not None:
        unit_context = await load_field_context(db, actor, company, "catalog.unit_of_measure")
        require_fields(
            unit_context, {"is_active", "dimension", "decimal_places", "quantity_increment"}
        )
        unit = await company_object(db, UnitOfMeasure, item.base_unit_id, company_id=company)
        if not unit.is_active:
            raise ConflictError("product base unit is inactive")
        validate_structure(
            kind=family.kind,
            type_kind=revision.kind,
            dimension=unit.dimension,
            allowed_dimensions=tuple(revision.unit_dimensions),
            quantity=QuantityRule(unit.decimal_places, unit.quantity_increment),
            minimum_sale=item.min_sale_quantity,
        )
        if item.min_sale_quantity is not None:
            from catalog.tasks.configuration_access import ConfigurationAccess
            from catalog.tasks.product_unit_rules import validate_minimum_quantity

            await validate_minimum_quantity(
                ConfigurationAccess(db, actor, company), item.id, item.min_sale_quantity
            )


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID, *, item: bool
) -> BaseModel:
    entity = "catalog.item" if item else "catalog.product_family"
    context = await load_field_context(db, actor, company, entity)
    row = await company_object(db, Item if item else ProductFamily, object_id, company_id=company)
    assert isinstance(row, ProductFamily | Item)
    state = await policy_state(db, actor, company)
    return detail(row, context, state.generation if state else 1)


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: FamilyCreate | FamilyPatch | ItemPatch | SimpleProductCreate | SimpleProductPatch,
    key: str,
    *,
    object_id: uuid.UUID | None = None,
    item: bool = False,
    secret: bytes | None = None,
    advanced_definition: AdvancedDefinitionCreate | None = None,
) -> CommandResult[BaseModel]:
    if advanced_definition is not None and not isinstance(body, FamilyCreate):
        raise ValueError("advanced definitions require a family create command")
    public_create = isinstance(body, SimpleProductCreate)
    public_patch = isinstance(body, SimpleProductPatch)
    public_body = body
    creating = isinstance(body, FamilyCreate | SimpleProductCreate)
    if public_patch:
        item = True
    entity = "catalog.item" if item else "catalog.product_family"
    action = "create" if creating else "update"
    contexts: dict[str, FieldContext] = {}
    checks: dict[str, FieldWriteChecks] = {}
    state: CatalogPolicyState | None = None
    identity_prefix = (
        "advanced_" if advanced_definition else "simple_" if public_create or public_patch else ""
    )
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        entity + "." + identity_prefix + action,
        key,
        {
            "body": (advanced_definition or body).model_dump(mode="json", exclude_unset=True),
            "id": str(object_id) if object_id else None,
        },
    )
    if isinstance(body, SimpleProductCreate):
        from catalog.tasks.simple_products import create_input

        body = create_input(body)

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal state
        actor.require_scope("item.read", target=ScopePath(company_id=company))
        if isinstance(body, FamilyCreate) and body.initial_setup is not None:
            actor.require_scope("item.update", target=ScopePath(company_id=company))
            setup = body.initial_setup
            if setup.tax is not None:
                actor.require_scope("tax_rule.manage", target=ScopePath(company_id=company))
                actor.require_scope("tax_rule.publish", target=ScopePath(company_id=company))
            if setup.prices:
                from catalog.models.pricing import PricePlan
                from catalog.tasks.configuration_access import ConfigurationAccess
                from catalog.tasks.pricing_commands import purpose_access, row

                actor.require_scope("price_plan.manage", target=ScopePath(company_id=company))
                access = ConfigurationAccess(db, actor, company)
                for price in setup.prices:
                    await purpose_access(
                        access, await row(access, PricePlan, price.plan_id), write=True
                    )
        for name in (
            {"catalog.product_family", "catalog.item"} if creating or public_patch else {entity}
        ):
            contexts[name] = await load_field_context(
                db, actor, company, name, permission="item." + action
            )
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for name, changed in receipt["changed"].items():
                if name not in contexts:
                    contexts[name] = await load_field_context(db, actor, company, name)
                if name in checks and checks[name].writes:
                    checks[name].recheck(contexts[name])
                else:
                    assert_fields_writable(
                        frozenset(changed),
                        rules=contexts[name].rules(),
                        target=ScopePath(company_id=company),
                    )
            await company_object(
                db, Item if item else ProductFamily, uuid.UUID(receipt["id"]), company_id=company
            )

    async def store(
        db: AsyncSession,
        row: ProductRow,
        context: FieldContext,
        before: dict[str, Any],
        incoming_custom: Mapping[str, Any],
        previous_custom: Mapping[str, Any],
    ) -> frozenset[str]:
        after = native(row, context)
        row.custom_fields = await validate_custom(
            db,
            actor,
            company,
            context,
            incoming_custom,
            before,
            after,
            previous_custom,
            creating=creating,
        )
        after = native(row, context)
        changed = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        ) - {"row_version"}
        if changed and not creating:
            if row.row_version >= 2**31 - 1:
                raise ConflictError("product version is exhausted")
            row.row_version += 1
            row.updated_at, row.updated_by = utcnow(), actor.user_id
            after["row_version"] = row.row_version
        checked = checks.setdefault(context.native.entity_type, FieldWriteChecks())
        context.assert_writable(changed, before=before, after=after, checked=checked)
        return changed

    async def persist(
        db: AsyncSession,
        row: ProductRow,
        context: FieldContext,
        changed: frozenset[str],
        before: Mapping[str, Any] | None = None,
    ) -> None:
        await reserve_claims(
            db,
            company_id=company,
            entity_type=context.native.entity_type,
            entity_id=row.id,
            definitions=context.definitions,
            values=row.custom_fields or {},
        )
        await index_values(db, context, row.id, row.custom_fields or {})
        if changed:
            audit_change(
                db,
                actor,
                company,
                context.native.entity_type,
                row.id,
                action,
                changed,
                before=before,
                after=native(row, context),
            )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        from catalog.tasks.product_creation_review import reviewed_source

        if advanced_definition is not None:
            from catalog.schemas.configuration import EffectiveQuery
            from catalog.tasks.configuration_resolution import resolve
            from catalog.tasks.pricing_commands import business_date
            from catalog.tasks.product_mode import read as read_mode

            mode = await read_mode(db, actor, company, lock=True)
            if (
                not mode.product_family_sku_enabled
                or mode.row_version != advanced_definition.mode_version
            ):
                raise ConflictError("Product authoring mode changed; review the product again.")
            if state is None or state.generation != advanced_definition.policy_generation:
                raise ConflictError("Company product policy changed; review the product again.")
            if advanced_definition.as_of != business_date(contexts[entity].company.timezone):
                raise ConflictError("Product business date changed; review the product again.")
            effective = await resolve(
                db,
                actor,
                company,
                EffectiveQuery(
                    as_of=advanced_definition.as_of,
                    kind=advanced_definition.profile.kind,
                    product_type_revision_id=advanced_definition.profile.product_type_revision_id,
                    group_id=advanced_definition.group_id,
                ),
            )
            if effective.source_version != advanced_definition.source_version:
                raise ConflictError("Product configuration changed; review the product again.")
        if isinstance(public_body, SimpleProductCreate | SimpleProductPatch):
            from catalog.tasks.product_mode import check_version

            await check_version(db, company, public_body.authoring_version)
        reviewed_source_version = (
            await reviewed_source(db, actor, company, body)
            if isinstance(body, FamilyCreate)
            else None
        )
        assert state is not None
        common = {
            "tenant_id": actor.tenant_id,
            "company_id": company,
            "created_by": actor.user_id,
            "updated_by": actor.user_id,
            "row_version": 1,
            "status": "DRAFT",
        }
        changes: dict[str, list[str]] = {}
        price_draft_ids: list[uuid.UUID] = []
        creation_id: uuid.UUID | None = None
        if isinstance(body, FamilyCreate):
            family_context, item_context = contexts[entity], contexts["catalog.item"]
            incoming = body.model_dump(
                exclude={"default_item", "custom_fields", "accept_defaults", "initial_setup"}
            )
            family = ProductFamily(id=uuid7(), structure_mode="SIMPLE", **common, **incoming)
            sku = Item(
                id=uuid7(),
                family_id=family.id,
                default_slot=1,
                **common,
                **body.default_item.model_dump(exclude={"custom_fields"}),
            )
            # Field denies run before reference validation can reveal hidden values.
            changes[entity] = sorted(
                await store(db, family, family_context, {}, body.custom_fields, {})
            )
            changes["catalog.item"] = sorted(
                await store(db, sku, item_context, {}, body.default_item.custom_fields, {})
            )
            if body.accept_defaults is not None:
                from catalog.schemas.configuration import AuthoringDefaultsQuery
                from catalog.tasks.configuration_access import ConfigurationAccess
                from catalog.tasks.configuration_authoring import accepted

                suggestion = await accepted(
                    ConfigurationAccess(db, actor, company),
                    body.accept_defaults.model_copy(
                        update={"expected_source_version": reviewed_source_version}
                    )
                    if reviewed_source_version is not None
                    else body.accept_defaults,
                    AuthoringDefaultsQuery(as_of=body.accept_defaults.as_of, kind=body.kind),
                )
                if body.product_type_revision_id != suggestion.product_type_revision_id:
                    raise ConflictError("selected product type differs from accepted defaults")
            await references(db, actor, company, family, sku)
            await persist(db, family, family_context, frozenset(changes[entity]))
            await persist(db, sku, item_context, frozenset(changes["catalog.item"]))
            db.add(family)
            await db.flush()
            db.add(sku)
            sku_ids = [sku.id]
            if advanced_definition is not None:
                from catalog.schemas.product_authoring import FamilyAttributesInput, VariantInput
                from catalog.tasks.configuration_access import ConfigurationAccess
                from catalog.tasks.product_attributes import configure_family, create_variant
                from catalog.tasks.product_commands import ProductWork

                await db.flush()
                access = ConfigurationAccess(db, actor, company)
                access.checks = checks
                work = ProductWork(db, actor, company, family, sku, access)
                if advanced_definition.attributes:
                    await configure_family(
                        work,
                        FamilyAttributesInput(
                            expected_version=family.row_version,
                            expected_default_item_version=sku.row_version,
                            attributes=advanced_definition.attributes,
                            default_item_attributes=advanced_definition.skus[0].attributes,
                        ),
                    )
                elif advanced_definition.skus[0].attributes:
                    raise ConflictError("SKU attributes require family declarations")
                for definition in advanced_definition.skus[1:]:
                    await create_variant(
                        work,
                        VariantInput(
                            expected_version=family.row_version,
                            item=definition.item,
                            attributes=definition.attributes,
                        ),
                    )
                    assert work.item is not None
                    sku_ids.append(work.item.id)
                    await db.flush()
                for name, changed in work.changed.items():
                    changes[name] = sorted(set(changes.get(name, [])) | changed)
            if body.initial_setup is not None:
                from catalog.tasks.configuration_access import ConfigurationAccess
                from catalog.tasks.product_commands import ProductWork
                from catalog.tasks.product_initial import apply_initial

                await db.flush()
                access = ConfigurationAccess(db, actor, company)
                access.checks = checks
                work = ProductWork(db, actor, company, family, sku, access)
                runtime_setup = (
                    body.initial_setup.model_copy(
                        update={"expected_source_version": reviewed_source_version}
                    )
                    if reviewed_source_version is not None
                    else body.initial_setup
                )
                price_draft_ids = await apply_initial(work, runtime_setup, state)
                for name, changed in work.changed.items():
                    changes[name] = sorted(set(changes.get(name, [])) | changed)
            from catalog.tasks.configuration_access import ConfigurationAccess
            from catalog.tasks.product_choices import require_assignments
            from catalog.tasks.product_commands import ProductWork

            await db.flush()
            await require_assignments(
                ProductWork(
                    db, actor, company, family, sku, ConfigurationAccess(db, actor, company)
                ),
                {},
                as_of=body.initial_setup.effective_from
                if body.initial_setup
                else (body.accept_defaults.as_of if body.accept_defaults else None),
            )
            result_id = family.id
            child_id = str(sku.id)
            if advanced_definition is not None:
                from catalog.tasks.advanced_product_creation import record_definition

                creation_id = await record_definition(
                    db, actor, company, key, advanced_definition, family.id, sku_ids
                )
        elif isinstance(body, SimpleProductPatch):
            from catalog.tasks.simple_products import (
                assert_simple,
                decode_revision,
                revision_values,
            )

            assert object_id is not None and secret is not None
            item_context, family_context = (
                contexts["catalog.item"],
                contexts["catalog.product_family"],
            )
            require_fields(item_context, {"family_id", "row_version", "status", "default_slot"})
            require_fields(family_context, {"row_version", "status", "structure_mode"})
            sku = await company_object(db, Item, object_id, company_id=company, lock=True)
            family = await company_object(
                db, ProductFamily, sku.family_id, company_id=company, lock=True
            )
            await assert_simple(db, company, sku, family)
            if decode_revision(actor, company, sku.id, secret, body.revision) != revision_values(
                sku, family
            ):
                raise ConflictError("Product changed; reload before editing.")
            values = body.model_dump(exclude_unset=True, exclude={"revision", "authoring_version"})
            descriptive = set(values) <= {
                "name",
                "description",
                "model_code",
                "custom_fields",
                "shared_custom_fields",
            }
            if sku.status != "DRAFT" and not (sku.status == "ACTIVE" and descriptive):
                raise ConflictError("only descriptive fields can change on active products")
            if family.status != "DRAFT" and not (
                family.status == "ACTIVE" and (descriptive or sku.status == "DRAFT")
            ):
                raise ConflictError("product belongs to a non-draft family")
            item_fields = {"code", "name", "sellable", "purchasable", "min_sale_quantity"}
            family_fields = {"name", "description", "model_code", "brand_id", "series_id"}
            pending_writes: list[
                tuple[ProductRow, FieldContext, frozenset[str], Mapping[str, Any]]
            ] = []
            for row, context, fields, custom_key in (
                (family, family_context, family_fields, "shared_custom_fields"),
                (sku, item_context, item_fields, "custom_fields"),
            ):
                before = native(row, context)
                previous_custom = dict(row.custom_fields or {})
                for field in set(values) & fields:
                    setattr(row, "sku" if field == "code" else field, values[field])
                edited_fields = await store(
                    db, row, context, before, values.get(custom_key, {}), previous_custom
                )
                changes[context.native.entity_type] = sorted(edited_fields)
                pending_writes.append((row, context, edited_fields, before))
            # Claims/index maintenance can flush. Check both members' field policies
            # and all scoped references before any aggregate member is persisted.
            if not descriptive:
                await references(db, actor, company, family, sku)
            from catalog.tasks.configuration_access import ConfigurationAccess
            from catalog.tasks.product_choices import require_assignments
            from catalog.tasks.product_commands import ProductWork

            await require_assignments(
                ProductWork(
                    db, actor, company, family, sku, ConfigurationAccess(db, actor, company)
                ),
                pending_writes[0][3],
            )
            for row, context, edited_fields, previous_values in pending_writes:
                await persist(db, row, context, edited_fields, before=previous_values)
            result_id, child_id = sku.id, None
        else:
            assert object_id is not None
            context = contexts[entity]
            descriptive_fields = {"name"} if item else {"name", "description", "model_code"}
            descriptive_only = (
                body.model_fields_set - {"expected_version", "custom_fields"} <= descriptive_fields
            )
            require_fields(
                context,
                {"status", "row_version"}
                | (
                    set()
                    if descriptive_only
                    else {"family_id", "base_unit_id", "min_sale_quantity"}
                    if item
                    else {"kind", "product_type_revision_id", "brand_id", "series_id"}
                ),
            )
            row = await company_object(
                db, Item if item else ProductFamily, object_id, company_id=company, lock=True
            )
            assert isinstance(row, ProductFamily | Item)
            if row.row_version != body.expected_version:
                raise ConflictError("product version changed; reload before updating")
            if row.status != "DRAFT" and not (row.status == "ACTIVE" and descriptive_only):
                raise ConflictError("only descriptive fields can change on active products")
            before = native(row, context)
            previous_custom = dict(row.custom_fields or {})
            incoming = body.model_dump(
                exclude_unset=True, exclude={"expected_version", "custom_fields"}
            )
            for field, value in incoming.items():
                setattr(row, field, value)
            changes[entity] = sorted(
                await store(db, row, context, before, body.custom_fields, previous_custom)
            )
            if isinstance(row, Item):
                family_context = await load_field_context(
                    db, actor, company, "catalog.product_family"
                )
                require_fields(
                    family_context,
                    {"status"}
                    if descriptive_only
                    else {"kind", "product_type_revision_id", "brand_id", "series_id", "status"},
                )
                family = await company_object(db, ProductFamily, row.family_id, company_id=company)
                if family.status != "DRAFT" and not (
                    family.status == "ACTIVE" and (descriptive_only or row.status == "DRAFT")
                ):
                    raise ConflictError("SKU structure belongs to a non-draft family")
                if not descriptive_only:
                    await references(db, actor, company, family, row)
            elif not descriptive_only:
                await references(db, actor, company, row)
            if isinstance(row, ProductFamily):
                from catalog.tasks.configuration_access import ConfigurationAccess
                from catalog.tasks.product_choices import require_assignments
                from catalog.tasks.product_commands import ProductWork

                await require_assignments(
                    ProductWork(
                        db, actor, company, row, None, ConfigurationAccess(db, actor, company)
                    ),
                    before,
                )
            await persist(db, row, context, frozenset(changes[entity]), before=before)
            result_id, child_id = row.id, None
        if any(changes.values()):
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation is exhausted")
            state.generation += 1
        await db.flush()
        return CommandReceipt(
            201 if creating else 200,
            {
                "id": str(result_id),
                "child_id": child_id,
                "changed": changes,
                **({"creation_id": str(creation_id)} if creation_id else {}),
                **({"sku_ids": [str(value) for value in sku_ids]} if creation_id else {}),
                **(
                    {"price_draft_ids": [str(value) for value in price_draft_ids]}
                    if price_draft_ids
                    else {}
                ),
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert state is not None
        if advanced_definition is not None:
            from catalog.models.advanced_product_creation import AdvancedProductCreation
            from catalog.schemas.advanced_product_creation import AdvancedDefinitionResult
            from catalog.tasks.advanced_product_creation import status

            creation = await company_object(
                db, AdvancedProductCreation, uuid.UUID(receipt["creation_id"]), company_id=company
            )
            if creation.owner_user_id != actor.user_id:
                raise PermissionDeniedError("Only the submitting user can read this creation")
            family = await company_object(db, ProductFamily, creation.family_id, company_id=company)
            skus = [
                await company_object(db, Item, uuid.UUID(value), company_id=company)
                for value in creation.sku_ids
            ]
            return AdvancedDefinitionResult(
                creation=status(creation),
                family=FamilyDetail.model_validate(
                    detail(
                        family, contexts["catalog.product_family"], state.generation
                    ).model_dump()
                ),
                skus=[
                    ItemDetail.model_validate(
                        detail(value, contexts["catalog.item"], state.generation).model_dump()
                    )
                    for value in skus
                ],
            )
        if public_create or public_patch:
            from catalog.tasks.simple_products import read as read_product

            assert secret is not None
            return await read_product(
                db,
                actor,
                company,
                uuid.UUID(receipt["child_id"] if public_create else receipt["id"]),
                secret,
                receipt.get("price_draft_ids"),
            )
        row = await company_object(
            db, Item if item else ProductFamily, uuid.UUID(receipt["id"]), company_id=company
        )
        assert isinstance(row, ProductFamily | Item)
        result = detail(row, contexts[entity], state.generation)
        if creating:
            sku = await company_object(db, Item, uuid.UUID(receipt["child_id"]), company_id=company)
            return ProductCreated.model_validate(
                {
                    "family": result,
                    "default_item": detail(sku, contexts["catalog.item"], state.generation),
                    **(
                        {"price_draft_ids": receipt["price_draft_ids"]}
                        if receipt.get("price_draft_ids")
                        else {}
                    ),
                }
            )
        return result

    try:
        return await execute_idempotent(
            factory,
            identity,
            authorize=authorize,
            mutate=mutate,
            render=render,
            timeout_seconds=30 if creating else 10,
        )
    except IntegrityError as exc:
        raise ConflictError("product identity conflicts or its references are invalid") from exc


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: FamilyQuery | ItemQuery,
    secret: bytes,
    *,
    item: bool,
    cursor_resource: str | None = None,
) -> Page[BaseModel]:
    entity = "catalog.item" if item else "catalog.product_family"
    model = Item if item else ProductFamily
    schema = ItemListItem if item else FamilyListItem
    context = await load_field_context(db, actor, company, entity)
    readable = (context.readable() & frozenset(context.native.fields)) | {"id"}
    selected = readable & schema.model_fields.keys()
    stmt = select(*(getattr(model, key) for key in selected)).where(model.company_id == company)
    keys = (
        {"sku", "family_id", "base_unit_id", "status", "sellable", "purchasable"}
        if item
        else {"code", "kind", "status", "product_type_revision_id", "brand_id"}
    )
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=keys),
        filters={key: FilterColumn(key, getattr(model, key)) for key in keys},
        readable=readable,
    )
    code_key = "sku" if item else "code"
    code_column = Item.sku if item else ProductFamily.code
    stmt = apply_search(
        stmt, query.q, columns={code_key: code_column, "name": model.name}, readable=readable
    )
    terms = resolve_sort(
        query.sort,
        default=code_key if code_key in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            code_key: SortColumn(code_column, "text"),
            "name": SortColumn(model.name, "text"),
        },
        readable=readable,
        supported=frozenset(
            (key,) for key in ("id", "-id", code_key, "-" + code_key, "name", "-name")
        ),
    )
    stmt, token = await apply_custom_filters(db, stmt, context, query.predicates())
    codec = cursor_codec(
        secret, actor, company, (cursor_resource or entity) + ":" + token, context, query
    )

    def project(values: Mapping[str, Any]) -> BaseModel:
        return schema.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)

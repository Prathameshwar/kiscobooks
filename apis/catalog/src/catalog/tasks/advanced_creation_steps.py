"""Per-SKU Catalog setup, price publication and activation with durable progress."""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import ItemPriceDraft, ItemPriceNumericRevision, PricePlan
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from catalog.schemas.activation import ActivationCommit
from catalog.schemas.advanced_product_creation import (
    AdvancedDefinitionStatus,
    AdvancedSkuActivate,
    AdvancedSkuPublish,
    AdvancedSkuSetup,
)
from catalog.schemas.configuration import EffectiveQuery
from catalog.schemas.pricing import CostInput, MrpInput, NumericInput, PublishInput
from catalog.tasks import activation, pricing_foundation, pricing_publication, pricing_references
from catalog.tasks.advanced_product_creation import audit, owned, status
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.field_context import load_field_context
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, purpose_access
from catalog.tasks.pricing_commands import row as pricing_row
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_creation_review import configuration_fingerprint
from catalog.tasks.configuration_context import family_group
from catalog.tasks.product_initial import apply_initial

Factory = async_sessionmaker[AsyncSession]
SetupBody = AdvancedSkuSetup | AdvancedSkuPublish | AdvancedSkuActivate
Handler = Callable[
    [AsyncSession, AdvancedProductCreation, CatalogPolicyState],
    Awaitable[dict[str, set[str]]],
]


def sku_progress(row: AdvancedProductCreation, item_id: uuid.UUID) -> dict[str, Any]:
    if str(item_id) not in row.sku_ids:
        raise PermissionDeniedError("SKU does not belong to this product creation")
    return dict(row.progress.get("skus", {}).get(str(item_id), {}))


def save_sku_progress(
    row: AdvancedProductCreation, item_id: uuid.UUID, entry: dict[str, Any]
) -> None:
    progress = dict(row.progress)
    skus = dict(progress.get("skus", {}))
    skus[str(item_id)] = entry
    progress["skus"] = skus
    row.progress = progress


async def native_rows(
    db: AsyncSession,
    row: AdvancedProductCreation,
    company: uuid.UUID,
    item_id: uuid.UUID,
    *,
    lock: bool = True,
) -> tuple[ProductFamily, Item]:
    sku_progress(row, item_id)
    family = await company_object(db, ProductFamily, row.family_id, company_id=company, lock=lock)
    item = await company_object(db, Item, item_id, company_id=company, lock=lock)
    if item.family_id != family.id:
        raise PermissionDeniedError("SKU belongs to another Product Profile")
    return family, item


def expected(row: AdvancedProductCreation, version: int) -> None:
    if row.row_version != version or row.row_version >= 2**31 - 1:
        raise ConflictError("Product creation changed; reload its progress")


async def bump(work: ProductWork, value: ProductFamily | Item) -> None:
    if value.row_version >= 2**31 - 1:
        raise ConflictError("product version is exhausted")
    before = await work.access.values(value)
    value.row_version += 1
    value.updated_at, value.updated_by = utcnow(), work.actor.user_id
    await work.record(value, before, "update")
    await work.db.flush([value])


async def run(
    factory: Factory,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: SetupBody,
    key: str,
    action: str,
    handler: Handler,
) -> CommandResult[AdvancedDefinitionStatus]:
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.advanced_product_creation." + action,
        key,
        {
            "creation_id": str(creation_id),
            "item_id": str(item_id),
            "body": body.model_dump(mode="json", exclude_unset=True),
        },
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        creation = await owned(db, actor, company, creation_id)
        actor.require_scope("item.update", target=ScopePath(company_id=company))
        if action == "activate":
            actor.require_scope("item.activate", target=ScopePath(company_id=company))
        if action == "publish":
            actor.require_scope("price_plan.publish", target=ScopePath(company_id=company))
            actor.require_scope("price_plan.manage", target=ScopePath(company_id=company))
            access = ConfigurationAccess(db, actor, company)
            for raw in sku_progress(creation, item_id).get("price_draft_ids", []):
                await purpose_access(
                    access, await pricing_row(access, ItemPriceDraft, uuid.UUID(raw)), write=True
                )
        if isinstance(body, AdvancedSkuSetup):
            if body.setup.tax is not None:
                for permission in ("tax_rule.manage", "tax_rule.publish"):
                    actor.require_scope(permission, target=ScopePath(company_id=company))
            if body.setup.prices:
                actor.require_scope("price_plan.manage", target=ScopePath(company_id=company))
                access = ConfigurationAccess(db, actor, company)
                for price in body.setup.prices:
                    await purpose_access(
                        access, await pricing_row(access, PricePlan, price.plan_id), write=True
                    )
            if body.purchase_reference is not None:
                actor.require_scope("reference_cost.manage", target=ScopePath(company_id=company))
            if body.purchase_reference is not None or body.mrp is not None:
                actor.require_scope("price_plan.manage", target=ScopePath(company_id=company))
        await load_field_context(db, actor, company, "catalog.item", permission="item.update")
        await load_field_context(db, actor, company, "catalog.product_family")
        if receipt is not None:
            for entity, fields in receipt["changed"].items():
                context = await load_field_context(db, actor, company, entity)
                assert_fields_writable(
                    frozenset(fields),
                    rules=context.rules(),
                    target=ScopePath(company_id=company),
                )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        state = await policy_state(db, actor, company, lock=True)
        assert state is not None
        row = await owned(db, actor, company, creation_id, lock=True)
        changes = await handler(db, row, state)
        if any(changes.values()):
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation is exhausted")
            state.generation += 1
        row.row_version += 1
        row.updated_at, row.updated_by = utcnow(), actor.user_id
        audit(db, row, actor, "update")
        await db.flush()
        return CommandReceipt(
            200,
            {
                "id": str(row.id),
                "changed": {name: sorted(fields) for name, fields in changes.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> AdvancedDefinitionStatus:
        return status(await owned(db, actor, company, uuid.UUID(receipt["id"])))

    try:
        return await execute_idempotent(
            factory,
            identity,
            authorize=authorize,
            mutate=mutate,
            render=render,
            timeout_seconds=30,
        )
    except IntegrityError as exc:
        raise ConflictError("product setup conflicts or its references changed") from exc


async def setup(
    factory: Factory,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuSetup,
    key: str,
) -> CommandResult[AdvancedDefinitionStatus]:
    async def apply(
        db: AsyncSession, row: AdvancedProductCreation, state: CatalogPolicyState
    ) -> dict[str, set[str]]:
        expected(row, body.expected_creation_version)
        entry = sku_progress(row, item_id)
        if entry.get("setup_done"):
            raise ConflictError("SKU setup was already submitted; reload its progress")
        if row.status not in {"DEFINED", "SETUP", "ACTIVATING"}:
            raise ConflictError("product creation has passed setup")
        family, item = await native_rows(db, row, company, item_id)
        if (family.row_version, item.row_version) != (
            body.expected_family_version,
            body.expected_item_version,
        ):
            raise ConflictError("Product Profile or SKU changed; review setup again")
        if item.status != "DRAFT" or family.status not in {"DRAFT", "ACTIVE"}:
            raise ConflictError("only a draft SKU can receive initial setup")
        shared = bool(body.setup.group_id or body.setup.categories or body.setup.manufacturer)
        if shared and str(item_id) != row.sku_ids[0]:
            raise ValidationFailedError("Profile setup belongs to the default SKU")
        access = ConfigurationAccess(db, actor, company)
        work = ProductWork(db, actor, company, family, item, access)
        if body.setup.expected_generation is not None and (
            body.setup.expected_generation != state.generation
        ):
            raise ConflictError("Company product policy changed; review setup again")
        if body.setup.expected_source_version is not None or body.setup.configuration_fingerprint:
            assigned = await family_group(access, family.id, body.setup.effective_from)
            # The default SKU is about to create this dated group assignment.
            # Resolve the proposed group before that write without claiming the
            # still-unassigned family already belongs to it.
            pending_group = body.setup.group_id is not None and assigned is None
            current = await resolve(
                db,
                actor,
                company,
                EffectiveQuery(
                    as_of=body.setup.effective_from,
                    kind=cast(Literal["GOODS", "SERVICE"], family.kind),
                    family_id=None if pending_group else family.id,
                    item_id=None if pending_group else item.id,
                    product_type_revision_id=family.product_type_revision_id,
                    group_id=body.setup.group_id or row.request.get("group_id"),
                ),
            )
            if body.setup.expected_source_version != current.source_version or (
                body.setup.configuration_fingerprint is not None
                and body.setup.configuration_fingerprint != configuration_fingerprint(current)
            ):
                raise ConflictError("Product configuration changed; review setup again")
        await bump(work, item)
        if shared:
            await bump(work, family)
        price_drafts = await apply_initial(work, body.setup, state)
        reference_ids = await setup_references(work, state, body)
        entry.update(
            setup_done=True,
            setup_key=key,
            setup_hash=hashlib.sha256(
                canonical_json(body.model_dump(mode="json", exclude_unset=True))
            ).hexdigest(),
            price_draft_ids=[str(value) for value in price_drafts],
            published_price_ids=[],
            **reference_ids,
            prices_published=not price_drafts,
            activated=False,
        )
        save_sku_progress(row, item_id, entry)
        already_active = any(
            row.progress.get("skus", {}).get(value, {}).get("activated") for value in row.sku_ids
        )
        row.status, row.step = (
            ("ACTIVATING", "ACTIVATE") if already_active else ("SETUP", "SETUP")
        )
        return work.changed

    return await run(factory, actor, company, creation_id, item_id, body, key, "setup", apply)


async def setup_references(
    work: ProductWork, state: CatalogPolicyState, body: AdvancedSkuSetup
) -> dict[str, str]:
    """Create base-unit declarations through the native dated pricing writers."""
    if body.purchase_reference is None and body.mrp is None:
        return {}
    assert work.item is not None
    expected_generation = body.setup.expected_generation
    expected_source_version = body.setup.expected_source_version
    assert expected_generation is not None and expected_source_version is not None
    revision = await work.db.scalar(
        select(ItemUnitRevision)
        .join(ItemUnitBinding, ItemUnitBinding.id == ItemUnitRevision.binding_id)
        .where(
            ItemUnitBinding.company_id == work.company,
            ItemUnitBinding.item_id == work.item.id,
            ItemUnitBinding.usage_role == "BASE",
            ItemUnitRevision.valid_from <= body.setup.effective_from,
            (ItemUnitRevision.valid_to.is_(None))
            | (ItemUnitRevision.valid_to >= body.setup.effective_from),
        )
        .limit(2)
    )
    if revision is None:
        raise ValidationFailedError("purchase reference and MRP require a current base unit")
    pricing = PricingWork(work.access, state)
    numeric_ids: dict[tuple[str, int], uuid.UUID] = {}
    result: dict[str, str] = {}
    for field, reference in (
        ("purchase_reference", body.purchase_reference),
        ("mrp", body.mrp),
    ):
        if reference is None:
            continue
        key = (reference.currency, reference.price_decimal_places)
        if key not in numeric_ids:
            numerics = list(
                await work.db.scalars(
                    select(ItemPriceNumericRevision)
                    .where(
                        ItemPriceNumericRevision.company_id == work.company,
                        ItemPriceNumericRevision.item_id == work.item.id,
                        ItemPriceNumericRevision.unit_revision_id == revision.id,
                        ItemPriceNumericRevision.currency == reference.currency,
                    )
                    .limit(2)
                )
            )
            if numerics:
                if len(numerics) != 1 or numerics[0].price_decimal_places != key[1]:
                    raise ConflictError(
                        "reference precision differs from the SKU's price precision"
                    )
                numeric_ids[key] = numerics[0].id
            else:
                created = await pricing_foundation.create_numeric(
                    pricing,
                    NumericInput(
                        expected_generation=expected_generation,
                        expected_source_version=expected_source_version,
                        valid_from=body.setup.effective_from,
                        item_id=work.item.id,
                        unit_revision_id=revision.id,
                        currency=reference.currency,
                        price_decimal_places=reference.price_decimal_places,
                    ),
                    None,
                )
                numeric_ids[key] = created.id
        common: dict[str, Any] = {
            "expected_generation": expected_generation,
            "expected_source_version": expected_source_version,
            "valid_from": body.setup.effective_from,
            "item_id": work.item.id,
            "unit_revision_id": revision.id,
            "numeric_revision_id": numeric_ids[key],
            "currency": reference.currency,
            "amount": reference.amount,
            "price_basis_quantity": reference.price_basis_quantity,
            "source_reference": reference.source_reference,
        }
        if field == "purchase_reference":
            assert body.purchase_reference is not None
            saved = await pricing_references.create_cost(
                pricing,
                CostInput.model_validate(
                    {**common, "estimate_kind": body.purchase_reference.estimate_kind}
                ),
                None,
            )
            result["purchase_reference_id"] = str(saved.id)
        else:
            assert body.mrp is not None
            saved = await pricing_references.create_mrp(
                pricing,
                MrpInput.model_validate({**common, "jurisdiction": body.mrp.jurisdiction}),
                None,
            )
            result["mrp_id"] = str(saved.id)
    for entity, fields in pricing.changed.items():
        work.changed.setdefault(entity, set()).update(fields)
    return result


async def publish(
    factory: Factory,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuPublish,
    key: str,
) -> CommandResult[AdvancedDefinitionStatus]:
    async def apply(
        db: AsyncSession, row: AdvancedProductCreation, state: CatalogPolicyState
    ) -> dict[str, set[str]]:
        expected(row, body.expected_creation_version)
        entry = sku_progress(row, item_id)
        if not entry.get("setup_done") or entry.get("prices_published"):
            raise ConflictError("SKU has no unpublished setup prices")
        _, item = await native_rows(db, row, company, item_id)
        if item.status != "DRAFT":
            raise ConflictError("SKU is no longer a draft")
        access = ConfigurationAccess(db, actor, company)
        work = PricingWork(access, state)
        published_ids = []
        for raw in entry.get("price_draft_ids", []):
            draft_id = uuid.UUID(raw)
            draft = await pricing_row(access, ItemPriceDraft, draft_id)
            if draft.item_id != item_id:
                raise PermissionDeniedError("price draft belongs to another SKU")
            preview = await pricing_publication.preview(db, actor, company, draft_id)
            if not preview.publishable:
                raise ConflictError("Price setup changed; review its publication blockers")
            result = await pricing_publication.publish(
                work,
                PublishInput(
                    expected_version=preview.row_version,
                    expected_generation=state.generation,
                    expected_source_version=preview.source_version,
                    supersedes_id=preview.supersedes_id,
                    expected_previous_version=preview.expected_previous_version,
                ),
                draft_id,
            )
            published_ids.append(str(result.id))
        entry["published_price_ids"] = published_ids
        entry["prices_published"] = True
        save_sku_progress(row, item_id, entry)
        return work.changed

    return await run(factory, actor, company, creation_id, item_id, body, key, "publish", apply)


async def activate(
    factory: Factory,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuActivate,
    key: str,
    secret: bytes,
) -> CommandResult[AdvancedDefinitionStatus]:
    async def apply(
        db: AsyncSession, row: AdvancedProductCreation, state: CatalogPolicyState
    ) -> dict[str, set[str]]:
        expected(row, body.expected_creation_version)
        entry = sku_progress(row, item_id)
        if not entry.get("setup_done") or not entry.get("prices_published"):
            raise ConflictError("Complete and publish SKU setup before activation")
        if entry.get("activated"):
            raise ConflictError("SKU was already activated; reload its progress")
        family, item = await native_rows(db, row, company, item_id)
        if (family.row_version, item.row_version) != (
            body.expected_family_version,
            body.expected_item_version,
        ):
            raise ConflictError("Product Profile or SKU changed; preview activation again")
        if state.generation != body.expected_generation:
            raise ConflictError("Company policy changed; preview activation again")
        access = ConfigurationAccess(db, actor, company)
        work = ProductWork(db, actor, company, family, item, access)
        await bump(work, item)
        reviewed = await activation.prepare(
            work, body.as_of, secret, item_version=body.expected_item_version
        )
        if reviewed[0].source_version != body.expected_source_version:
            raise ConflictError("Activation sources changed; preview activation again")
        if not reviewed[0].eligible:
            raise ConflictError("SKU setup has activation blockers")
        await activation.activate(
            work,
            ActivationCommit(
                expected_version=body.expected_item_version,
                expected_family_version=body.expected_family_version,
                as_of=body.as_of,
                preview_token=reviewed[0].preview_token,
            ),
            secret,
            prepared=reviewed,
        )
        entry["activated"] = True
        save_sku_progress(row, item_id, entry)
        all_done = all(
            row.progress.get("skus", {}).get(value, {}).get("activated") for value in row.sku_ids
        )
        row.status, row.step = ("OPENING", "OPENING") if all_done else ("ACTIVATING", "ACTIVATE")
        return work.changed

    return await run(factory, actor, company, creation_id, item_id, body, key, "activate", apply)

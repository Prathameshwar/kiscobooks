"""Editable native drafts and immutable price publication with explicit predecessors."""

import uuid

from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.pricing import (
    ItemPrice,
    ItemPriceDraft,
    ItemPriceFormula,
    ItemPriceSeries,
    ItemPriceTier,
    PricePlan,
    PricingRow,
    PurchasePriceTerm,
)
from catalog.schemas.pricing import (
    DatedInput,
    DraftInput,
    DraftPreview,
    DraftReplace,
    FormulaInput,
    PublishInput,
    PurchaseTermInput,
    TierInput,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldWriteChecks
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, protected, purpose_access, row
from catalog.tasks.pricing_readiness import assess
from catalog.tasks.pricing_schedule import publication as review_publication
from catalog.tasks.pricing_validation import validate

CHILDREN = (
    ("tiers", ItemPriceTier, TierInput),
    ("purchase_term", PurchasePriceTerm, PurchaseTermInput),
    ("formula", ItemPriceFormula, FormulaInput),
)


async def draft_input(access: ConfigurationAccess, value: ItemPriceDraft | ItemPrice) -> DraftInput:
    await access.require(value)
    await purpose_access(access, value)
    result = {key: getattr(value, key) for key in DraftInput.model_fields if hasattr(value, key)}
    for field, model, schema in CHILDREN:
        # Sale callers never query or require purchase-term access.
        if field == "purchase_term":
            series = await row(access, ItemPriceSeries, value.series_id)
            plan = await row(access, PricePlan, series.plan_id)
            if plan.purpose != "PURCHASE":
                result[field] = None
                continue
        await protected(access, model)
        owner_field = "draft_id" if isinstance(value, ItemPriceDraft) else "price_id"
        records = list(
            await access.db.scalars(
                select(model)
                .where(model.company_id == access.company, getattr(model, owner_field) == value.id)
                .order_by(model.min_quantity if model is ItemPriceTier else model.id)
                .limit(65 if field == "tiers" else 2)
            )
        )
        if len(records) > (64 if field == "tiers" else 1):
            raise ConflictError("price aggregate exceeds its bounded native shape")
        entries = []
        for record in records:
            await access.require(record)
            entries.append({key: getattr(record, key) for key in schema.model_fields})
        result[field] = entries if field == "tiers" else entries[0] if entries else None
    return DraftInput.model_validate(result)


async def children(
    work: PricingWork,
    parent: ItemPriceDraft | ItemPrice,
    body: DraftInput,
    *,
    replacing: bool = False,
) -> None:
    owner_field = "draft_id" if isinstance(parent, ItemPriceDraft) else "price_id"
    for field, model, _ in CHILDREN:
        incoming = getattr(body, field)
        if field == "purchase_term":
            series = await row(work.access, ItemPriceSeries, parent.series_id)
            plan = await row(work.access, PricePlan, series.plan_id)
            if plan.purpose != "PURCHASE":
                continue
        if replacing:
            # Only unpublished draft children can be replaced; published terms are append-only.
            await protected(work.access, model)
            old = list(
                await work.db.scalars(
                    select(model)
                    .where(model.company_id == work.company, model.draft_id == parent.id)
                    .limit(65)
                )
            )
            for entry in old:
                native = await work.access.values(entry)
                context = await work.access.context(model)
                context.assert_writable(
                    frozenset(native),
                    before=native,
                    after={},
                    checked=work.access.checks.setdefault(
                        context.native.entity_type, FieldWriteChecks()
                    ),
                )
                work.changed.setdefault(context.native.entity_type, set()).update(native)
                audit_change(
                    work.db,
                    work.actor,
                    work.company,
                    context.native.entity_type,
                    entry.id,
                    "update",
                    frozenset(native),
                    before=native,
                    after={},
                )
                await work.db.delete(entry)
            await work.db.flush()
        entries = incoming if field == "tiers" else [incoming] if incoming is not None else []
        for entry in entries:
            data = entry.model_dump()
            if field != "formula":
                data["currency"] = parent.currency
            await work.new(
                model,
                draft_id=parent.id if owner_field == "draft_id" else None,
                price_id=parent.id if owner_field == "price_id" else None,
                **data,
            )


async def save_draft(
    work: PricingWork, body: DraftInput | DraftReplace, object_id: uuid.UUID | None
) -> PricingRow:
    series, _, _, _, _ = await validate(work.access, body)
    await purpose_access(work.access, series, write=True)
    data = body.model_dump(exclude={"tiers", "purchase_term", "formula", "expected_version"})
    data.update(
        item_id=series.item_id, unit_revision_id=series.unit_revision_id, currency=series.currency
    )
    if object_id is None:
        value = await work.new(ItemPriceDraft, **data, status="DRAFT")
    else:
        value = await row(work.access, ItemPriceDraft, object_id)
        await purpose_access(work.access, value, write=True)
        if value.status != "DRAFT":
            raise ConflictError("published price drafts cannot be edited")
        if value.series_id != body.series_id:
            raise PermissionDeniedError("an existing draft cannot change its price series")
        assert isinstance(body, DraftReplace)
        await work.update(value, body.expected_version, **data)
    await children(work, value, body, replacing=object_id is not None)
    return value


async def publish(work: PricingWork, body: PublishInput, object_id: uuid.UUID | None) -> PricingRow:
    assert object_id is not None
    value = await row(work.access, ItemPriceDraft, object_id)
    await purpose_access(work.access, value, write=True)
    if value.status != "DRAFT" or value.row_version != body.expected_version:
        raise ConflictError("draft changed or is already published")
    definition = await draft_input(work.access, value)
    assessment = await assess(work.access, definition, check_schedule=True)
    assessment.require_valid()
    dated = DatedInput.model_validate(
        {
            **body.model_dump(exclude={"expected_version"}),
            "valid_from": value.valid_from,
            "valid_to": value.valid_to,
        }
    )
    await work.history(ItemPrice, dated, {"series_id": value.series_id})
    data = {
        key: getattr(value, key)
        for key in (
            "item_id",
            "unit_revision_id",
            "currency",
            "numeric_revision_id",
            "series_id",
            "valid_from",
            "valid_to",
            "price_method",
            "amount",
            "price_basis_quantity",
        )
    }
    published = await work.new(
        ItemPrice, **data, source_draft_id=value.id, supersedes_id=body.supersedes_id
    )
    await children(work, published, definition)
    await work.update(value, body.expected_version, status="PUBLISHED")
    return published


async def preview(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID
) -> DraftPreview:
    access = ConfigurationAccess(db, actor, company)
    value = await row(access, ItemPriceDraft, object_id)
    definition = await draft_input(access, value)
    assessment = await assess(access, definition, check_schedule=True)
    publication = await review_publication(access, value)
    predecessor = publication.predecessor
    if predecessor is not None:
        assessment.source_ids = list(dict.fromkeys([*assessment.source_ids, predecessor.id]))
    state = await policy_state(db, actor, company)
    context = await access.context(ItemPriceDraft)
    return DraftPreview(
        id=value.id,
        row_version=value.row_version,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        valid=not assessment.issues,
        issues=assessment.issues,
        source_ids=assessment.source_ids,
        amount=assessment.amount,
        currency=value.currency,
        price_basis_quantity=value.price_basis_quantity,
        tax_basis=assessment.plan.tax_basis,
        guard_ids=list(assessment.guards.guard_ids),
        approval_guard_ids=list(assessment.guards.approval_ids),
        transaction_requirements=assessment.transaction_requirements,
        coverage_valid_to=assessment.coverage_valid_to,
        publishable=not assessment.issues and not publication.issues,
        publication_issues=publication.issues,
        supersedes_id=predecessor.id if predecessor else None,
        expected_previous_version=predecessor.row_version if predecessor else None,
    )

"""Native GST administration under Catalog's company lock and current authority."""

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select

from catalog.domain.tax import validate_components
from catalog.models import ItemGroup, ProductFamily, UnitOfMeasure
from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import PricingRow
from catalog.models.tax import (
    CatalogTaxBinding,
    CatalogTaxScope,
    TaxCategory,
    TaxClassification,
    TaxRate,
    TaxRateComponent,
    TaxRateSeries,
    TaxRule,
)
from catalog.models.tax_governance import (
    TaxHistoryAction,
    TaxImpactReview,
    TaxRuleApplicability,
)
from catalog.schemas import tax as s
from catalog.schemas.pricing import DatedInput, PublicationInput
from catalog.tasks.classification import validate_custom
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.custom_fields import reserve_claims
from catalog.tasks.field_indexes import index_values
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, business_date, product, protected, row
from catalog.tasks.pricing_foundation import values


async def jurisdiction(access: ConfigurationAccess) -> None:
    context = await access.context(TaxRule)
    if context.company.country_code != "IN":
        raise ConflictError("this tax definition adapter supports Indian companies only")


class TaxWork(PricingWork):
    def __init__(self, access: ConfigurationAccess, state: CatalogPolicyState) -> None:
        super().__init__(access, state)
        self.touched: dict[tuple[type[Any], uuid.UUID], Any] = {}
        self.predecessors: dict[uuid.UUID, dt.date | None] = {}
        self.release_id: uuid.UUID | None = None
        # Set when a release publishes against a verified COMPLETE background impact review.
        self.impact_review: TaxImpactReview | None = None
        self.change_reason = "Native tax publication"
        # Rows Accounting replicates (classification, rule, rate), with the strongest action this
        # command took on each. Components ride on their rate; bindings stay Catalog-only.
        self.publications: dict[tuple[type[Any], uuid.UUID], str] = {}

    async def record(self, value: Any, before: Mapping[str, Any], action: str = "create") -> None:
        await super().record(value, before, action)
        self.touched[type(value), value.id] = value
        self.access.tax_rows.clear()
        if isinstance(value, TaxClassification | TaxRule | TaxRate):
            from catalog.events.tax_publication import stronger

            if action == "withdraw" or (
                isinstance(value, TaxRule)
                and before.get("is_active") is True
                and not value.is_active
            ):
                kind = "WITHDRAW"
            else:
                kind = "PUBLISH" if not before else "UPDATE"
            key = (type(value), value.id)
            self.publications[key] = stronger(self.publications.get(key), kind)

    async def published(self) -> None:
        """Stage Accounting's replica events at the bumped generation (Phase 5)."""
        from catalog.tasks.tax_publication import emit_publications

        await emit_publications(self.db, self.state, self.publications)

    async def validate(self) -> None:
        from catalog.tasks.tax_integrity import validate_changes

        await validate_changes(self)

    async def history(self, model: type[Any], body: DatedInput, filters: dict[str, Any]) -> None:
        from catalog.tasks.tax_history import live_rows, require_live

        await self.publication(body)
        today = business_date((await self.access.context(model)).company.timezone)
        if body.valid_from < today:
            raise ConflictError("new tax history cannot rewrite past dates")
        existing = [
            entry
            for entry in await live_rows(self.access, model, **filters)
            if all(getattr(entry, key) == value for key, value in filters.items())
        ]
        previous = None
        if body.supersedes_id is not None:
            # Any predecessor applicable on `valid_from` is in force when that date is today, so
            # a same-day replacement would rewrite a definition already used (withdrawal rule).
            if body.valid_from <= today:
                raise ConflictError("a superseding tax revision must start on a future date")
            previous = await row(self.access, model, body.supersedes_id)
            await require_live(self.access, previous)
            if any(getattr(previous, key) != value for key, value in filters.items()):
                raise ConflictError("replacement belongs to a different tax history")
            if previous.valid_from >= body.valid_from or (
                previous.valid_to is not None and previous.valid_to < body.valid_from
            ):
                raise ConflictError("replacement must shorten an applicable predecessor")
        overlaps = [
            entry
            for entry in existing
            if (entry.valid_to is None or entry.valid_to >= body.valid_from)
            and entry.valid_from <= (body.valid_to or dt.date.max)
        ]
        if any(previous is None or entry.id != previous.id for entry in overlaps):
            raise ConflictError("tax history overlaps an existing revision")
        if previous is not None:
            assert body.expected_previous_version is not None
            self.predecessors[previous.id] = previous.valid_to
            await self.update(
                previous,
                body.expected_previous_version,
                valid_to=body.valid_from - dt.timedelta(days=1),
            )

    @staticmethod
    async def authorize_reference(
        access: ConfigurationAccess, value: Any, *, write: bool = False
    ) -> None:
        from catalog.tasks.tax_reads import dependencies

        await dependencies(access, value, publication=True)

    async def publication(self, body: PublicationInput) -> None:
        await jurisdiction(self.access)
        context = await self.access.context(TaxRule)
        if (
            body.expected_generation != self.state.generation
            or body.expected_source_version != context.source_version
        ):
            raise ConflictError("tax policy or Identity source changed; preview again")


async def history_evidence(work: PricingWork, value: Any, body: DatedInput) -> None:
    # Dated definitions audit as `publish` (the reviewed fact); this evidence row is `create`.
    assert isinstance(work, TaxWork)
    await work.new(
        TaxHistoryAction,
        resource=value.__tablename__,
        target_id=value.id,
        action="SUPERSEDE" if body.supersedes_id is not None else "PUBLISH",
        previous_id=body.supersedes_id,
        previous_valid_to=work.predecessors.get(body.supersedes_id) if body.supersedes_id else None,
        release_id=work.release_id,
        reason=work.change_reason,
        business_date=business_date((await work.access.context(type(value))).company.timezone),
    )


async def active(access: ConfigurationAccess, model: type[Any], object_id: uuid.UUID) -> Any:
    value = await row(access, model, object_id)
    if not value.is_active:
        raise ConflictError("tax definition references an inactive master")
    return value


async def scope_owner(access: ConfigurationAccess, body: Any) -> uuid.UUID:
    if body.owner_kind == "GROUP":
        await access.reference(ItemGroup, body.group_id)
        return uuid.UUID(str(body.group_id))
    if body.owner_kind == "FAMILY":
        family = await access.reference(ProductFamily, body.family_id)
        return uuid.UUID(str(family.id))
    if body.owner_kind == "SKU":
        item, _ = await product(access, body.item_id)
        return item.id
    return access.company


async def create_classification(
    work: PricingWork, body: s.ClassificationInput, object_id: uuid.UUID | None
) -> PricingRow:
    await work.history(
        TaxClassification, body, {"code_system": body.code_system, "code": body.code}
    )
    value = await work.new(TaxClassification, "publish", **values(body))
    await history_evidence(work, value, body)
    return value


async def create_category(
    work: PricingWork, body: s.CategoryInput, object_id: uuid.UUID | None
) -> PricingRow:
    await jurisdiction(work.access)
    return await work.new(TaxCategory, **body.model_dump(), is_active=True)


async def custom(
    work: PricingWork,
    body: s.RuleInput | s.RulePatch,
    value: TaxRule | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    context = await work.access.context(TaxRule)
    before = await work.access.values(value) if value is not None else {}
    return await validate_custom(
        work.db,
        work.actor,
        work.company,
        context,
        body.custom_fields,
        before,
        {**before, **incoming},
        value.custom_fields or {} if value is not None else {},
        creating=value is None,
    )


async def index_rule(work: PricingWork, value: TaxRule) -> None:
    context = await work.access.context(TaxRule)
    await reserve_claims(
        work.db,
        company_id=work.company,
        entity_type=context.native.entity_type,
        entity_id=value.id,
        definitions=context.definitions,
        values=value.custom_fields or {},
    )
    await index_values(work.db, context, value.id, value.custom_fields or {})


async def create_rule(
    work: PricingWork, body: s.RuleInput, object_id: uuid.UUID | None
) -> PricingRow:
    await jurisdiction(work.access)
    await active(work.access, TaxCategory, body.tax_category_id)
    incoming = body.model_dump(exclude={"custom_fields", "classifications"})
    incoming.update(is_active=True, row_version=1)
    descriptive = await custom(work, body, None, incoming)
    incoming.pop("row_version")
    value = await work.new(TaxRule, **incoming, custom_fields=descriptive)
    await index_rule(work, value)
    for definition in body.classifications:
        await create_applicability(
            work, s.ApplicabilityInput(rule_id=value.id, **definition.model_dump()), None
        )
    return value


async def create_applicability(
    work: PricingWork, body: s.ApplicabilityInput, object_id: uuid.UUID | None
) -> PricingRow:
    await jurisdiction(work.access)
    rule = await active(work.access, TaxRule, body.rule_id)
    if rule.classification_scope != "SPECIFIC":
        raise ValidationFailedError("generic templates cannot restrict individual classifications")
    if (rule.item_kind == "GOODS") != (body.code_system == "HSN"):
        raise ValidationFailedError("rule applicability differs from its product kind")
    await protected(work.access, CatalogTaxBinding)
    if (
        await work.db.scalar(
            select(CatalogTaxBinding.id)
            .where(
                CatalogTaxBinding.company_id == work.company, CatalogTaxBinding.rule_id == rule.id
            )
            .limit(1)
        )
        is not None
    ):
        raise ConflictError("a used rule's applicability is immutable; publish a replacement rule")
    existing = list(
        await work.db.scalars(
            select(TaxRuleApplicability.id)
            .where(
                TaxRuleApplicability.company_id == work.company,
                TaxRuleApplicability.rule_id == rule.id,
            )
            .limit(129)
        )
    )
    if len(existing) >= 128:
        raise ConflictError("tax rule applicability exceeds its bounded definition")
    return await work.new(TaxRuleApplicability, **body.model_dump())


async def patch_master(
    work: PricingWork,
    body: s.MasterPatch,
    object_id: uuid.UUID | None,
    model: type[TaxRule] | type[TaxCategory],
) -> PricingRow:
    assert object_id is not None
    value = await row(work.access, model, object_id)
    if not body.name.strip() or any(ord(char) < 32 for char in body.name):
        raise ValidationFailedError("master name must contain printable text")
    if not body.is_active:
        references = (
            ((TaxRateSeries, "rule_id"), (CatalogTaxBinding, "rule_id"))
            if model is TaxRule
            else ((TaxRule, "tax_category_id"), (CatalogTaxBinding, "tax_category_id"))
        )
        for dependent, field in references:
            await protected(work.access, dependent)
            if (
                await work.db.scalar(
                    select(dependent.id)
                    .where(
                        dependent.company_id == work.company, getattr(dependent, field) == value.id
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("referenced tax masters cannot be retired")
    incoming = {"name": body.name.strip(), "is_active": body.is_active}
    if isinstance(value, TaxRule):
        assert isinstance(body, s.RulePatch)
        incoming["custom_fields"] = await custom(work, body, value, incoming)
    await work.update(value, body.expected_version, **incoming)
    if isinstance(value, TaxRule):
        await index_rule(work, value)
    return value


async def patch_rule(
    work: PricingWork, body: s.RulePatch, object_id: uuid.UUID | None
) -> PricingRow:
    return await patch_master(work, body, object_id, TaxRule)


async def patch_category(
    work: PricingWork, body: s.MasterPatch, object_id: uuid.UUID | None
) -> PricingRow:
    return await patch_master(work, body, object_id, TaxCategory)


async def create_series(
    work: PricingWork, body: s.SeriesInput, object_id: uuid.UUID | None
) -> PricingRow:
    await jurisdiction(work.access)
    rule = await active(work.access, TaxRule, body.rule_id)
    await active(work.access, TaxCategory, rule.tax_category_id)
    if rule.treatment not in {"TAXABLE", "NIL_RATED"}:
        raise ValidationFailedError("exempt and non-GST rules have no charged rate series")
    return await work.new(TaxRateSeries, **body.model_dump())


async def validate_rate(
    access: ConfigurationAccess, body: s.RateInput
) -> tuple[TaxRateSeries, TaxRule]:
    await jurisdiction(access)
    series = await row(access, TaxRateSeries, body.series_id)
    rule = await active(access, TaxRule, series.rule_id)
    await active(access, TaxCategory, rule.tax_category_id)
    validate_components(series.applicability, rule.treatment, body.components)
    for component in body.components:
        await component_basis(access, component)
    return series, rule


async def component_basis(access: ConfigurationAccess, component: Any) -> UnitOfMeasure | None:
    if component.unit_id is None:
        return None
    unit = await access.reference(UnitOfMeasure, component.unit_id)
    from catalog.domain.units import QuantityRule

    assert component.basis_quantity is not None and component.currency is not None
    QuantityRule(unit.decimal_places, unit.quantity_increment).validate(component.basis_quantity)
    if component.currency != "INR":
        raise ValidationFailedError("Indian fixed cess must declare an INR amount")
    return cast(UnitOfMeasure, unit)


async def publish_rate(
    work: PricingWork, body: s.RateInput, object_id: uuid.UUID | None
) -> PricingRow:
    await validate_rate(work.access, body)
    await work.history(TaxRate, body, {"series_id": body.series_id})
    incoming = values(body)
    incoming.pop("components")
    value = await work.new(TaxRate, "publish", **incoming, supersedes_id=body.supersedes_id)
    for entry in body.components:
        await work.new(TaxRateComponent, "publish", rate_id=value.id, **entry.model_dump())
    await history_evidence(work, value, body)
    return value


async def preview_rate(access: ConfigurationAccess, body: s.RateInput) -> s.RatePreview:
    # Authority first: an unpermitted caller learns nothing from validation outcomes.
    access.actor.require_scope("tax_rule.publish", target=ScopePath(company_id=access.company))
    await access.context(TaxRate, "tax_rule.manage")
    series, rule = await validate_rate(access, body)
    state = await policy_state(access.db, access.actor, access.company)
    generation = state.generation if state is not None else 1
    source_version = (await access.context(TaxRule)).source_version
    if body.expected_generation != generation or body.expected_source_version != source_version:
        raise ConflictError("tax policy or Identity source changed; preview again")
    result = s.RatePreview(
        series_id=series.id,
        applicability=cast(s.Applicability, series.applicability),
        treatment=cast(s.Treatment, rule.treatment),
        policy_generation=generation,
        source_version=source_version,
        components=body.components,
    )
    state = await policy_state(access.db, access.actor, access.company, lock=True)
    assert state is not None
    work = TaxWork(access, state)
    savepoint = await access.db.begin_nested()
    try:
        await publish_rate(work, body, None)
        await work.validate()
    finally:
        await savepoint.rollback()
        access.tax_rows.clear()
    return result


async def create_scope(
    work: PricingWork, body: s.ScopeInput, object_id: uuid.UUID | None
) -> PricingRow:
    await jurisdiction(work.access)
    owner = await scope_owner(work.access, body)
    return await work.new(CatalogTaxScope, **body.model_dump(), owner_id=owner)


async def scope_kind(access: ConfigurationAccess, scope: CatalogTaxScope) -> str | None:
    if scope.group_id is not None:
        group = await access.reference(ItemGroup, scope.group_id)
        return None if group.allowed_kind == "BOTH" else cast(str, group.allowed_kind)
    if scope.family_id is not None:
        return cast(str, (await access.reference(ProductFamily, scope.family_id)).kind)
    if scope.item_id is not None:
        _, family = await product(access, scope.item_id)
        return family.kind
    return None


async def publish_binding(
    work: PricingWork, body: s.BindingInput, object_id: uuid.UUID | None
) -> PricingRow:
    scope = await row(work.access, CatalogTaxScope, body.scope_id)
    await scope_owner(work.access, scope)
    owner_kind = await scope_kind(work.access, scope)
    if body.item_kind is not None and owner_kind is not None and owner_kind != body.item_kind:
        raise ValidationFailedError("binding kind differs from the scope's product kind")
    # The kind a binding serves: its own key on a mixed scope, else the scope's fixed kind.
    kind = body.item_kind or owner_kind
    if body.classification_id is not None:
        value = await row(work.access, TaxClassification, body.classification_id)
        if value.valid_from > body.valid_from or (
            value.valid_to is not None and (body.valid_to is None or value.valid_to < body.valid_to)
        ):
            raise ConflictError("classification must cover the complete binding interval")
        if kind is not None and kind != value.item_kind:
            raise ValidationFailedError("classification differs from the binding's product kind")
    if body.tax_category_id is not None:
        await active(work.access, TaxCategory, body.tax_category_id)
    if body.rule_id is not None:
        rule = await active(work.access, TaxRule, body.rule_id)
        await active(work.access, TaxCategory, rule.tax_category_id)
        if kind is not None and kind != rule.item_kind:
            raise ValidationFailedError("tax rule differs from the binding's product kind")
    # Each kind keys its own history: a goods and a services default may coexist on one
    # company or BOTH group, and NULL (every kind) is a history of its own.
    await work.history(
        CatalogTaxBinding,
        body,
        {
            "scope_id": scope.id,
            "direction": body.direction,
            "bundle": body.bundle,
            "item_kind": body.item_kind,
        },
    )
    binding = await work.new(CatalogTaxBinding, "publish", **values(body))
    await history_evidence(work, binding, body)
    return binding

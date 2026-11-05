"""Resolve complete native bundles through dated ancestry, without invoice calculation."""

import uuid
from typing import Any, cast

from billing_platform.errors import ConflictError
from sqlalchemy import select

from catalog.domain.classification import MAX_DEPTH
from catalog.domain.tax import CONTEXTS, classification_matches, signature
from catalog.models import ItemGroup, ItemGroupParent
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
from catalog.models.tax_governance import TaxRuleApplicability
from catalog.schemas import tax as s
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import product, protected, row
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import group_on
from catalog.tasks.tax_commands import active, component_basis, jurisdiction, scope_owner
from catalog.tasks.tax_history import effective, require_live, rows
from catalog.tasks.tax_validation import stored_components, stored_match


class Pins:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, uuid.UUID], s.SourcePin] = {}

    def add(self, value: Any) -> None:
        entity = "catalog." + value.__tablename__
        self.rows[entity, value.id] = s.SourcePin(
            entity_type=entity, entity_id=value.id, entity_version=getattr(value, "row_version", 1)
        )


async def resolve(
    access: ConfigurationAccess, body: s.ResolveInput, *, work: ProductWork | None = None
) -> s.Resolution:
    await jurisdiction(access)
    if work is None:
        item, family = await product(access, body.item_id)
        work = ProductWork(access.db, access.actor, access.company, family, item, access)
    assert work.item is not None
    if work.item.status == "DISCONTINUED" or work.family.status == "DISCONTINUED":
        raise ConflictError("tax configuration requires a current product")
    if (body.direction == "SALE" and not work.item.sellable) or (
        body.direction == "PURCHASE" and not work.item.purchasable
    ):
        raise ConflictError("product does not support the requested tax direction")
    pins = Pins()
    pins.add(work.item)
    pins.add(work.family)
    owners = [("SKU", work.item.id), ("FAMILY", work.family.id)]
    group = await group_on(work, body.as_of)
    if group is not None:
        await access.require(group)
        pins.add(group)
    group_id = group.group_id if group is not None else None
    seen: set[uuid.UUID] = set()
    while group_id is not None:
        if group_id in seen or len(seen) >= MAX_DEPTH:
            raise ConflictError("tax ancestry is cyclic or exceeds its depth bound")
        seen.add(group_id)
        current = await access.reference(ItemGroup, group_id)
        pins.add(current)
        owners.append(("GROUP", group_id))
        edge = await effective(access, ItemGroupParent, body.as_of, group_id=group_id)
        if edge is None:
            raise ConflictError("tax ancestry has no effective parent definition")
        pins.add(edge)
        group_id = edge.parent_group_id
    owners.append(("COMPANY", access.company))
    await protected(access, CatalogTaxScope)
    scopes = list(
        await access.db.scalars(
            select(CatalogTaxScope)
            .where(
                CatalogTaxScope.company_id == access.company,
                CatalogTaxScope.owner_id.in_([owner for _, owner in owners]),
            )
            .limit(MAX_DEPTH + 4)
        )
    )
    indexed = {}
    for scope_row in scopes:
        await access.require(scope_row)
        await scope_owner(access, scope_row)
        pins.add(scope_row)
        indexed[scope_row.owner_kind, scope_row.owner_id] = scope_row
    selected: dict[str, CatalogTaxBinding] = {}
    missing = []
    blocked = False
    bundles = []
    for bundle in ("CLASSIFICATION", "TREATMENT", "RULE"):
        for owner in owners:
            scope = indexed.get(owner)
            if scope is None:
                continue
            # A binding keyed to the product's kind outranks the scope's all-kinds binding.
            binding = None
            for kind in (work.family.kind, None):
                binding = await effective(
                    access,
                    CatalogTaxBinding,
                    body.as_of,
                    scope_id=scope.id,
                    direction=body.direction,
                    bundle=bundle,
                    item_kind=kind,
                )
                if binding is not None:
                    break
            if binding is None:
                continue
            pins.add(binding)
            if binding.mode == "INHERIT":
                continue
            bundles.append(
                s.BundleSource(
                    bundle=bundle,
                    scope_id=scope.id,
                    owner_kind=scope.owner_kind,
                    binding_id=binding.id,
                )
            )
            if binding.mode == "REQUIRE_EXPLICIT":
                blocked = True
            else:
                selected[bundle] = binding
            break
        if bundle not in selected:
            missing.append(bundle.lower())
    state = await policy_state(access.db, access.actor, access.company)
    context = await access.context(TaxRule)
    result = s.Resolution(
        item_id=work.item.id,
        as_of=body.as_of,
        direction=body.direction,
        status="REQUIRE_EXPLICIT" if blocked else "MISSING" if missing else "COMPLETE",
        missing=missing,
        bundles=bundles,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
    )
    classification = None
    if "CLASSIFICATION" in selected:
        binding = selected["CLASSIFICATION"]
        assert binding.classification_id is not None
        classification = await row(access, TaxClassification, binding.classification_id)
        await require_live(access, classification)
        pins.add(classification)
        if (
            classification.item_kind != work.family.kind
            or classification.valid_from > body.as_of
            or (classification.valid_to is not None and classification.valid_to < body.as_of)
        ):
            raise ConflictError("selected classification is incompatible or not effective")
        result.classification_id, result.classification_code = (
            classification.id,
            classification.code,
        )
    treatment = selected.get("TREATMENT")
    if treatment is not None:
        assert treatment.tax_category_id is not None
        pins.add(await active(access, TaxCategory, treatment.tax_category_id))
        result.treatment = cast(s.Treatment, treatment.treatment)
        result.exemption_reason = treatment.exemption_reason
        result.tax_category_id = treatment.tax_category_id
    if "RULE" in selected:
        rule_id = selected["RULE"].rule_id
        assert rule_id is not None
        rule = await active(access, TaxRule, rule_id)
        pins.add(rule)
        pins.add(await active(access, TaxCategory, rule.tax_category_id))
        if rule.item_kind != work.family.kind or (
            treatment is not None
            and (
                rule.treatment != treatment.treatment
                or rule.tax_category_id != treatment.tax_category_id
            )
        ):
            raise ConflictError("classification, treatment and rule form an incompatible bundle")
        result.rule_id = rule.id
        applicability = await rows(access, TaxRuleApplicability, rule_id=rule.id)
        for match in applicability:
            await access.require(match)
            pins.add(match)
        matches = [stored_match(entry) for entry in applicability]
        if rule.classification_scope not in {"SPECIFIC", "ANY"}:
            raise ConflictError("tax rule classification scope requires a reviewed correction")
        if rule.classification_scope == "ANY" and applicability:
            raise ConflictError("generic tax template has incompatible classification restrictions")
        if rule.classification_scope == "SPECIFIC" and not applicability:
            result.missing.append("rule_applicability")
        elif rule.classification_scope == "SPECIFIC" and classification is not None and not any(
            classification_matches(classification.code_system, classification.code, entry)
            for entry in matches
        ):
            raise ConflictError(
                "selected classification is outside the rule's native applicability"
            )
        if rule.treatment in {"TAXABLE", "NIL_RATED"}:
            await protected(access, TaxRateSeries)
            series_rows = list(
                await access.db.scalars(
                    select(TaxRateSeries)
                    .where(
                        TaxRateSeries.company_id == access.company, TaxRateSeries.rule_id == rule.id
                    )
                    .limit(4)
                )
            )
            if len(series_rows) > 3:
                raise ConflictError("tax rule exceeds its native applicability contexts")
            found = set()
            totals = set()
            for series in series_rows:
                await access.require(series)
                pins.add(series)
                rate = await effective(access, TaxRate, body.as_of, series_id=series.id)
                if rate is None:
                    continue
                pins.add(rate)
                await protected(access, TaxRateComponent)
                components = list(
                    await access.db.scalars(
                        select(TaxRateComponent)
                        .where(
                            TaxRateComponent.company_id == access.company,
                            TaxRateComponent.rate_id == rate.id,
                        )
                        .order_by(TaxRateComponent.position)
                        .limit(17)
                    )
                )
                entries = stored_components(series.applicability, rule.treatment, components)
                for component in components:
                    await access.require(component)
                    unit = await component_basis(access, component)
                    if unit is not None:
                        pins.add(unit)
                    pins.add(component)
                found.add(series.applicability)
                totals.add(signature(entries))
                result.rates.append(
                    s.RateDefinition(
                        applicability=cast(s.Applicability, series.applicability),
                        rate_id=rate.id,
                        source_reference=rate.source_reference,
                        source_url=rate.source_url,
                        source_sha256=rate.source_sha256,
                        cess_levy="GST_COMPENSATION"
                        if any(entry.component == "CESS" for entry in entries)
                        else None,
                        components=entries,
                    )
                )
            if len(totals) > 1:
                raise ConflictError(
                    "effective GST or compensation cess disagrees across supply contexts"
                )
            result.missing += ["rate:" + key for key in sorted(CONTEXTS.keys() - found)]
    if result.missing and result.status == "COMPLETE":
        result.status = "MISSING"
    result.rates.sort(key=lambda entry: entry.applicability)
    result.sources = sorted(
        pins.rows.values(), key=lambda entry: (entry.entity_type, entry.entity_id)
    )
    return result

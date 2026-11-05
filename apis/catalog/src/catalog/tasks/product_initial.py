"""Initial master definitions participate in the product's existing transaction."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from billing_platform.authz import ScopePath
from billing_platform.errors import PlatformError, ValidationFailedError
from sqlalchemy import select

from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import PricePlan, PricingRow
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.tax import TaxRule
from catalog.schemas import pricing as p
from catalog.schemas import tax as t
from catalog.schemas.product_authoring import CategoryAssignmentInput, GroupAssignmentInput
from catalog.schemas.product_initial import InitialProductSetup
from catalog.tasks.pricing_commands import PricingWork, row
from catalog.tasks.product_classification import (
    assign_categories,
    assign_group,
    assign_manufacturer,
)
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_units import add_barcode, bind_unit


@contextmanager
def setup_field(path: str) -> Iterator[None]:
    try:
        yield
    except PlatformError as error:
        if error.status_code < 500:
            prefix = "initial_setup." + path
            fields = error.extra.get("fields") or {"": error.message}
            error.extra["fields"] = {
                key
                if key.startswith("initial_setup.")
                else prefix + ("." + key if key else ""): message
                for key, message in fields.items()
            }
        raise


async def apply_initial(
    work: ProductWork, setup: InitialProductSetup, state: CatalogPolicyState
) -> list[uuid.UUID]:
    if setup.group_id is not None:
        with setup_field("group_id"):
            await assign_group(
                work,
                GroupAssignmentInput(
                    expected_version=1, group_id=setup.group_id, valid_from=setup.effective_from
                ),
            )
        await work.db.flush()
    for index, unit in enumerate(setup.units):
        with setup_field("units." + str(index)):
            await bind_unit(work, unit)
        await work.db.flush()
    if setup.attributes is not None:
        from catalog.tasks.product_attributes import configure_family

        with setup_field("attributes"):
            await configure_family(work, setup.attributes)
        await work.db.flush()
    for index, barcode in enumerate(setup.barcodes):
        with setup_field("barcodes." + str(index)):
            await add_barcode(work, barcode)
        await work.db.flush()
    if setup.categories:
        with setup_field("categories"):
            await assign_categories(
                work,
                CategoryAssignmentInput(
                    expected_version=1,
                    categories=setup.categories,
                    valid_from=setup.effective_from,
                ),
            )
        await work.db.flush()
    if setup.manufacturer is not None:
        with setup_field("manufacturer"):
            await assign_manufacturer(work, setup.manufacturer)
        await work.db.flush()
    if setup.batch_enabled is not None:
        from catalog.tasks.product_stock_choice import capture

        with setup_field("batch_enabled"):
            await capture(work, setup.batch_enabled, setup.effective_from)
        await work.db.flush()
    if setup.tax is not None or setup.prices:
        with setup_field("tax" if setup.tax is not None else "prices"):
            return await commercial_setup(work, setup, state)
    return []


async def commercial_setup(
    work: ProductWork, setup: InitialProductSetup, state: CatalogPolicyState
) -> list[uuid.UUID]:
    from catalog.tasks import pricing_foundation as foundation
    from catalog.tasks import pricing_publication as publication
    from catalog.tasks import tax_commands

    assert work.item is not None
    pricing = PricingWork(work.access, state)
    price_ids: list[uuid.UUID] = []
    expectations = {
        "expected_generation": setup.expected_generation,
        "expected_source_version": setup.expected_source_version,
        "valid_from": setup.effective_from,
    }
    if setup.tax is not None:
        work.actor.require_scope("tax_rule.publish", target=ScopePath(company_id=work.company))
        tax_work = tax_commands.TaxWork(work.access, state)
        scope = await tax_commands.create_scope(
            tax_work, t.ScopeInput(owner_kind="SKU", item_id=work.item.id), None
        )
        for direction in setup.tax.directions:
            for bundle, key in (("CLASSIFICATION", "classification_id"), ("RULE", "rule_id")):
                selected = getattr(setup.tax, key)
                if selected is not None:
                    await tax_commands.publish_binding(
                        tax_work,
                        t.BindingInput.model_validate(
                            {
                                **expectations,
                                "scope_id": scope.id,
                                "direction": direction,
                                "bundle": bundle,
                                "mode": "OVERRIDE",
                                key: selected,
                            }
                        ),
                        None,
                    )
            if setup.tax.rule_id is not None:
                rule = await row(work.access, TaxRule, setup.tax.rule_id)
                await tax_commands.publish_binding(
                    tax_work,
                    t.BindingInput.model_validate(
                        {
                            **expectations,
                            "scope_id": scope.id,
                            "direction": direction,
                            "bundle": "TREATMENT",
                            "mode": "OVERRIDE",
                            "treatment": rule.treatment,
                            "tax_category_id": rule.tax_category_id,
                            **(
                                {"exemption_reason": rule.source_reference}
                                if rule.treatment in {"EXEMPT", "NON_GST"}
                                else {}
                            ),
                        }
                    ),
                    None,
                )
        await tax_work.validate()
        for entity, fields in tax_work.changed.items():
            work.changed.setdefault(entity, set()).update(fields)
    if setup.prices:
        assert work.item is not None
        revisions = list(
            await work.db.scalars(
                select(ItemUnitRevision)
                .join(ItemUnitBinding, ItemUnitBinding.id == ItemUnitRevision.binding_id)
                .where(
                    ItemUnitBinding.item_id == work.item.id, ItemUnitBinding.usage_role == "BASE"
                )
                .limit(2)
            )
        )
        if len(revisions) != 1:
            raise ValidationFailedError("initial prices require exactly one base unit binding")
        revision = revisions[0]
        scope = await foundation.create_scope(pricing, p.ScopeInput(item_id=work.item.id), None)
        numerics: dict[tuple[str, int], PricingRow] = {}
        for price in setup.prices:
            plan = await row(work.access, PricePlan, price.plan_id)
            numeric_key = (plan.currency, price.price_decimal_places)
            if numeric_key not in numerics:
                if any(key[0] == plan.currency for key in numerics):
                    raise ValidationFailedError("prices in one currency require the same precision")
                numerics[numeric_key] = await foundation.create_numeric(
                    pricing,
                    p.NumericInput.model_validate(
                        {
                            **expectations,
                            "item_id": work.item.id,
                            "unit_revision_id": revision.id,
                            "currency": plan.currency,
                            "price_decimal_places": price.price_decimal_places,
                        }
                    ),
                    None,
                )
            series = await foundation.create_series(
                pricing,
                p.SeriesInput(
                    plan_id=plan.id, price_scope_id=scope.id, unit_revision_id=revision.id
                ),
                None,
            )
            draft = await publication.save_draft(
                pricing,
                p.DraftInput(
                    series_id=series.id,
                    numeric_revision_id=numerics[numeric_key].id,
                    valid_from=setup.effective_from,
                    price_method="FIXED",
                    amount=price.amount,
                    price_basis_quantity=price.price_basis_quantity,
                ),
                None,
            )
            price_ids.append(draft.id)
    for entity, fields in pricing.changed.items():
        work.changed.setdefault(entity, set()).update(fields)
    return price_ids

"""Native, scoped BOM fixtures including all six tables and exact child quantities."""

import datetime as dt
from decimal import Decimal

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7

from catalog.models.boms import Bom, BomAssignment, BomComponent, BomDraft, BomOutput, BomRevision
from tests.product_definition_factories import seed_definitions


async def physical_bom_sources(factory, tenant):
    from sqlalchemy import select

    from catalog.models import (
        CatalogDefaultProfile,
        InventoryProfileTemplateRevision,
        Item,
        ItemUnitBinding,
        ItemUnitRevision,
    )
    from tests.inventory_factories import seed_template
    from tests.product_integrity_factories import features

    company, ids = await seed_definitions(factory, tenant)
    _, template_id = await seed_template(factory, tenant, company)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            template = await db.get(InventoryProfileTemplateRevision, template_id)
            assert template is not None
            template.published_at = utcnow()
            for profile in await db.scalars(
                select(CatalogDefaultProfile).where(CatalogDefaultProfile.company_id == company)
            ):
                profile.inventory_template_revision_mode = "VALUE"
                profile.inventory_template_revision_id = template_id
            item = await db.get(Item, ids["item"])
            assert item is not None
            output = Item(
                tenant_id=tenant,
                company_id=company,
                family_id=item.family_id,
                sku="FINISHED",
                name="Finished goods",
                base_unit_id=item.base_unit_id,
                status="DRAFT",
                sellable=True,
                purchasable=False,
            )
            db.add(output)
            await db.flush()
            binding = ItemUnitBinding(
                tenant_id=tenant,
                company_id=company,
                item_id=output.id,
                unit_id=output.base_unit_id,
                code="BASE",
                usage_role="BASE",
            )
            db.add(binding)
            await db.flush()
            unit = ItemUnitRevision(
                tenant_id=tenant,
                company_id=company,
                binding_id=binding.id,
                revision=1,
                conversion_mode="FIXED",
                numerator=1,
                denominator=1,
                quantity_decimal_places=0,
                quantity_increment=Decimal("1"),
                fractional_entry=False,
                valid_from=dt.date(2090, 1, 1),
            )
            db.add(unit)
            await db.flush()
            ids.update(output_item=output.id, output_unit_revision=unit.id)
    await features(factory, tenant, company, ids["actor_user"], {"inventory", "bom_definitions"})
    return company, ids


async def seed_bom(factory, tenant):
    company, sources = await seed_definitions(factory, tenant)
    common = {"tenant_id": tenant, "company_id": company}
    values = {
        "specification": "Single-level fixture",
        "change_reason": "Initial definition",
        "definition_date": dt.date(2090, 1, 1),
        "component_count": 0,
        "output_count": 1,
    }
    with tenant_scope(tenant):
        async with factory.begin() as db:
            bom = Bom(**common, code="RECIPE", name="Recipe")
            db.add(bom)
            await db.flush()
            draft = BomDraft(**common, bom_id=bom.id, draft_number=1, status="DRAFT", **values)
            db.add(draft)
            await db.flush()
            revision = BomRevision(
                **common,
                bom_id=bom.id,
                draft_id=draft.id,
                revision=1,
                status="PUBLISHED",
                published_at=utcnow(),
                policy_generation=1,
                source_version=1,
                content_sha256="a" * 64,
                dependency_manifest={"schema": 1},
                **values,
            )
            db.add(revision)
            await db.flush()
            draft.status, draft.published_revision_id = "PUBLISHED", revision.id
            output = BomOutput(
                **common,
                revision_id=revision.id,
                draft_id=None,
                line_key=uuid7(),
                sequence=1,
                item_id=sources["item"],
                unit_revision_id=sources["item_unit_revision"],
                nominal_quantity=Decimal("10"),
                yield_fraction=Decimal("1"),
                role="PRIMARY",
            )
            # Separate next draft may start with partial components and no unit pin yet.
            next_draft = BomDraft(
                **common,
                bom_id=bom.id,
                draft_number=2,
                status="DRAFT",
                **{**values, "component_count": 1, "output_count": 0},
            )
            db.add_all((output, next_draft))
            await db.flush()
            component = BomComponent(
                **common,
                draft_id=next_draft.id,
                revision_id=None,
                line_key=uuid7(),
                sequence=1,
                item_id=sources["item"],
                unit_revision_id=None,
                quantity=Decimal("1.2500"),
                basis="NET_REQUIRED",
                loss_fraction=Decimal("0.125"),
                timing="PER_BASIS",
            )
            assignment = BomAssignment(
                **common,
                bom_revision_id=revision.id,
                item_id=sources["item"],
                warehouse_id=None,
                valid_from=dt.date(2090, 1, 1),
                change_reason="Default recipe",
            )
            db.add_all((component, assignment))
            await db.flush()
            return company, {
                "bom": bom.id,
                "bom_draft": draft.id,
                "bom_revision": revision.id,
                "bom_component": component.id,
                "bom_output": output.id,
                "bom_assignment": assignment.id,
                "next_draft": next_draft.id,
                "item": sources["item"],
                "unit_revision": sources["item_unit_revision"],
            }

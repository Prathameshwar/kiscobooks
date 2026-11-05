import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductTypeRevision, UnitConversion
from catalog.models.tax import TaxRate
from tests.bulk_factories import setup, unit_row
from tests.tax_factories import EVIDENCE, components
from tests.test_bulk_products_prices import reviewed_commit

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def row(
    key: str,
    resource: str,
    data: dict[str, Any],
    *,
    action: str = "CREATE",
    target: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "change_set": group or key,
        "resource": resource,
        "action": action,
        "target": {"record": target} if target else {},
        "data": data,
    }


def ref(key: str) -> dict[str, str]:
    return {"$ref": key, "field": "id"}


async def test_native_master_relations_lifecycle_and_type_publication_adapters(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    records = [
        unit_row("ea"),
        unit_row("box"),
        row(
            "canonical",
            "unit_conversion",
            {
                "from_unit_id": ref("ea"),
                "canonical_unit_id": ref("ea"),
                "numerator": 1,
                "denominator": 1,
            },
        ),
        row(
            "conversion",
            "unit_conversion",
            {
                "from_unit_id": ref("box"),
                "canonical_unit_id": ref("ea"),
                "numerator": 12,
                "denominator": 1,
            },
        ),
        row("pack", "pack_type", {"code": "BOX", "name": "Box"}, group="packs"),
        row("retire", "pack_type", {}, action="DEACTIVATE", target="pack", group="packs"),
        row("restore", "pack_type", {}, action="ACTIVATE", target="pack", group="packs"),
        row(
            "root",
            "item_group",
            {"code": "ROOT", "name": "Root", "valid_from": "2020-01-01"},
            group="groups",
        ),
        row(
            "child",
            "item_group",
            {"code": "CHILD", "name": "Child", "valid_from": "2020-01-01"},
            group="groups",
        ),
        row(
            "move",
            "item_group",
            {"parent_group_id": ref("root"), "effective_from": "2090-01-01"},
            action="MOVE",
            target="child",
            group="groups",
        ),
        row(
            "type",
            "product_type",
            {"code": "GENERAL", "name": "General", "kind": "GOODS"},
            group="type",
        ),
        row(
            "revision",
            "product_type_revision",
            {
                "product_type_id": ref("type"),
                "inventory_modes": ["STOCK"],
                "tracking_modes": ["NONE"],
                "unit_dimensions": ["COUNT"],
            },
            group="type",
        ),
        row(
            "publish",
            "product_type_revision",
            {},
            action="PUBLISH",
            target="revision",
            group="type",
        ),
    ]
    # Explicit order for the conversion graph; native validation requires the canonical root first.
    records[3]["depends_on"] = ["canonical"]
    await reviewed_commit(
        client, factory, tenant_a, company, user, auth, {"format": "JSON", "records": records}
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(UnitConversion.id)))) == 2
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            assert revision.published_at is not None


async def test_sourced_tax_definitions_publish_as_one_reviewed_change_set(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    records = [
        row("category", "tax_category", {"code": "TEST", "name": "Synthetic category"}),
        row(
            "rule",
            "tax_rule",
            {
                "code": "TEST",
                "name": "Synthetic goods",
                "item_kind": "GOODS",
                "treatment": "TAXABLE",
                "tax_category_id": ref("category"),
                **EVIDENCE,
            },
        ),
        row("series", "tax_rate_series", {"rule_id": ref("rule"), "applicability": "INTER_STATE"}),
        row(
            "rate",
            "tax_rate",
            {
                "series_id": ref("series"),
                "components": components("INTER_STATE"),
                "valid_from": "2090-01-01",
                **EVIDENCE,
            },
            action="PUBLISH",
        ),
    ]
    for record in records:
        record["change_set"] = "tax"
    await reviewed_commit(
        client, factory, tenant_a, company, user, auth, {"format": "JSON", "records": records}
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            published = (await db.scalars(select(TaxRate))).one()
            assert published.source_reference == EVIDENCE["source_reference"]


async def test_configuration_draft_update_and_publication_use_native_adapters(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from catalog.models.configuration import ProductConfigurationRevision

    company, user, auth = await setup(factory, tenant_a)
    records = [
        row("scope", "product_configuration_scope", {"scope_kind": "COMPANY"}, group="config"),
        row(
            "draft",
            "product_configuration_draft",
            {
                "scope_id": ref("scope"),
                "effective_from": "2090-01-01",
                "change_reason": "Reviewed defaults",
            },
            group="config",
        ),
        row(
            "update",
            "product_configuration_draft",
            {"options": {"brand_mode": "REQUIRED"}},
            action="UPDATE",
            target="draft",
            group="config",
        ),
        row(
            "publish",
            "product_configuration_draft",
            {},
            action="PUBLISH",
            target="draft",
            group="config",
        ),
    ]
    records[-1]["depends_on"] = ["update"]
    await reviewed_commit(
        client, factory, tenant_a, company, user, auth, {"format": "JSON", "records": records}
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(ProductConfigurationRevision.id)))) == 1

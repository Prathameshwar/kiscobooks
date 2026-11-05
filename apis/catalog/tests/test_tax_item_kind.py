"""Company and BOTH-group tax defaults keyed by product kind (mixed goods/services)."""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily
from catalog.models import tax as m
from catalog.models.tax_governance import TaxRuleApplicability
from tests.tax_factories import DATE, EVIDENCE, components, query, seed_tax
from tests.test_commercial_api import command_headers
from tests.test_tax_governance import release

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def add_services(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, ids: dict[str, uuid.UUID]
) -> dict[str, uuid.UUID]:
    """A service product plus a complete synthetic SAC definition in a goods company."""
    created: dict[str, uuid.UUID] = {}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            goods = await db.get(ProductFamily, ids["product_family"])
            assert goods is not None
            common = {"tenant_id": tenant, "company_id": goods.company_id, "row_version": 1}

            async def save(label: str, model: type[Any], /, **values: Any) -> Any:
                value = model(**common, **values)
                db.add(value)
                await db.flush()
                created[label] = value.id
                return value

            family = await save(
                "family",
                ProductFamily,
                code="SERVICE",
                name="Service",
                kind="SERVICE",
                product_type_revision_id=goods.product_type_revision_id,
                structure_mode="SIMPLE",
                status="DRAFT",
            )
            await save(
                "item",
                Item,
                family_id=family.id,
                default_slot=1,
                sku="SERVICE",
                name="Service",
                base_unit_id=ids["unit_of_measure"],
                sellable=True,
                purchasable=True,
                status="DRAFT",
            )
            rule = await save(
                "rule",
                m.TaxRule,
                code="SERVICE",
                name="Test services",
                item_kind="SERVICE",
                treatment="TAXABLE",
                tax_category_id=ids["tax_category"],
                tax_system="gst_in",
                jurisdiction="IN",
                is_active=True,
                **EVIDENCE,
            )
            await save(
                "classification",
                m.TaxClassification,
                jurisdiction="IN",
                code_system="SAC",
                code="995411",
                item_kind="SERVICE",
                description="Synthetic service classification",
                valid_from=DATE,
                valid_to=None,
                **EVIDENCE,
            )
            await save(
                "applicability",
                TaxRuleApplicability,
                rule_id=rule.id,
                code_system="SAC",
                code="995411",
                match_kind="EXACT",
            )
            for context in ("INTRA_STATE", "INTRA_UT", "INTER_STATE"):
                series = await save(
                    "series_" + context, m.TaxRateSeries, rule_id=rule.id, applicability=context
                )
                rate = await save(
                    "rate_" + context,
                    m.TaxRate,
                    series_id=series.id,
                    supersedes_id=None,
                    valid_from=DATE,
                    valid_to=None,
                    **EVIDENCE,
                )
                for position, entry in enumerate(components(context, "18")):
                    await save(
                        f"component_{context}_{position}",
                        m.TaxRateComponent,
                        rate_id=rate.id,
                        **entry,
                    )
    return created


def binding(
    ids: dict[str, uuid.UUID], key: str, bundle: str, value: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    return {
        "key": key,
        "kind": "BINDING",
        "definition": {
            "expected_generation": 1,
            "expected_source_version": 2,
            "scope_id": str(ids["catalog_tax_scope"]),
            "direction": "SALE",
            "bundle": bundle,
            "mode": "OVERRIDE",
            "valid_from": str(DATE),
            **value,
            **extra,
        },
    }


async def test_mixed_company_resolves_goods_and_services_defaults(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    services = await add_services(factory, tenant_a, ids)
    service_query = {**query(ids), "item_id": str(services["item"])}
    # The single all-kinds company default serves goods only; services are incompatible.
    blocked = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=service_query
    )
    assert blocked.status_code == 409, blocked.text
    changes = [
        entry
        for direction in ("SALE", "PURCHASE")
        for entry in (
            binding(
                ids,
                "classification_" + direction,
                "CLASSIFICATION",
                {"classification_id": str(services["classification"])},
                item_kind="SERVICE",
                direction=direction,
            ),
            binding(
                ids,
                "rule_" + direction,
                "RULE",
                {"rule_id": str(services["rule"])},
                item_kind="SERVICE",
                direction=direction,
            ),
        )
    ]
    body = {
        "expected_generation": 1,
        "expected_source_version": 2,
        "change_reason": "Synthetic services default",
        "changes": changes,
    }
    published = await release(client, root, auth, body)
    assert published["policy_generation"] == 2
    goods = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert goods.status_code == 200 and goods.json()["status"] == "COMPLETE", goods.text
    assert goods.json()["rule_id"] == str(ids["tax_rule"])
    assert goods.json()["classification_code"] == "1234"
    service = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=service_query
    )
    assert service.status_code == 200 and service.json()["status"] == "COMPLETE", service.text
    assert service.json()["rule_id"] == str(services["rule"])
    assert service.json()["classification_code"] == "995411"
    listed = await client.get(
        root + "/tax-bindings", headers=auth, params={"scope_id": str(ids["catalog_tax_scope"])}
    )
    assert listed.status_code == 200, listed.text
    kinds = sorted(str(entry["item_kind"]) for entry in listed.json()["items"])
    assert kinds.count("SERVICE") == 4 and kinds.count("None") == 6
    # A second services default for the same key overlaps its own history.
    again = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **changes[1]["definition"],
            "expected_generation": 2,
            "valid_from": "2091-01-01",
        },
    )
    assert again.status_code == 409, again.text


async def test_binding_kind_must_match_scope_and_selected_definition(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    services = await add_services(factory, tenant_a, ids)
    common = {
        "expected_generation": 1,
        "expected_source_version": 2,
        "scope_id": str(ids["catalog_tax_scope"]),
        "direction": "PURCHASE",
        "mode": "OVERRIDE",
        "valid_from": "2091-01-01",
    }
    for bundle, value, kind in (
        ("RULE", {"rule_id": str(services["rule"])}, "GOODS"),
        ("CLASSIFICATION", {"classification_id": str(ids["tax_classification"])}, "SERVICE"),
    ):
        result = await client.post(
            root + "/tax-bindings",
            headers=command_headers(auth),
            json={**common, "bundle": bundle, **value, "item_kind": kind},
        )
        assert result.status_code == 422, result.text
    scope = await client.post(
        root + "/tax-scopes",
        headers=command_headers(auth),
        json={"owner_kind": "FAMILY", "family_id": str(ids["product_family"])},
    )
    assert scope.status_code == 201, scope.text
    result = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **common,
            "expected_generation": scope.json()["policy_generation"],
            "scope_id": scope.json()["id"],
            "bundle": "TREATMENT",
            "treatment": "TAXABLE",
            "tax_category_id": str(ids["tax_category"]),
            "item_kind": "SERVICE",
        },
    )
    assert result.status_code == 422, result.text
    invalid = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={**common, "bundle": "RULE", "rule_id": str(ids["tax_rule"]), "item_kind": "WARE"},
    )
    assert invalid.status_code == 422, invalid.text

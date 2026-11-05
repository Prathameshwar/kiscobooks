import uuid
from typing import Any

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create
from tests.tax_factories import EVIDENCE, components, query, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_tax_mutations_require_auth_scope_and_strict_input(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    denied = headers(company, tenant=tenant_a, user=ids["actor_user"], permission=["item.read"])
    dated = {"valid_from": "2091-01-01", "expected_generation": 1, "expected_source_version": 2}
    cases: list[tuple[str, str, dict[str, Any]]] = [
        (
            "POST",
            "/tax-classifications",
            {
                **dated,
                **EVIDENCE,
                "code_system": "HSN",
                "code": "5678",
                "description": "Synthetic",
                "item_kind": "GOODS",
            },
        ),
        ("POST", "/tax-categories", {"code": "NEW", "name": "New"}),
        (
            "PATCH",
            "/tax-categories/" + str(ids["tax_category"]),
            {"expected_version": 1, "name": "Changed", "is_active": True},
        ),
        (
            "POST",
            "/tax-rules",
            {
                **EVIDENCE,
                "code": "NEW",
                "name": "New",
                "item_kind": "GOODS",
                "treatment": "TAXABLE",
                "tax_category_id": str(ids["tax_category"]),
            },
        ),
        (
            "PATCH",
            "/tax-rules/" + str(ids["tax_rule"]),
            {"expected_version": 1, "name": "Changed", "is_active": True},
        ),
        (
            "POST",
            "/tax-rate-series",
            {"rule_id": str(ids["tax_rule"]), "applicability": "INTER_STATE"},
        ),
        (
            "POST",
            "/tax-rates",
            {
                **dated,
                **EVIDENCE,
                "series_id": str(ids["series_INTER_STATE"]),
                "components": components("INTER_STATE"),
            },
        ),
        ("POST", "/tax-scopes", {"owner_kind": "SKU", "item_id": str(ids["item"])}),
        (
            "POST",
            "/tax-bindings",
            {
                **dated,
                "scope_id": str(ids["catalog_tax_scope"]),
                "bundle": "RULE",
                "direction": "SALE",
                "mode": "INHERIT",
            },
        ),
    ]
    for method, path, body in cases:
        for supplied, expected in (({}, 401), (denied, 403), (auth, 422)):
            result = await client.request(
                method,
                root + path,
                headers=command_headers(supplied),
                json={**body, **({"unknown": True} if expected == 422 else {})},
            )
            assert result.status_code == expected, (path, result.text)
        wrong = await client.request(
            method, f"/v1/companies/{uuid.uuid4()}" + path, headers=command_headers(auth), json=body
        )
        assert wrong.status_code == 403, (path, wrong.text)
    no_publish = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"tax_rule.publish"}),
    )
    result = await client.post(
        root + cases[6][1], headers=command_headers(no_publish), json=cases[6][2]
    )
    assert result.status_code == 403, result.text


async def test_tax_field_denies_hold_for_reads_filters_and_resolution(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    for version, entity, field, path, params in (
        (3, "tax_rate", "series_id", "tax-rates", {"series_id": str(ids["tax_rate_series"])}),
        (4, "tax_rate", "valid_from", "tax-rates", {"as_of": "2090-01-01"}),
        (5, "tax_category", "code", "tax-categories", {"q": "TEST"}),
    ):
        await policy(
            factory,
            tenant_a,
            company,
            ids["actor_user"],
            "catalog." + entity,
            field,
            "read",
            version=version,
        )
        response = await client.get(root + "/" + path, headers=auth, params=params)
        assert response.status_code == 403, response.text
        result = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert result.status_code == 403, result.text


async def test_unused_tax_masters_can_retire_and_names_must_be_printable(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    category = await create(
        client, root, auth, "/tax-categories", {"code": "UNUSED", "name": "Unused"}
    )
    rule = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            **EVIDENCE,
            "code": "UNUSED",
            "name": "Unused",
            "item_kind": "GOODS",
            "treatment": "EXEMPT",
            "tax_category_id": category["id"],
        },
    )
    for name in ("   ", "bad\nname"):
        result = await client.patch(
            root + "/tax-rules/" + rule["id"],
            headers=command_headers(auth),
            json={"name": name, "expected_version": 1, "is_active": True},
        )
        assert result.status_code == 422, result.text
    result = await client.patch(
        root + "/tax-rules/" + rule["id"],
        headers=command_headers(auth),
        json={"name": "Retired", "expected_version": 1, "is_active": False},
    )
    assert result.status_code == 200, result.text
    fresh = await create(client, root, auth, "/tax-categories", {"code": "EMPTY", "name": "Empty"})
    result = await client.patch(
        root + "/tax-categories/" + fresh["id"],
        headers=command_headers(auth),
        json={"name": "Retired", "expected_version": 1, "is_active": False},
    )
    assert result.status_code == 200, result.text

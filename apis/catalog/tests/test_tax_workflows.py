import datetime as dt
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import tax as m
from tests.pricing_factories import create, guard
from tests.product_review_factories import changed
from tests.tax_factories import DATE, EVIDENCE, components, query, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_tax_resolution_preserves_contexts_and_distinguishes_missing_and_exempt(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    result = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["status"] == "COMPLETE" and value["treatment"] == "TAXABLE"
    assert {entry["applicability"] for entry in value["rates"]} == {
        "INTRA_STATE",
        "INTRA_UT",
        "INTER_STATE",
    }
    assert value["transaction_determination_required"] is True and value["sources"]
    async with changed(
        factory, tenant_a, m.TaxRate, ids["rate_INTER_STATE"], valid_from=dt.date(2091, 1, 1)
    ):
        missing = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert missing.json()["missing"] == ["rate:INTER_STATE"]
    async with changed(
        factory,
        tenant_a,
        m.CatalogTaxBinding,
        ids["binding_SALE_RULE"],
        mode="REQUIRE_EXPLICIT",
        rule_id=None,
    ):
        blocked = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert blocked.json()["status"] == "REQUIRE_EXPLICIT", blocked.text


async def test_tax_publication_is_dated_atomic_and_replayable(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert current.status_code == 200, current.text
    body = {
        **guard(current.json()),
        **EVIDENCE,
        "series_id": str(ids["series_INTER_STATE"]),
        "valid_from": "2091-01-01",
        "supersedes_id": str(ids["rate_INTER_STATE"]),
        "expected_previous_version": 1,
        "components": components("INTER_STATE", "5"),
    }
    preview = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert preview.status_code == 200 and preview.json()["valid"], preview.text
    request = command_headers(auth)
    published = await client.post(root + "/tax-rates", headers=request, json=body)
    assert published.status_code == 201, published.text
    replay = await client.post(root + "/tax-rates", headers=request, json=body)
    assert (
        replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    old = await client.get(root + "/tax-rates/" + str(ids["rate_INTER_STATE"]), headers=auth)
    assert old.json()["valid_to"] == "2090-12-31"
    history = await client.get(root + "/tax-rates", headers=auth, params={"as_of": "2091-01-01"})
    assert history.status_code == 200 and len(history.json()["items"]) == 3, history.text
    stale = await client.post(root + "/tax-rates", headers=command_headers(auth), json=body)
    assert stale.status_code == 409, stale.text


async def test_tax_authoring_company_defaults_and_immutable_masters(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.pricing_factories import setup_pricing

    root, auth, ids = await setup_pricing(factory, tenant_a)
    category = await create(
        client, root, auth, "/tax-categories", {"code": "SERV", "name": "Service"}
    )
    rule = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            "code": "SERV",
            "name": "Services",
            "classifications": [{"code_system": "HSN", "code": "1234", "match_kind": "EXACT"}],
            "item_kind": "GOODS",
            "treatment": "TAXABLE",
            "tax_category_id": category["id"],
            **EVIDENCE,
        },
    )
    classification = await create(
        client,
        root,
        auth,
        "/tax-classifications",
        {
            **guard(rule),
            "valid_from": str(DATE),
            "code_system": "HSN",
            "code": "1234",
            "item_kind": "GOODS",
            "description": "Synthetic test",
            **EVIDENCE,
        },
    )
    scope = await create(client, root, auth, "/tax-scopes", {"owner_kind": "COMPANY"})
    last = scope
    for bundle, fields in (
        ("CLASSIFICATION", {"classification_id": classification["id"]}),
        ("TREATMENT", {"treatment": "TAXABLE", "tax_category_id": category["id"]}),
        ("RULE", {"rule_id": rule["id"]}),
    ):
        last = await create(
            client,
            root,
            auth,
            "/tax-bindings",
            {
                **guard(last),
                "scope_id": scope["id"],
                "direction": "SALE",
                "bundle": bundle,
                "mode": "OVERRIDE",
                "valid_from": str(DATE),
                **fields,
            },
        )
    for context in ("INTRA_STATE", "INTRA_UT", "INTER_STATE"):
        series = await create(
            client,
            root,
            auth,
            "/tax-rate-series",
            {"rule_id": rule["id"], "applicability": context},
        )
        await create(
            client,
            root,
            auth,
            "/tax-rates",
            {
                **guard(series),
                **EVIDENCE,
                "series_id": series["id"],
                "valid_from": str(DATE),
                "components": components(context),
            },
        )
    resolved = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids)
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "COMPLETE", resolved.text
    for resource, identity in (("tax-categories", category["id"]), ("tax-rules", rule["id"])):
        renamed = await client.patch(
            root + "/" + resource + "/" + identity,
            headers=command_headers(auth),
            json={"expected_version": 1, "name": "Renamed", "is_active": True},
        )
        assert renamed.status_code == 200, renamed.text
        retired = await client.patch(
            root + "/" + resource + "/" + identity,
            headers=command_headers(auth),
            json={"expected_version": 2, "name": "Renamed", "is_active": False},
        )
        assert retired.status_code == 409, retired.text


async def test_cbic_hsn_sac_directory_search_and_lookup(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, current, _ = await seed_tax(factory, tenant_a)

    # 1. Search by query "phone"
    res = await client.get(f"{root}/tax-reference/hsn-sac", headers=current, params={"q": "phone"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["count"] >= 1
    codes = [item["code"] for item in data["items"]]
    assert "8517" in codes or "85171200" in codes

    # 2. Filter by code_system "SAC"
    res_sac = await client.get(
        f"{root}/tax-reference/hsn-sac", headers=current, params={"code_system": "SAC"}
    )
    assert res_sac.status_code == 200
    for item in res_sac.json()["items"]:
        assert item["code_system"] == "SAC"
        assert item["item_kind"] == "SERVICE"

    # 3. Filter by chapter "30" (Pharma)
    res_pharma = await client.get(
        f"{root}/tax-reference/hsn-sac", headers=current, params={"chapter": "30"}
    )
    assert res_pharma.status_code == 200
    for item in res_pharma.json()["items"]:
        assert item["chapter"] == "30"
        assert item["code"].startswith("30")

    # 4. Lookup exact code
    res_exact = await client.get(f"{root}/tax-reference/hsn-sac/85171200", headers=current)
    assert res_exact.status_code == 200
    entry = res_exact.json()
    assert entry["code"] == "85171200"
    assert entry["chapter"] == "85"
    assert entry["item_kind"] == "GOODS"
    assert entry["gst_rate_default"] is None

    # 5. Lookup nonexistent code
    res_404 = await client.get(f"{root}/tax-reference/hsn-sac/00000000", headers=current)
    assert res_404.status_code == 404

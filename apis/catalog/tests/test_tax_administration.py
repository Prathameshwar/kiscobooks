"""Tax masters participate in native administration and preserve scoped authority."""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import guard
from tests.tax_factories import query, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_tax_governance import rates

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_tax_master_options_mappings_and_usage(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    for resource, source in (
        ("tax_category", "tax_categories"),
        ("tax_rule", "tax_rules"),
        ("tax_classification", "tax_classifications"),
    ):
        options = await client.get(
            root + "/option-sources/catalog." + source,
            headers=auth,
            params={"as_of": "2090-01-01"} if resource == "tax_classification" else {},
        )
        assert options.status_code == 200, options.text
        assert options.json()["items"][0]["value"] == str(ids[resource])
        master = root + "/masters/catalog." + resource
        for path, body in (
            ("aliases", {"alias": "Synthetic tax"}),
            ("external-keys", {"source_namespace": "review", "external_key": "tax"}),
        ):
            created = await client.post(
                master + "/" + str(ids[resource]) + "/" + path,
                headers=command_headers(auth),
                json=body,
            )
            assert created.status_code == 201, created.text
            found = await client.get(master + "/" + path + "/resolve", headers=auth, params=body)
            assert found.status_code == 200 and found.json()["target_id"] == str(
                ids[resource]
            ), found.text
        usage = await client.get(
            master + "/" + str(ids[resource]) + "/usage-relations", headers=auth
        )
        assert usage.status_code == 200 and usage.json()["relations"], (resource, usage.text)
    result = await client.post(
        root + "/tax-impact-previews",
        headers=auth,
        json={"resource": "tax_rule", "target_id": str(ids["tax_rule"]), "as_of": "2090-01-01"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["affected_item_ids"] == [str(ids["item"])]
    assert all(entry["status"] == "COMPLETE" for entry in result.json()["impact"])


async def test_tax_release_and_withdrawal_require_scoped_publish_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    _, _, foreign = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    generation = guard(current.json())
    body: dict[str, Any] = {
        **generation,
        "change_reason": "Synthetic",
        "changes": rates(ids, generation),
    }
    denied = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"tax_rule.publish"}),
    )
    withdrawal = {
        **generation,
        "resource": "tax_rate",
        "target_id": str(ids["rate_INTER_STATE"]),
        "expected_version": 1,
        "reason": "Synthetic",
    }
    for path, payload in (
        ("tax-release-previews", body),
        ("tax-releases", {**body, "preview_token": "synthetic-unsigned-token"}),
        ("tax-withdrawals", withdrawal),
    ):
        assert (await client.post(root + "/" + path, json=payload)).status_code == 401
        result = await client.post(root + "/" + path, headers=command_headers(denied), json=payload)
        assert result.status_code == 403, result.text
    body["changes"][0]["definition"]["series_id"] = str(foreign["series_INTRA_STATE"])
    result = await client.post(root + "/tax-release-previews", headers=auth, json=body)
    assert result.status_code == 403, result.text
    result = await client.post(
        root + "/tax-withdrawals",
        headers=command_headers(auth),
        json={**withdrawal, "target_id": str(foreign["rate_INTER_STATE"])},
    )
    assert result.status_code == 403, result.text


async def test_applicability_and_impact_require_current_authority_and_company_scope(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    _, _, foreign = await seed_tax(factory, tenant_a)
    for path, permission, identity, body in (
        (
            "tax-rule-applicabilities",
            "tax_rule.manage",
            "rule_id",
            {
                "rule_id": str(ids["tax_rule"]),
                "code_system": "HSN",
                "code": "5678",
            },
        ),
        (
            "tax-impact-previews",
            "tax_rule.read",
            "target_id",
            {
                "resource": "tax_rule",
                "target_id": str(ids["tax_rule"]),
                "as_of": "2090-01-01",
            },
        ),
    ):
        denied = headers(
            uuid.UUID(root.rsplit("/", 1)[1]),
            tenant=tenant_a,
            user=ids["actor_user"],
            permission=sorted(CATALOG_PERMISSIONS - {permission}),
        )
        assert (await client.post(root + "/" + path, json=body)).status_code == 401
        result = await client.post(root + "/" + path, headers=command_headers(denied), json=body)
        assert result.status_code == 403, result.text
        result = await client.post(
            root + "/" + path,
            headers=command_headers(auth),
            json={**body, identity: str(foreign["tax_rule"])},
        )
        assert result.status_code == 403, result.text

import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.bulk_factories import post, setup, unit_row
from tests.test_api import headers
from tests.test_unit_api import policy, seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_all_bulk_operations_require_current_authority_and_protect_job_membership(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    app: FastAPI,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    path = root + "/" + job["id"]
    restricted = headers(company, tenant=tenant_a, user=user, permission="item.read")
    requests: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", root, None),
        ("GET", path, None),
        ("GET", path + "/records", None),
        ("GET", path + "/records/" + str(uuid7()), None),
        ("GET", root + "/templates?resource=unit_of_measure", None),
        ("GET", path + "/report-ticket", None),
        ("GET", path + "/report?token=invalid", None),
        ("POST", root, {"format": "JSON", "records": [unit_row("box")]}),
        ("POST", path + "/validate", {"expected_version": 1}),
        ("POST", path + "/commit", {"expected_version": 1, "selection_digest": "a" * 64}),
        ("POST", path + "/cancel", {"expected_version": 1}),
        ("POST", path + "/revise", {"expected_version": 1, "batch": {"records": [unit_row("ea")]}}),
    ]
    for method, url, body in requests:
        for actor_headers, status in (({}, 401), (restricted, 403)):
            response = await client.request(
                method, url, headers={**actor_headers, "Idempotency-Key": str(uuid7())}, json=body
            )
            assert response.status_code == status, (method, url, response.text)
    foreign_actor = headers(
        company, tenant=tenant_a, user=uuid7(), permission=["catalog.bulk.read"]
    )
    assert (await client.get(path, headers=foreign_actor)).status_code == 403
    assert (await client.get(path + "/records/" + str(uuid7()), headers=auth)).status_code == 403
    template = await client.get(root + "/templates?resource=unit_of_measure", headers=auth)
    assert template.status_code == 200 and template.json()["schema_version"] == 1
    app.state.pricing_limiter = SimpleNamespace(allow=lambda *args, **kwargs: False)
    assert (
        await client.post(
            root,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"format": "JSON", "records": [unit_row("box")]},
        )
    ).status_code == 429


async def test_denied_bulk_metadata_and_template_fields_are_unavailable(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        (policy(user, "state", "read", entity="catalog.bulk_job"), policy(user, "name", "read")),
        version=3,
    )
    for suffix in ("", "/" + job["id"], "/templates?resource=unit_of_measure"):
        response = await client.get(root + suffix, headers=auth)
        assert response.status_code == 403, response.text


async def test_release_metadata_marks_native_history_and_bulk_evidence_readonly(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    expected = {
        "item_price": {"amount", "series_id", "row_version"},
        "product_type_revision": {"revision", "product_type_id", "kind", "published_at"},
        "attribute_set_revision": {"revision", "attribute_set_id", "published_at"},
        "attribute_set_member": {"revision_id"},
        "identifier_profile": {"normalization_version"},
        "identifier_profile_requirement": {"profile_id"},
        "inventory_profile_template_revision": {"template_id", "revision", "published_at"},
        "warranty_policy_revision": {"policy_id", "revision", "published_at"},
        "return_policy_revision": {"policy_id", "revision", "published_at", "condition_count"},
        "return_policy_condition": {"revision_id"},
        "handling_profile_revision": {"profile_id", "revision", "published_at"},
        "bulk_job": {"state", "row_version", "input_hash"},
    }
    for entity, fields in expected.items():
        response = await client.get(
            f"/v1/companies/{company}/entities/catalog.{entity}/field-set", headers=auth
        )
        assert response.status_code == 200, response.text
        actual = {x["key"]: x for x in response.json()["fields"]}
        assert fields <= actual.keys(), entity
        assert all(not actual[field]["writable"] for field in fields), entity
        if entity == "bulk_job":
            assert "identity_digest" not in actual and "selected_keys" not in actual

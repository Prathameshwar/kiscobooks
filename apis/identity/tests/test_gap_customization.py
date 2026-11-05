from __future__ import annotations

import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CustomFieldValueIndex
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies, seed_two_tenants
from tests.test_api_companies import _valid_company_body

PERMISSIONS = [
    "company.read",
    "company.update",
    "company.create",
    "custom_field.manage",
    "field_config.manage",
    "field_policy.manage",
]


async def test_custom_validation_indexed_search_layout_and_field_denial(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    admin, reader = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=reader))
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMISSIONS)])
    body = {
        "label": "Segment",
        "definition": {
            "key": "cf_segment",
            "data_type": "text",
            "is_searchable": True,
            "validation": {"max_length": 20},
        },
    }
    response = await client.post("/v1/custom-field-definitions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    did = response.json()["id"]
    url = f"/v1/companies/{company}"
    response = await client.patch(
        url, headers=headers, json={"custom_fields": {"cf_segment": "retail"}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["custom_fields"] == {"cf_segment": "retail"}
    assert (
        await client.patch(url, headers=headers, json={"custom_fields": {"cf_segment": "x" * 21}})
    ).status_code == 422
    assert (
        await client.patch(url, headers=headers, json={"custom_fields": {"cf_unknown": 1}})
    ).status_code == 422
    listing = await client.get(
        "/v1/companies",
        headers=headers,
        params={"custom_field": "cf_segment", "custom_value": "retail"},
    )
    assert listing.status_code == 200, listing.text
    assert [r["id"] for r in listing.json()["items"]] == [str(company)]
    assert (
        await client.get(
            "/v1/companies",
            headers=headers,
            params={"custom_field": "cf_segment", "custom_value": "other"},
        )
    ).json()["items"] == []
    configured = await client.put(
        "/v1/entities/identity.company/field-config/custom_field:cf_segment",
        headers=headers,
        json={"label_override": "Market segment", "is_visible": False},
    )
    assert configured.status_code == 200, configured.text
    descriptors = (
        await client.get(
            "/v1/entities/identity.company/field-set",
            headers=headers,
            params={"company_id": str(company)},
        )
    ).json()["fields"]
    custom = next(d for d in descriptors if d["key"] == "custom_field:cf_segment")
    assert custom["label"] == "Market segment" and custom["is_visible"] is False
    # Hidden layout does not remove API data or reject writes.
    assert (await client.get(url, headers=headers)).json()["custom_fields"] == {
        "cf_segment": "retail"
    }
    denied = {
        "subject_type": "user",
        "subject_id": str(reader),
        "field_key": "custom_field:cf_segment",
        "access": "read",
        "effect": "deny",
        "reason": "restricted",
    }
    response = await client.post("/v1/field-policies", headers=headers, json=denied)
    assert response.status_code == 201, response.text
    reader_headers = actor_headers(
        tenant_id=tenant_a, user_id=reader, grants=[grant(["company.read", "company.update"])]
    )
    assert (await client.get(url, headers=reader_headers)).json()["custom_fields"] == {}
    assert (
        await client.get(
            "/v1/companies",
            headers=reader_headers,
            params={"custom_field": "cf_segment", "custom_value": "retail"},
        )
    ).status_code == 403
    denywrite = await client.post(
        "/v1/field-policies", headers=headers, json={**denied, "access": "write"}
    )
    assert denywrite.status_code == 201, denywrite.text
    assert (
        await client.patch(
            url, headers=reader_headers, json={"custom_fields": {"cf_segment": "trade"}}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/v1/field-policies", headers=headers, json={**denied, "subject_id": str(admin)}
        )
    ).status_code in {403, 422}
    assert (
        await client.get(
            f"/v1/custom-field-definitions/{did}",
            headers=actor_headers(tenant_id=tenant_b, user_id=uuid7(), grants=[grant(PERMISSIONS)]),
        )
    ).status_code == 404
    # Tightening a rule must validate stored values before it can commit.
    tightened = {**body, "definition": {**body["definition"], "validation": {"max_length": 3}}}
    assert (
        await client.put(f"/v1/custom-field-definitions/{did}", headers=headers, json=tightened)
    ).status_code == 422
    with tenant_scope(tenant_a):
        indexed = (await session.scalars(select(CustomFieldValueIndex))).one()
        assert indexed.value_text == "retail"


async def test_custom_autonumber_and_tenant_uniqueness(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMISSIONS)])
    definition = {
        "label": "Reference",
        "definition": {
            "key": "cf_ref",
            "data_type": "auto_number",
            "sequence_config": {"prefix": "ORG-", "padding": 3, "start": 1},
            "is_immutable_after_create": True,
        },
    }
    assert (
        await client.post("/v1/custom-field-definitions", headers=headers, json=definition)
    ).status_code == 201
    unique = {
        "label": "External ID",
        "definition": {
            "key": "cf_external",
            "data_type": "text",
            "is_searchable": True,
            "validation": {"max_length": 30, "unique_within": "tenant"},
        },
    }
    assert (
        await client.post("/v1/custom-field-definitions", headers=headers, json=unique)
    ).status_code == 201
    first = await client.post(
        "/v1/companies",
        headers=headers,
        json={**_valid_company_body("ONE"), "custom_fields": {"cf_external": "external-1"}},
    )
    assert first.status_code == 201, first.text
    assert first.json()["custom_fields"]["cf_ref"] == "ORG-001"
    duplicate = await client.post(
        "/v1/companies",
        headers=headers,
        json={**_valid_company_body("TWO"), "custom_fields": {"cf_external": "external-1"}},
    )
    assert duplicate.status_code == 409, duplicate.text
    second = await client.post(
        "/v1/companies",
        headers=headers,
        json={**_valid_company_body("TWO"), "custom_fields": {"cf_external": "external-2"}},
    )
    assert second.status_code == 201, second.text
    assert second.json()["custom_fields"]["cf_ref"] == "ORG-002"
    assert (
        await client.patch(
            f"/v1/companies/{first.json()['id']}",
            headers=headers,
            json={"custom_fields": {"cf_ref": "manual"}},
        )
    ).status_code == 422


async def test_field_metadata_respects_actor_lifecycle_and_posting_locks(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    from billing_platform.db.types import utcnow

    from identity.models import Company

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    reader = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read"])])
    editor = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read", "company.update"])]
    )
    url = f"/v1/entities/identity.company/field-set?company_id={company}"
    read_fields = (await client.get(url, headers=reader)).json()["fields"]
    assert not any(field["writable"] for field in read_fields)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        row.first_posted_at = utcnow()
        await session.commit()
    fields = {
        field["key"]: field for field in (await client.get(url, headers=editor)).json()["fields"]
    }
    assert fields["legal_name"]["writable"]
    assert not fields["amount_precision"]["writable"]
    with tenant_scope(tenant_a):
        row.status = "inactive"
        await session.commit()
    inactive_fields = (await client.get(url, headers=editor)).json()["fields"]
    assert not any(field["writable"] for field in inactive_fields)

"""Management form contracts, concurrency and persistence against real request sessions."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import build_field_policy, seed_two_companies
from tests.test_api_companies import _admin_headers, _valid_company_body

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("status", ["suspended", "closed"])
@pytest.mark.parametrize(
    "path,permission,body",
    [
        (
            "addresses",
            "company.update",
            {
                "type": "registered",
                "line1": "Office",
                "city": "Mumbai",
                "country_code": "IN",
                "state_code": "MH",
                "postal_code": "400001",
            },
        ),
        ("statutory-ids", "company.statutory_id.manage", {"kind": "pan", "value": "AAAPA1234A"}),
        (
            "licences",
            "company.licence.manage",
            {"kind": "drug_retail", "number": "DL-123", "valid_from": "2026-04-01"},
        ),
        (
            "tax-registrations",
            "company.tax_registration.manage",
            {
                "tax_system": "gst_in",
                "regime": "regular",
                "number": "27AAAPA1234A1ZT",
                "jurisdiction_code": "MH",
                "valid_from": "2026-04-01",
            },
        ),
    ],
)
async def test_inactive_company_refuses_new_setup_but_retains_historical_reads(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    status: str,
    path: str,
    permission: str,
    body: dict[str, str],
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        assert row is not None
        row.status = status
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant([permission, "company.read"])]
    )
    url = f"/v1/companies/{company}/{path}"
    refused = await client.post(url, headers=headers, json=body)
    assert refused.status_code == 409, refused.text
    history = await client.get(url, headers=headers)
    assert history.status_code == 200 and history.json()["items"] == []


@pytest.mark.parametrize("month,day", [(4, 31), (2, 30), (6, 31)])
async def test_fiscal_anchor_is_validated_before_create_or_merged_update(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    month: int,
    day: int,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    body = {
        **_valid_company_body("CAL"),
        "fiscal_year_start_month": month,
        "fiscal_year_start_day": day,
    }
    assert (await client.post("/v1/companies", headers=headers, json=body)).status_code == 422
    url = f"/v1/companies/{company}"
    assert (
        await client.patch(url, headers=headers, json={"fiscal_year_start_month": month})
    ).status_code == 200
    response = await client.patch(url, headers=headers, json={"fiscal_year_start_day": day})
    assert response.status_code == 422, response.text
    assert (await client.get(url, headers=headers)).json()["fiscal_year_start_day"] == 1


async def test_leap_day_anchor_is_supported(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    response = await client.post(
        "/v1/companies",
        headers=_admin_headers(tenant_a),
        json={
            **_valid_company_body("LEAP"),
            "fiscal_year_start_month": 2,
            "fiscal_year_start_day": 29,
        },
    )
    assert response.status_code == 201, response.text


async def test_detail_round_trips_document_text_and_edit_precondition(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    url = f"/v1/companies/{company}"
    previous = (await client.get(url, headers=headers)).json()
    first = await client.patch(
        url,
        headers=headers,
        json={
            "expected_updated_at": previous["updated_at"],
            "display_name": "First editor",
            "terms_and_conditions": "Payment due within thirty days.",
            "declaration_text": "Goods checked.",
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["terms_and_conditions"] == "Payment due within thirty days."
    assert first.json()["declaration_text"] == "Goods checked."
    stale = await client.patch(
        url,
        headers=headers,
        json={
            "expected_updated_at": previous["updated_at"],
            "display_name": "Stale editor",
        },
    )
    assert stale.status_code == 409, stale.text
    assert "Reload" in stale.json()["error"]["message"]
    assert (await client.get(url, headers=headers)).json()["display_name"] == "First editor"
    retry = await client.patch(
        url,
        headers=headers,
        json={
            "expected_updated_at": first.json()["updated_at"],
            "display_name": "Latest editor",
        },
    )
    assert retry.status_code == 200, retry.text


@pytest.mark.parametrize("status", ["suspended", "closed"])
async def test_nonactive_company_is_readable_but_not_editable(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    status: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        assert row
        row.status = status
        await session.commit()
    headers = _admin_headers(tenant_a)
    url = f"/v1/companies/{company}"
    assert (await client.get(url, headers=headers)).status_code == 200
    refused = await client.patch(url, headers=headers, json={"display_name": "New"})
    assert refused.status_code == 409


@pytest.mark.parametrize("value", ["   ", "Bad\nName", "Bad\x00Name"])
async def test_invalid_company_identity_is_rejected_on_create_and_update(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    value: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _admin_headers(tenant_a)
    body = {**_valid_company_body("OTHER"), "legal_name": value}
    assert (await client.post("/v1/companies", headers=headers, json=body)).status_code == 422
    assert (
        await client.patch(
            f"/v1/companies/{company}", headers=headers, json={"display_name": value}
        )
    ).status_code == 422


async def test_metadata_describes_native_validation_and_read_only_settings(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    response = await client.get(
        f"/v1/entities/identity.company/field-set?company_id={company}",
        headers=_admin_headers(tenant_a),
    )
    assert response.status_code == 200, response.text
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert fields["fiscal_year_start_month"]["data_type"] == "integer"
    assert fields["fiscal_year_start_month"]["validation"]["max"] == 12
    assert fields["books_begin_date"]["data_type"] == "date"
    assert fields["cash_receipt_limit"]["data_type"] == "decimal"
    assert fields["legal_name"]["validation"]["max_length"] == 255
    assert fields["entity_type"]["choices"]
    assert not fields["visibility"]["writable"]


async def test_precondition_rejects_naive_timestamp(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    response = await client.patch(
        f"/v1/companies/{company}",
        headers=_admin_headers(tenant_a),
        json={
            "expected_updated_at": "2026-10-23T10:30:00",
            "display_name": "New name",
        },
    )
    assert response.status_code == 422


async def test_create_only_actor_can_read_creation_metadata_not_existing_company(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create"])])
    url = "/v1/entities/identity.company/field-set"
    assert (await client.get(url, headers=headers)).status_code == 200
    assert (await client.get(url + f"?company_id={company}", headers=headers)).status_code == 403


async def test_management_can_list_redacted_visibility_without_filtering_it(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user = uuid7()
    with tenant_scope(tenant_a):
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=user,
                entity_type="identity.company",
                field_key="visibility",
                access="read",
            )
        )
        await session.commit()
    headers = _admin_headers(tenant_a, user)
    response = await client.get("/v1/companies?include_unlisted=true", headers=headers)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [str(company)]
    assert "visibility" not in response.json()["items"][0]
    assert (await client.get("/v1/companies", headers=headers)).status_code == 403

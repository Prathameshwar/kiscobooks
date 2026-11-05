"""HTTP tests for a company's tax registrations, statutory IDs, licences, addresses.

The AADHAAR test is the P4 exit criterion (docs/identity-db-plan.md §4): a full
restricted identifier submitted to the API must be absent from the response and from
every column of the persisted row — only the last four survive.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyStatutoryId
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_companies

pytestmark = pytest.mark.asyncio


def _headers(tenant_id: uuid.UUID, perms: list[str]) -> dict[str, str]:
    from billing_platform.ids import uuid7

    return actor_headers(tenant_id=tenant_id, user_id=uuid7(), grants=[grant(perms)])


# --- statutory ids: the redaction invariant ----------------------------------


async def test_business_identifier_stored_in_full(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/statutory-ids",
        json={"kind": "pan", "value": "AAAPA1234A"},
        headers=_headers(tenant_a, ["company.statutory_id.manage"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["value"] == "AAAPA1234A"  # business id: full value kept
    assert body["value_last4"] == "234A"


async def test_restricted_identifier_is_redacted_everywhere(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    full = "123456789012"
    resp = await client.post(
        f"/v1/companies/{company_a}/statutory-ids",
        json={"kind": "aadhaar", "value": full},
        headers=_headers(tenant_a, ["company.statutory_id.manage"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # The response never carries the full number.
    assert body["value"] is None
    assert body["value_last4"] == "9012"

    # The full number is absent from *every* column of the persisted row.
    with tenant_scope(tenant_a):
        row = await session.get(CompanyStatutoryId, uuid.UUID(body["id"]))
    assert row is not None
    assert row.value is None
    for column_value in vars(row).values():
        assert full not in str(column_value), "the full restricted number leaked into a column"


async def test_malformed_restricted_value_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/statutory-ids",
        json={"kind": "aadhaar", "value": "not-twelve-digits"},
        headers=_headers(tenant_a, ["company.statutory_id.manage"]),
    )
    assert resp.status_code == 422


async def test_statutory_id_without_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/statutory-ids",
        json={"kind": "pan", "value": "AAAPA1234A"},
        headers=_headers(tenant_a, ["company.read"]),
    )
    assert resp.status_code == 403


# --- tax registrations --------------------------------------------------------


def _gst_body(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "tax_system": "gst_in",
        "regime": "regular",
        "number": "27AAAPA1234A1ZT",
        "jurisdiction_code": "MH",
        "valid_from": "2026-04-01",
        "is_primary": True,
    }
    body.update(over)
    return body


async def test_add_tax_registration_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/tax-registrations",
        json=_gst_body(),
        headers=_headers(tenant_a, ["company.tax_registration.manage"]),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["tax_system"] == "gst_in"


async def test_overlapping_registration_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _headers(tenant_a, ["company.tax_registration.manage"])
    first = await client.post(
        f"/v1/companies/{company_a}/tax-registrations", json=_gst_body(), headers=headers
    )
    assert first.status_code == 201
    # A second open-ended registration for the same system/jurisdiction overlaps the
    # first — rejected at write as a conflict (409).
    second = await client.post(
        f"/v1/companies/{company_a}/tax-registrations",
        json=_gst_body(valid_from="2026-06-01"),
        headers=headers,
    )
    assert second.status_code == 409


async def test_wrong_jurisdiction_code_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/tax-registrations",
        json=_gst_body(jurisdiction_code="US-CA"),  # not a state of IN
        headers=_headers(tenant_a, ["company.tax_registration.manage"]),
    )
    assert resp.status_code == 422


# --- licences -----------------------------------------------------------------


async def test_add_licence_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/licences",
        json={
            "kind": "drug_licence_20b",
            "number": "MH-MUM-20B-4471",
            "valid_from": "2026-04-01",
            "valid_to": "2031-03-31",
        },
        headers=_headers(tenant_a, ["company.licence.manage"]),
    )
    assert resp.status_code == 201, resp.text


async def test_expiring_licence_without_valid_to_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A licence the profile marks ``has_expiry`` must carry an expiry date (LUT)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/licences",
        json={"kind": "lut", "number": "LUT-2026-01", "valid_from": "2026-04-01"},
        headers=_headers(tenant_a, ["company.licence.manage"]),
    )
    assert resp.status_code == 422


# --- addresses ----------------------------------------------------------------


async def test_add_address_happy_and_bad_jurisdiction(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _headers(tenant_a, ["company.update"])
    good = await client.post(
        f"/v1/companies/{company_a}/addresses",
        json={
            "type": "registered",
            "line1": "12 Marine Drive",
            "city": "Mumbai",
            "state_code": "MH",
            "postal_code": "400020",
            "country_code": "IN",
            "is_primary": True,
        },
        headers=headers,
    )
    assert good.status_code == 201, good.text
    bad = await client.post(
        f"/v1/companies/{company_a}/addresses",
        json={
            "type": "registered",
            "line1": "x",
            "city": "y",
            "state_code": "US-CA",
            "postal_code": "1",
            "country_code": "IN",
        },
        headers=headers,
    )
    assert bad.status_code == 422


async def test_cross_tenant_statutory_write_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Tenant B cannot even address tenant A's company — the session filter hides it."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/statutory-ids",
        json={"kind": "pan", "value": "AAAPA1234A"},
        headers=_headers(tenant_b, ["company.statutory_id.manage"]),
    )
    assert resp.status_code == 404

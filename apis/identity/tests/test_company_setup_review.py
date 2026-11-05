"""Regression tests for company setup references, currencies and pharmacy licences."""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company, CompanyLicence, Country, Currency, State
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_company_address,
    build_company_licence,
    build_country,
    build_currency,
    build_state,
    seed_two_companies,
    seed_two_tenants,
)
from tests.test_api_companies import _admin_headers, _valid_company_body

pytestmark = pytest.mark.asyncio


def headers(
    tenant: uuid.UUID, *permissions: str, company: uuid.UUID | None = None
) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant,
        user_id=uuid7(),
        grants=[
            grant(
                list(permissions),
                scope_type="company" if company else "tenant",
                scope_id=company,
            )
        ],
    )


def licence_body(**values: object) -> dict[str, object]:
    return {
        "kind": "drug_licence_20b",
        "number": "TEST-20B-001",
        "valid_from": "2026-04-01",
        "valid_to": "2027-03-31",
        **values,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"base_currency": "ZZZ"},
        {"reporting_currency": "ZZZ"},
        {"country_code": "ZZ"},
        {"state_code": "XX"},
        {"base_currency": None},
        {"country_code": None},
        {"state_code": None},
        {"default_tax_system": "vat_gb"},
    ],
)
async def test_invalid_setup_patch_is_validation_error_and_does_not_mutate(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    changes: dict[str, object],
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    response = await client.patch(
        f"/v1/companies/{company}", json=changes, headers=_admin_headers(tenant_a)
    )
    assert response.status_code == 422, response.text
    with tenant_scope(tenant_a):
        session.expire_all()
        row = await session.get(Company, company)
        assert row is not None
        assert (row.country_code, row.state_code, row.base_currency, row.reporting_currency) == (
            "IN",
            "MH",
            "INR",
            None,
        )


@pytest.mark.parametrize("model,code", [(Country, "IN"), (State, "MH"), (Currency, "INR")])
async def test_inactive_reference_not_selectable_but_existing_values_can_be_kept(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    model: type[Country] | type[State] | type[Currency],
    code: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    row = await session.get(model, code)
    assert isinstance(row, Country | State | Currency)
    row.is_active = False
    await session.commit()
    create = await client.post(
        "/v1/companies", json=_valid_company_body("NEW"), headers=_admin_headers(tenant_a)
    )
    assert create.status_code == 422, create.text
    unchanged = await client.patch(
        f"/v1/companies/{company}",
        headers=_admin_headers(tenant_a),
        json={
            "country_code": "IN",
            "state_code": "MH",
            "base_currency": "INR",
            "display_name": "New display",
        },
    )
    assert unchanged.status_code == 200, unchanged.text


async def test_currency_create_update_clear_and_posting_lock(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    session.add(build_currency("USD", name="US Dollar"))
    await session.commit()
    create = await client.post(
        "/v1/companies",
        headers=_admin_headers(tenant_a),
        json={**_valid_company_body(), "reporting_currency": "USD"},
    )
    assert create.status_code == 201, create.text
    assert create.json()["reporting_currency"] == "USD"
    company = uuid.UUID(create.json()["id"])
    patch = await client.patch(
        f"/v1/companies/{company}",
        headers=_admin_headers(tenant_a),
        json={"reporting_currency": None},
    )
    assert patch.status_code == 200 and patch.json()["reporting_currency"] is None
    with tenant_scope(tenant_a):
        row = await session.get(Company, company)
        assert row is not None
        row.first_posted_at = dt.datetime.now(dt.UTC)
        await session.commit()
    patch = await client.patch(
        f"/v1/companies/{company}", headers=_admin_headers(tenant_a), json={"base_currency": "USD"}
    )
    assert patch.status_code == 422


async def test_country_and_tax_system_are_validated_together(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    session.add_all([build_country("GB"), build_country("US")])
    await session.flush()
    session.add_all([build_state("GB-ENG", "GB"), build_state("US-CA", "US")])
    await session.commit()
    for changes in [
        {"default_tax_system": "vat_gb"},
        {"country_code": "US", "state_code": "US-CA"},
    ]:
        response = await client.post(
            "/v1/companies",
            json={**_valid_company_body(), **changes},
            headers=_admin_headers(tenant_a),
        )
        assert response.status_code == 422, response.text
    response = await client.post(
        "/v1/companies",
        headers=_admin_headers(tenant_a),
        json={
            **_valid_company_body(),
            "country_code": "GB",
            "state_code": "GB-ENG",
            "default_tax_system": "vat_gb",
        },
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("owner", ["other_company", "other_tenant", "missing", "inactive"])
async def test_licence_rejects_unusable_premises_without_writing(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    owner: str,
) -> None:
    company, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    address_id = uuid7()
    with unfiltered():
        if owner == "other_company":
            company_b = uuid7()
            session.add(build_company(tenant_id=tenant_a, company_id=company_b, code="SECOND"))
            await session.flush()
        if owner != "missing":
            address = build_company_address(
                tenant_id=tenant_b if owner == "other_tenant" else tenant_a,
                company_id=company if owner == "inactive" else company_b,
                is_active=owner != "inactive",
            )
            address_id = address.id
            session.add(address)
        await session.commit()
    response = await client.post(
        f"/v1/companies/{company}/licences",
        json=licence_body(premises_address_id=str(address_id)),
        headers=headers(tenant_a, "company.licence.manage", company=company),
    )
    assert response.status_code == 422, response.text
    assert "premises_address_id" in response.json()["error"]["fields"]
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CompanyLicence.id))) == 0


async def test_two_retail_licences_round_trip_with_correct_company_premises(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        address = build_company_address(tenant_id=tenant_a, company_id=company)
        session.add(address)
        await session.commit()
    for kind in ["drug_licence_20", "drug_licence_21"]:
        response = await client.post(
            f"/v1/companies/{company}/licences",
            json=licence_body(kind=kind, number=kind, premises_address_id=str(address.id)),
            headers=headers(tenant_a, "company.licence.manage", company=company),
        )
        assert response.status_code == 201, response.text
    response = await client.get(
        f"/v1/companies/{company}/licences",
        headers=headers(tenant_a, "company.read", company=company),
    )
    assert {r["kind"] for r in response.json()["items"]} == {"drug_licence_20", "drug_licence_21"}


async def test_country_change_cannot_invalidate_existing_licences(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        session.add(build_country("GB"))
        await session.flush()
        session.add(build_state("GB-ENG", "GB"))
        session.add(build_company_licence(tenant_id=tenant_a, company_id=company))
        await session.commit()
    response = await client.patch(
        f"/v1/companies/{company}",
        headers=_admin_headers(tenant_a),
        json={"country_code": "GB", "state_code": "GB-ENG", "default_tax_system": "vat_gb"},
    )
    assert response.status_code == 422, response.text


REFERENCE_PATHS = [
    "/v1/reference/countries",
    "/v1/reference/currencies",
    "/v1/reference/countries/IN/states",
    "/v1/reference/countries/IN/licence-types",
]


@pytest.mark.parametrize("path", REFERENCE_PATHS)
async def test_setup_lookups_require_authority_and_have_no_crud(
    client: httpx.AsyncClient,
    tenant_a: uuid.UUID,
    path: str,
) -> None:
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=headers(tenant_a, "user.read"))).status_code == 403
    assert (await client.post(path, json={}, headers=_admin_headers(tenant_a))).status_code == 405


async def test_setup_lookups_read_seeded_active_rows_and_scoped_readers_can_select(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    session.add_all(
        [
            build_currency("USD", name="US Dollar"),
            build_currency("XXX", is_active=False),
            build_country("US"),
            build_country("ZZ", is_active=False),
        ]
    )
    await session.flush()
    session.add_all([build_state("US-CA", "US"), build_state("IN-XX", is_active=False)])
    await session.commit()
    reader = headers(tenant_a, "company.read", company=company)
    countries = await client.get(REFERENCE_PATHS[0], headers=reader)
    assert countries.status_code == 200, countries.text
    by_code = {r["code"]: r for r in countries.json()}
    assert set(by_code) == {"IN", "US"}
    assert by_code["IN"]["default_currency_code"] == "INR"
    assert by_code["IN"]["jurisdiction_supported"] is True
    assert by_code["US"]["jurisdiction_supported"] is False
    currencies = await client.get(REFERENCE_PATHS[1], headers=reader)
    assert {r["code"] for r in currencies.json()} == {"INR", "USD"}
    states = await client.get(REFERENCE_PATHS[2], headers=reader)
    assert [r["code"] for r in states.json()] == ["MH"]
    kinds = await client.get(REFERENCE_PATHS[3], headers=reader)
    assert kinds.status_code == 200, kinds.text
    kinds_by_code = {r["kind"]: r for r in kinds.json()}
    assert "retail" in kinds_by_code["drug_licence_20"]["label"].lower()
    assert "wholesale" in kinds_by_code["drug_licence_20b"]["label"].lower()
    assert "drug_licence_21" in kinds_by_code
    assert "drug_licence_21b" in kinds_by_code
    # These rows are global, and do not contain any other tenant's company details.
    other = await client.get(REFERENCE_PATHS[0], headers=headers(tenant_b, "company.create"))
    assert other.json() == countries.json()


@pytest.mark.parametrize("path", REFERENCE_PATHS)
@pytest.mark.parametrize(
    "window",
    [
        {"valid_from": "2000-01-01", "valid_to": "2000-01-02"},
        {"valid_from": "2999-01-01"},
        {"is_active": False},
    ],
)
async def test_reference_lookups_refuse_grants_outside_their_validity(
    client: httpx.AsyncClient,
    tenant_a: uuid.UUID,
    path: str,
    window: dict[str, object],
) -> None:
    value = grant(["company.read"])
    value.update(window)
    response = await client.get(
        path, headers=actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[value])
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/v1/reference/countries/ZZ/states",
        "/v1/reference/countries/ZZ/licence-types",
        "/v1/reference/countries/invalid/states",
    ],
)
async def test_reference_lookups_reject_unknown_and_malformed_country(
    client: httpx.AsyncClient,
    tenant_a: uuid.UUID,
    path: str,
) -> None:
    response = await client.get(path, headers=headers(tenant_a, "company.create"))
    assert response.status_code == 422


async def test_reference_limit_does_not_silently_truncate_choices(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from identity.services import company_choices

    await seed_two_tenants(session, tenant_a, tenant_b)
    session.add(build_currency("USD"))
    await session.commit()
    monkeypatch.setattr(company_choices, "MAX_CHOICES", 1)
    response = await client.get("/v1/reference/currencies", headers=_admin_headers(tenant_a))
    assert response.status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"reporting_currency": "USD"},
        {"base_currency": "USD"},
        {"state_code": "IN-XX"},
    ],
)
async def test_patch_cannot_select_newly_inactive_codes(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    patch: dict[str, str],
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    session.add_all([build_currency("USD", is_active=False), build_state("IN-XX", is_active=False)])
    await session.commit()
    response = await client.patch(
        f"/v1/companies/{company}", json=patch, headers=_admin_headers(tenant_a)
    )
    assert response.status_code == 422


async def test_licence_duplicate_and_date_validation_preserve_original(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    auth = headers(tenant_a, "company.licence.manage", company=company)
    path = f"/v1/companies/{company}/licences"
    assert (await client.post(path, headers=auth, json=licence_body())).status_code == 201
    assert (await client.post(path, headers=auth, json=licence_body())).status_code == 409
    invalid_changes: list[dict[str, object]] = [
        {"valid_to": "2025-01-01"},
        {"valid_to": None},
        {"number": "   "},
    ]
    for changes in invalid_changes:
        response = await client.post(path, headers=auth, json=licence_body(**changes))
        assert response.status_code == 422, response.text
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CompanyLicence.id))) == 1


async def test_licence_company_scope_and_tenant_isolation(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other_tenant_company = await seed_two_companies(session, tenant_a, tenant_b)
    other_company = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_company(tenant_id=tenant_a, company_id=other_company, code="SECOND"))
        await session.commit()
    auth = headers(tenant_a, "company.licence.manage", company=company)
    for target, expected in [(other_company, 403), (other_tenant_company, 404)]:
        response = await client.post(
            f"/v1/companies/{target}/licences", headers=auth, json=licence_body()
        )
        assert response.status_code == expected
    path = f"/v1/companies/{company}/licences"
    assert (await client.post(path, json=licence_body())).status_code == 401
    assert (
        await client.post(path, json=licence_body(), headers=headers(tenant_a, "company.read"))
    ).status_code == 403

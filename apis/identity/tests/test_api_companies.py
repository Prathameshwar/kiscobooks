"""HTTP-level tests for the company resource.

Per endpoint (CLAUDE.md §7): happy path against the response schema · unauthenticated
401 · authenticated-but-wrong-company 403 · invalid input 422 · cross-tenant isolation.
Plus the company-specific invariants: the immutability ratchet is a 422 for every
actor, and a feature that is off is a 409.

The app runs in-process over ASGITransport against the same in-memory SQLite the test
seeds — no live server, no mocked service. Money is asserted as ``Decimal`` on the
persisted row, since that is where driver float-coercion would show (the wire is JSON).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company
from identity.seeds.roles import seed_system_roles
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_field_policy, seed_two_companies, seed_two_tenants

pytestmark = pytest.mark.asyncio


def _valid_company_body(code: str = "MAIN") -> dict[str, object]:
    """A create body that mirrors the ``build_company`` factory's valid Indian company."""
    return {
        "code": code,
        "legal_name": "Acme Traders Private Limited",
        "trade_name": "Acme",
        "display_name": "Acme Traders",
        "entity_type": "pvt_ltd",
        "incorporation_date": "2019-04-01",
        "country_code": "IN",
        "state_code": "MH",
        "base_currency": "INR",
        "fiscal_year_start_month": 4,
        "fiscal_year_start_day": 1,
        "books_begin_date": "2026-04-01",
        "amount_precision": 2,
        "quantity_precision": 3,
        "rounding_mode": "half_up",
        "default_tax_system": "gst_in",
        "tax_treatment_default": "exclusive",
        "default_payment_terms_days": 30,
        "cash_receipt_limit": "200000.0000",
        "timezone": "Asia/Kolkata",
        "locale": "en-IN",
        "date_format": "dd-MM-yyyy",
        "datetime_format": "dd-MM-yyyy HH:mm",
        "digit_grouping": "indian",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "negative_format": "minus",
        "currency_symbol_position": "prefix",
    }


def _admin_headers(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant_id,
        user_id=user_id or uuid7(),
        grants=[
            grant(
                [
                    "company.create",
                    "company.read",
                    "company.update",
                    "company.visibility.manage",
                ]
            )
        ],
    )


# --- create -------------------------------------------------------------------


async def test_create_company_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    resp = await client.post(
        "/v1/companies", json=_valid_company_body(), headers=_admin_headers(tenant_a)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "MAIN"
    assert body["status"] == "active"
    assert body["first_posted_at"] is None

    # The money column is a Decimal on the persisted row — where a float coercion
    # would surface — not merely correct-looking JSON on the wire.
    with tenant_scope(tenant_a):
        row = await session.get(Company, uuid.UUID(body["id"]))
    assert row is not None
    assert isinstance(row.cash_receipt_limit, Decimal)
    assert row.cash_receipt_limit == Decimal("200000.0000")


async def test_create_unauthenticated_is_401(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.post("/v1/companies", json=_valid_company_body())
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_required"


async def test_create_without_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read"])])
    resp = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "permission_denied"


async def test_create_invalid_enum_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    body = _valid_company_body()
    body["rounding_mode"] = "banker"  # not in ROUNDING_MODES
    resp = await client.post("/v1/companies", json=body, headers=_admin_headers(tenant_a))
    assert resp.status_code == 422


async def test_create_unknown_field_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    body = _valid_company_body()
    body["surprise"] = "value"  # extra="forbid": no mass assignment
    resp = await client.post("/v1/companies", json=body, headers=_admin_headers(tenant_a))
    assert resp.status_code == 422


async def test_create_duplicate_code_is_a_409_that_names_the_field(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A taken code says so, with ``fields.code`` on it.

    The unique key still backstops the race, but it arrives as the generic conflict
    envelope — the constraint name is an internal identifier and cannot be returned. This
    route has a second 409 (an unseeded role catalogue) and under that envelope the two are
    indistinguishable, so a client that generates the code (docs/company.md §4.1) could not
    tell whether a fresh code was worth trying. The field is what tells them apart.
    """
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    first = await client.post(
        "/v1/companies", json=_valid_company_body(), headers=_admin_headers(tenant_a)
    )
    assert first.status_code == 201, first.text

    again = _valid_company_body()
    again["display_name"] = "A second company, same code"
    resp = await client.post("/v1/companies", json=again, headers=_admin_headers(tenant_a))

    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["code"] == "conflict"
    assert error["fields"] == {"code": "already in use"}
    # No SQL, no constraint name, no identifiers (CLAUDE.md §5.8).
    assert "uq_company" not in resp.text


async def test_another_tenant_may_still_use_that_code(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The pre-check reads through the session tenant filter, so it cannot refuse a code on
    the strength of another tenant's row — which would leak that the row exists."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    await session.commit()
    first = await client.post(
        "/v1/companies", json=_valid_company_body(), headers=_admin_headers(tenant_a)
    )
    assert first.status_code == 201, first.text

    resp = await client.post(
        "/v1/companies", json=_valid_company_body(), headers=_admin_headers(tenant_b)
    )
    assert resp.status_code == 201, resp.text


async def test_create_impossible_jurisdiction_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    body = _valid_company_body()
    body["state_code"] = "US-CA"  # not a subdivision of IN
    resp = await client.post("/v1/companies", json=body, headers=_admin_headers(tenant_a))
    assert resp.status_code == 422


# --- read / isolation / object scope ------------------------------------------


async def test_get_company_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.get(f"/v1/companies/{company_a}", headers=_admin_headers(tenant_a))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(company_a)


async def test_cross_tenant_get_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Tenant B cannot see tenant A's company at all — the session filter hides it, so
    it is a 404, never a 403 (which would confirm the row exists)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.get(f"/v1/companies/{company_a}", headers=_admin_headers(tenant_b))
    assert resp.status_code == 404


async def test_wrong_company_within_tenant_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A company-scoped actor holding company.read on company A is refused company B in
    the same tenant — the object-scope check, not the endpoint gate (CLAUDE.md §5.2)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    other = uuid7()
    with tenant_scope(tenant_a):
        from tests.factories import build_company

        session.add(build_company(tenant_id=tenant_a, company_id=other, code="OTHER"))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read"], scope_type="company", scope_id=company_a)],
    )
    resp = await client.get(f"/v1/companies/{other}", headers=headers)
    assert resp.status_code == 403


# --- update / immutability ----------------------------------------------------


async def test_patch_display_name_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.patch(
        f"/v1/companies/{company_a}",
        json={"display_name": "Alpha Renamed"},
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alpha Renamed"


async def test_patch_frozen_field_after_posting_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company_a)
        assert row is not None
        row.first_posted_at = dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
        await session.commit()
    resp = await client.patch(
        f"/v1/companies/{company_a}",
        json={"base_currency": "USD"},
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "immutable_field"


async def test_patch_unchanged_frozen_field_after_posting_is_allowed(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A full PUT that re-sends a frozen field *unchanged* is not an edit — the ratchet
    is on the diff, not on payload presence (docs/field-permissions.md §6)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        row = await session.get(Company, company_a)
        assert row is not None
        row.first_posted_at = dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
        await session.commit()
    resp = await client.patch(
        f"/v1/companies/{company_a}",
        json={"base_currency": "INR", "display_name": "Alpha Two"},
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alpha Two"


# --- list ---------------------------------------------------------------------


async def test_list_is_scoped_and_paginates(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.get("/v1/companies", headers=_admin_headers(tenant_a))
    assert resp.status_code == 200
    payload = resp.json()
    ids = {item["id"] for item in payload["items"]}
    assert str(company_a) in ids
    assert "has_more" in payload["page"]


async def test_company_scoped_actor_list_excludes_other_companies(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    other = uuid7()
    with tenant_scope(tenant_a):
        from tests.factories import build_company

        session.add(build_company(tenant_id=tenant_a, company_id=other, code="OTHER"))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read"], scope_type="company", scope_id=company_a)],
    )
    resp = await client.get("/v1/companies", headers=headers)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {str(company_a)}


# --- display config & field set -----------------------------------------------


async def test_display_config(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.get(
        f"/v1/companies/{company_a}/display-config", headers=_admin_headers(tenant_a)
    )
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["digit_grouping"] == "indian"
    assert cfg["base_currency"] == "INR"


async def test_field_set_returns_registry(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get(
        "/v1/entities/identity.company/field-set", headers=_admin_headers(tenant_a)
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["entity_type"] == "identity.company"
    keys = {f["key"] for f in payload["fields"]}
    assert {"legal_name", "base_currency", "code"} <= keys
    code_field = next(f for f in payload["fields"] if f["key"] == "code")
    assert code_field["hideable"] is False


async def test_field_set_unknown_entity_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get(
        "/v1/entities/identity.nope/field-set", headers=_admin_headers(tenant_a)
    )
    assert resp.status_code == 404


# --- features -----------------------------------------------------------------


async def test_company_setup_readiness_is_scoped_and_feature_states_are_truthful(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_a, company_other_tenant = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        other = build_company(tenant_id=tenant_a, code="OTHER")
        session.add(other)
        await session.commit()
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read"], scope_type="company", scope_id=company_a)],
    )
    path = f"/v1/companies/{company_a}/setup-readiness"
    assert (await client.get(path)).status_code == 401
    denied = await client.get(f"/v1/companies/{other.id}/setup-readiness", headers=scoped)
    assert denied.status_code == 403
    assert (
        await client.get(f"/v1/companies/{company_other_tenant}/setup-readiness", headers=scoped)
    ).status_code in {403, 404}
    response = await client.get(path, headers=scoped)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["scope"] == "IDENTITY_ONLY"
    assert data["company_id"] == str(company_a)
    assert data["frozen_company_fields"] == []
    features = {row["feature_key"]: row for row in data["features"]}
    assert features["inventory"]["state"] == "DISABLED"
    assert features["expiry_tracking"]["required_features"] == ["batch_tracking", "inventory"]
    assert features["expiry_tracking"]["missing_prerequisites"] == [
        "batch_tracking",
        "inventory",
    ]
    assert features["expiry_tracking"]["tax_system_supported"] is True
    invalid = await client.get("/v1/companies/not-a-uuid/setup-readiness", headers=scoped)
    assert invalid.status_code == 422


async def test_company_setup_readiness_refuses_hidden_source_fields(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_id=user_id,
                subject_type="user",
                entity_type="identity.company",
                field_key="default_tax_system",
                access="read",
                scope_type="company",
                scope_id=company_a,
            )
        )
        await session.commit()
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[grant(["company.read"], scope_type="company", scope_id=company_a)],
    )
    response = await client.get(f"/v1/companies/{company_a}/setup-readiness", headers=scoped)
    assert response.status_code == 403


async def test_enable_feature_closes_dependencies(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Enabling expiry_tracking enables its whole prerequisite chain."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/features/expiry_tracking/enable",
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 200, resp.text
    listing = await client.get(
        f"/v1/companies/{company_a}/features", headers=_admin_headers(tenant_a)
    )
    enabled = set(listing.json()["enabled"])
    assert {"inventory", "batch_tracking", "expiry_tracking"} <= enabled
    readiness = await client.get(
        f"/v1/companies/{company_a}/setup-readiness", headers=_admin_headers(tenant_a)
    )
    assert readiness.status_code == 200, readiness.text
    expiry = next(
        row for row in readiness.json()["features"] if row["feature_key"] == "expiry_tracking"
    )
    assert expiry["state"] == "ENABLED"
    assert expiry["missing_prerequisites"] == []


async def test_feature_changes_lock_company_before_reading_state(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from identity.api import companies

    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    original = companies._load_company
    locks: list[bool] = []

    async def observed(db, company_id, *, for_update=False):
        locks.append(for_update)
        return await original(db, company_id, for_update=for_update)

    monkeypatch.setattr(companies, "_load_company", observed)
    for action in ("enable", "disable"):
        response = await client.post(
            f"/v1/companies/{company_a}/features/budgets/{action}",
            headers=_admin_headers(tenant_a),
        )
        assert response.status_code == 200, response.text
    assert locks == [True, True]


async def test_disable_feature_with_dependent_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    await client.post(
        f"/v1/companies/{company_a}/features/batch_tracking/enable",
        headers=_admin_headers(tenant_a),
    )
    resp = await client.post(
        f"/v1/companies/{company_a}/features/inventory/disable",
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 422


async def test_disable_locked_feature_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    from tests.factories import build_company_feature

    with tenant_scope(tenant_a):
        session.add(
            build_company_feature(
                tenant_id=tenant_a,
                company_id=company_a,
                feature_key="multi_currency",
                is_enabled=True,
                locked_at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
                lock_reason="a foreign-currency document has posted",
            )
        )
        await session.commit()
    resp = await client.post(
        f"/v1/companies/{company_a}/features/multi_currency/disable",
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "immutable_field"


# --- visibility ---------------------------------------------------------------


async def test_visibility_change_and_still_reachable(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Unlisting is a display preference: the company drops out of the default list but
    is still reachable by id for an authorized reader (invariant 17)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/visibility?visibility=unlisted",
        headers=_admin_headers(tenant_a),
    )
    assert resp.status_code == 200
    assert resp.json()["visibility"] == "unlisted"

    listed = await client.get("/v1/companies", headers=_admin_headers(tenant_a))
    assert str(company_a) not in {i["id"] for i in listed.json()["items"]}

    with_unlisted = await client.get(
        "/v1/companies?include_unlisted=true", headers=_admin_headers(tenant_a)
    )
    assert str(company_a) in {i["id"] for i in with_unlisted.json()["items"]}

    still = await client.get(f"/v1/companies/{company_a}", headers=_admin_headers(tenant_a))
    assert still.status_code == 200


async def test_visibility_change_without_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read"])])
    resp = await client.post(
        f"/v1/companies/{company_a}/visibility?visibility=unlisted", headers=headers
    )
    assert resp.status_code == 403

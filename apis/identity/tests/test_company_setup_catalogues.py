"""The two code catalogues a setup form reads: features, and per-country suggestions.

Both replace a table the console wizard was carrying itself. A stale client copy of the
feature catalogue can only omit a capability from the screen — but a capability nobody
can enable is indistinguishable from one the platform does not have, so the server is
the one that says what exists.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict

import pytest
from billing_platform.db import tenant_scope
from billing_platform.features import FEATURES
from billing_platform.ids import uuid7
from billing_platform.jurisdiction import JURISDICTION_PROFILES

from identity.domain.company_defaults import NEUTRAL_DEFAULTS, setup_defaults
from tests.api_support import actor_headers, grant
from tests.factories import build_country, build_currency, seed_two_companies

CATALOGUE = "/v1/company-features"
COUNTRIES = "/v1/reference/countries"


def setup_headers(tenant: uuid.UUID, *permissions: str) -> dict[str, str]:
    return actor_headers(tenant_id=tenant, user_id=uuid7(), grants=[grant(list(permissions))])


async def test_feature_catalogue_offers_every_catalogued_capability(client, tenant_a):
    response = await client.get(CATALOGUE, headers=setup_headers(tenant_a, "company.create"))
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    # Every key in the code catalogue, exactly once, so the wizard cannot be missing one.
    assert sorted(item["key"] for item in items) == sorted(FEATURES)
    assert len({item["key"] for item in items}) == len(items)
    by_key = {item["key"]: item for item in items}
    assert set(by_key["inventory"]) == {
        "key",
        "label",
        "description",
        "requires",
        "tax_systems",
        "locks",
    }
    # The graph as the catalogue states it: direct dependencies, not the closure.
    assert by_key["expiry_tracking"]["requires"] == ["batch_tracking"]
    assert by_key["inventory"]["requires"] == []
    # Tax gating is carried, so a UK VAT company is never offered a GST e-way bill.
    assert by_key["e_waybill"]["tax_systems"] == ["gst_in"]
    assert by_key["budgets"]["tax_systems"] == []
    # The irreversibility ratchet is visible before the choice is made.
    assert by_key["inventory"]["locks"] is True
    assert by_key["budgets"]["locks"] is False
    assert by_key["inventory"]["label"] and by_key["inventory"]["description"]
    # Ordering is the offer order, not alphabetical: "Expiry dates" after "Batches".
    keys = [item["key"] for item in items]
    assert keys.index("inventory") < keys.index("batch_tracking") < keys.index("expiry_tracking")


async def test_feature_catalogue_is_gated_and_read_only(client, tenant_a):
    assert (await client.get(CATALOGUE)).status_code == 401
    assert (
        await client.get(CATALOGUE, headers=setup_headers(tenant_a, "user.read"))
    ).status_code == 403
    for permission in ("company.create", "company.read", "company.update"):
        assert (
            await client.get(CATALOGUE, headers=setup_headers(tenant_a, permission))
        ).status_code == 200
    assert (
        await client.post(CATALOGUE, json={}, headers=setup_headers(tenant_a, "company.create"))
    ).status_code == 405


async def test_feature_catalogue_carries_no_company_state(client, session, tenant_a, tenant_b):
    """It describes the platform, so two tenants get byte-identical answers."""
    await seed_two_companies(session, tenant_a, tenant_b)
    first = await client.get(CATALOGUE, headers=setup_headers(tenant_a, "company.read"))
    second = await client.get(CATALOGUE, headers=setup_headers(tenant_b, "company.read"))
    assert first.json() == second.json()


async def test_countries_carry_their_setup_suggestions(client, session, tenant_a, tenant_b):
    await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        session.add(build_currency("EUR"))
        await session.flush()
        # A country with no jurisdiction profile: still offered, with the neutral set.
        session.add(build_country("FR", currency_code="EUR"))
        await session.commit()
    response = await client.get(COUNTRIES, headers=setup_headers(tenant_a, "company.create"))
    assert response.status_code == 200, response.text
    rows = {row["code"]: row for row in response.json()}
    india = rows["IN"]["setup_defaults"]
    assert india["fiscal_year_start_month"] == 4
    assert india["fiscal_year_start_day"] == 1
    assert india["timezone"] == "Asia/Kolkata"
    assert india["digit_grouping"] == "indian"
    assert india["date_format"] == "dd-MM-yyyy"
    # Exactly the domain table, so the endpoint cannot drift from the suggestions that
    # `test_company_defaults_domain` checks without a database.
    assert india == asdict(setup_defaults("IN"))
    assert rows["FR"]["jurisdiction_supported"] is False
    assert rows["FR"]["setup_defaults"]["timezone"] == NEUTRAL_DEFAULTS.timezone
    assert rows["FR"]["setup_defaults"]["fiscal_year_start_month"] == 1
    # The capabilities a setup form offers pre-selected, from the jurisdiction profile —
    # in its order, so a form enabling them in turn never asks for a dependent first.
    assert rows["IN"]["default_features"] == list(JURISDICTION_PROFILES["IN"].default_features)
    assert rows["IN"]["default_features"][0] == "inventory"
    # A jurisdiction with no profile suggests nothing: there is no basis for a default, and
    # a company cannot be created there anyway.
    assert rows["FR"]["default_features"] == []


@pytest.mark.parametrize("field", ["fiscal_year_start_month", "timezone", "rounding_mode"])
async def test_setup_suggestions_are_present_for_every_offered_country(
    client, session, tenant_a, tenant_b, field
):
    """A form with no suggestion for one country would silently fall back to its own."""
    await seed_two_companies(session, tenant_a, tenant_b)
    response = await client.get(COUNTRIES, headers=setup_headers(tenant_a, "company.read"))
    rows = response.json()
    assert rows
    assert all(row["setup_defaults"][field] is not None for row in rows)

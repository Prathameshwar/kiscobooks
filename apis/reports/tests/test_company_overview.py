"""A real overview must not substitute sample figures or partial-input totals."""

import re
import uuid

from conftest import COMPANY, PERMISSIONS, headers
from test_native_ledger import prepared

BASE = f"/v2/companies/{COMPANY}/overview"


async def test_overview_requires_auth_and_complete_company_authority(client):
    assert (await client.get(BASE)).status_code == 401
    denied = await client.get(BASE, headers=headers(permissions=PERMISSIONS - {"ledger.read"}))
    assert denied.status_code == 403


async def test_overview_has_exact_source_bound_figures_and_unknown_query_refusal(app, client):
    identities, facts, _ = await prepared(app)
    year = next(
        str(row.source_id)
        for row in facts
        if row.entity == "fiscal_year" and row.data["start_date"] == "2026-04-01"
    )
    response = await client.get(
        BASE,
        params={
            "generation_id": str(identities[2]),
            "fiscal_year_id": year,
            "date_to": "2026-04-30",
        },
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["company_id"] == str(COMPANY)
    assert value["generation_id"] == str(identities[2])
    assert value["currency"] == "INR"
    assert value["series"] and len(value["series"]) <= 366
    assert value["totals"] == {
        "cash": "180.0000",
        "bank": "0.0000",
        "net_receivable": "80.0000",
        "net_payable": "0.0000",
        "income": "200.0000",
        "expenses": "40.0000",
        "net_income": "160.0000",
    }
    for amount in value["totals"].values():
        assert isinstance(amount, str) and re.fullmatch(r"-?\d+\.\d{4}", amount)
    assert response.headers["cache-control"] == "no-store"
    assert (
        await client.get(BASE, params={"unexpected": "value"}, headers=headers())
    ).status_code == 422
    foreign = await client.get(BASE, params={"generation_id": str(uuid.uuid4())}, headers=headers())
    assert foreign.status_code == 404


async def test_overview_scopes_all_aggregates_and_refuses_read_denies(app, client):
    identities, _, _ = await prepared(app)
    await prepared(app, tenant=uuid.uuid4())
    response = await client.get(
        BASE,
        params={"generation_id": str(identities[2]), "date_to": "2026-04-30"},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["totals"]["cash"] == "180.0000"
    other_company = uuid.uuid4()
    other = await client.get(
        f"/v2/companies/{other_company}/overview",
        params={"generation_id": str(identities[2])},
        headers=headers(company=other_company),
    )
    assert other.status_code == 403
    denied = await client.get(
        BASE,
        headers=headers(
            policies=[
                {
                    "access": "read",
                    "effect": "deny",
                    "entity": "accounting.journal_line",
                    "field": "amount",
                }
            ]
        ),
    )
    assert denied.status_code == 403


async def test_overview_is_explicitly_unavailable_without_verified_sources(app, client):
    response = await client.get(BASE, headers=headers())
    assert response.status_code == 409
    assert "totals" not in response.json()


async def test_verified_overview_read_does_not_require_native_run_admission(app, client):
    identities, _, _ = await prepared(app)
    assert app.state.settings.native_queries_enabled is False

    response = await client.get(
        BASE,
        params={"generation_id": str(identities[2]), "date_to": "2026-04-30"},
        headers=headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["generation_id"] == str(identities[2])

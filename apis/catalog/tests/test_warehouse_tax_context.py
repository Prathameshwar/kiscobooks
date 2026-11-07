"""References are accepted only from scoped, signed Identity company facts."""

import time

import pytest
from billing_platform.company_context import CompanyContext, sign_company_context
from billing_platform.ids import uuid7

from tests.commercial_factories import reference_data
from tests.conftest import ACTOR_SECRET
from tests.test_commercial_api import command_headers
from tests.warehouse_factories import auth


def registration_headers(current, tenant, company, user, identities, *, jurisdiction="IN-MH"):
    facts = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        base_currency="INR",
        registrations=tuple(
            {
                "id": str(identity),
                "country_code": "IN",
                "jurisdiction_code": jurisdiction,
                "valid_from": "2000-01-01",
                "valid_to": None,
            }
            for identity in identities
        ),
    )
    token, signature = sign_company_context(facts, ACTOR_SECRET.encode())
    return {**current, "x-company-context": token, "x-company-signature": signature}


@pytest.mark.parametrize("scenario", ["unknown", "jurisdiction", "company", "signature", "missing"])
async def test_warehouse_registration_reference_requires_owner_context(
    client, factory, tenant_a, scenario
):
    company, user, identity = uuid7(), uuid7(), uuid7()
    await reference_data(factory)
    current = await auth(factory, tenant_a, company, user)
    headers = registration_headers(
        current,
        tenant_a,
        uuid7() if scenario == "company" else company,
        user,
        [] if scenario == "unknown" else [identity],
        jurisdiction="IN-DL" if scenario == "jurisdiction" else "IN-MH",
    )
    if scenario == "signature":
        headers["x-company-signature"] = "invalid"
    if scenario == "missing":
        headers = current
    response = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(headers),
        json={
            "code": "REG",
            "name": "Registered warehouse",
            "kind": "GODOWN",
            "country_code": "IN",
            "state_code": "IN-MH",
            "tax_registration_id": str(identity),
        },
    )
    assert response.status_code == (
        401 if scenario in {"company", "signature"} else 503 if scenario == "missing" else 422
    ), response.text
    if response.status_code == 422:
        assert "tax_registration_id" in response.json()["error"]["fields"]

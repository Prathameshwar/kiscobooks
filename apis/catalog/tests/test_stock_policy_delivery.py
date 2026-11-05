"""Only verified native owner claims may update the preserved billing consumer."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from pydantic import SecretStr
from sqlalchemy import select
from voucher_execution.stock_policy import PolicyInspectionResult
from voucher_execution.stock_policy_transport import (
    PolicyClient,
    PolicyConnection,
    PolicyUnavailableError,
)

from catalog.models.releases import CatalogPolicyConsumerAck
from tests.conftest import ACTOR_SECRET
from tests.test_commercial_api import command_headers
from tests.test_policy_release_api import body, provision, route, view


@pytest.mark.parametrize("verdict", ["APPLIED", "REJECTED", "PENDING", "UNAVAILABLE", "WRONG"])
async def test_exact_owner_delivery_and_unavailability_preserve_truth(
    app, client, factory, tenant_a, monkeypatch, verdict
):
    state = await provision(client, factory, tenant_a)
    company, current = state["company"], state["current"]
    calls = []

    async def inspect(self, request):
        calls.append(request)
        if verdict == "UNAVAILABLE":
            raise PolicyUnavailableError("owner is offline")
        now = utcnow()
        return PolicyInspectionResult(
            check_id=request.check_id,
            request_hash="a" * 64 if verdict == "WRONG" else request.digest(),
            issued_at=now,
            expires_at=now + dt.timedelta(seconds=30),
            result="APPLIED" if verdict == "WRONG" else verdict,
            reason="UNSUPPORTED_OPERATION"
            if verdict == "REJECTED"
            else "SOURCE_UNAVAILABLE"
            if verdict == "PENDING"
            else None,
        )

    monkeypatch.setattr(PolicyClient, "inspect", inspect)
    app.state.settings = app.state.settings.model_copy(
        update={
            "stock_policy_accounting": PolicyConnection(
                origin="http://127.0.0.1:8011", secret=SecretStr(ACTOR_SECRET)
            )
        }
    )
    before = await view(client, company, current)
    response = await client.post(
        route(company), json=body(before), headers=command_headers(current)
    )
    if verdict == "WRONG":
        assert response.status_code == 409
        assert (await view(client, company, current))["current"] is None
        return
    assert response.status_code == 201, response.text
    expected = verdict if verdict in {"APPLIED", "REJECTED"} else "PENDING"
    after = await view(client, company, current)
    assert after["current"]["delivery_state"] == expected
    with tenant_scope(tenant_a):
        async with factory() as db:
            claims = list(
                await db.scalars(
                    select(CatalogPolicyConsumerAck).where(
                        CatalogPolicyConsumerAck.company_id == company
                    )
                )
            )
            assert len(claims) == (3 if expected != "PENDING" else 0)  # release, Main, transit
            assert all(row.consumer == "billing" for row in claims)
    assert len(calls) == 1
    assert calls[0].manifest.digest() == after["current"]["manifest_digest"]

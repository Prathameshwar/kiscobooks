"""Catalog batch verification must forward fresh company facts to Accounting."""

import uuid

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.company_context import verify_company_context
from billing_platform.db.types import utcnow
from fastapi import Request

from identity.api.auth import Actor
from identity.api.login import gateway_authorize
from tests.factories import seed_two_companies


@pytest.mark.parametrize("route", ["prices/resolve", "prices/coverage", "batch-prices"])
async def test_batch_pricing_gets_verified_owner_context(app, session, tenant_a, tenant_b, route):
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    current = Actor(
        tenant_a,
        uuid.uuid4(),
        grants=(Grant(frozenset({"item.read"}), Scope("company", company), utcnow().date()),),
    )
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/internal/v1/gateway/authorize",
        "headers": [(b"x-original-uri", f"/catalog/v1/companies/{company}/{route}".encode())],
        "app": app,
    })
    response = await gateway_authorize(request, current)
    assert response.status_code == 204
    facts = verify_company_context(
        response.headers["x-company-context"],
        response.headers["x-company-signature"],
        app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    assert facts.company_id == company and facts.user_id == current.user_id
    assert {"vouchers", "accounting"} <= facts.policy_namespaces

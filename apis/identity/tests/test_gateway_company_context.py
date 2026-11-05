"""Company creation cannot exhaust gateway headers by accumulating other-company roles."""

import base64
import json
import uuid

import pytest
from billing_platform.authz import Grant, Scope, grant_to_wire
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from fastapi import Request

from identity.api.auth import Actor
from identity.api.login import gateway_authorize
from tests.factories import build_department, seed_two_companies


@pytest.mark.parametrize(
    "route",
    [
        "simple-product-creations/options?kind=GOODS",
        "import-templates",
        "import-jobs",
        "simple-product-imports",
    ],
)
async def test_simple_creation_gets_fresh_voucher_and_accounting_context(
    app, session, tenant_a, tenant_b, route
):
    from billing_platform.company_context import verify_company_context

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    current = Actor(
        tenant_a,
        uuid.uuid4(),
        grants=(
            Grant(
                frozenset({"item.create", "item.read"}), Scope("company", company), utcnow().date()
            ),
        ),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/internal/v1/gateway/authorize",
            "headers": [
                (
                    b"x-original-uri",
                    f"/catalog/v1/companies/{company}/{route}".encode(),
                )
            ],
            "app": app,
        }
    )
    response = await gateway_authorize(request, current)
    assert response.status_code == 204
    facts = verify_company_context(
        response.headers["x-company-context"],
        response.headers["x-company-signature"],
        app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    assert facts.company_id == company and facts.user_id == current.user_id
    assert {"vouchers", "accounting"} <= facts.policy_namespaces


async def test_gateway_retains_exact_company_and_department_authority_with_many_other_companies(
    app,
    session,
    tenant_a,
    tenant_b,
):
    company, foreign_company = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        own = build_department(tenant_id=tenant_a, company_id=company)
        session.add(own)
        await session.commit()
        own_id = own.id
    with tenant_scope(tenant_b):
        foreign = build_department(tenant_id=tenant_b, company_id=foreign_company)
        session.add(foreign)
        await session.commit()
        foreign_id = foreign.id
    day = utcnow().date()
    retained = (
        Grant(frozenset({"company.read"}), Scope("tenant"), day),
        Grant(frozenset({"unit.manage"}), Scope("company", company), day),
        Grant(frozenset({"item.read"}), Scope("department", own_id), day),
    )
    unrelated = tuple(
        Grant(
            frozenset({"company.read", "unit.read", "unit.manage"}),
            Scope("company", uuid.uuid4()),
            day,
        )
        for _ in range(200)
    )
    current = Actor(
        tenant_a,
        uuid.uuid4(),
        grants=(
            *retained,
            *unrelated,
            Grant(frozenset({"item.manage"}), Scope("department", foreign_id), day),
        ),
    )
    assert len(json.dumps([grant_to_wire(g) for g in current.grants]).encode()) > 24_000
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/internal/v1/gateway/authorize",
            "headers": [
                (
                    b"x-original-uri",
                    f"/catalog/v1/companies/{company}/unit-defaults/bootstrap".encode(),
                )
            ],
            "app": app,
        }
    )
    response = await gateway_authorize(request, current)
    assert response.status_code == 204
    encoded = response.headers["x-actor-context"]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert payload["grants"] == [grant_to_wire(g) for g in retained]
    assert len(json.dumps(payload).encode()) < 24_000
    assert len(current.grants) == 204  # The session actor remains unchanged.

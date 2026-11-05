"""Encoded public paths must retain gateway company authentication requirements."""

import pytest
from billing_platform.db import tenant_scope

from identity.models import Company
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies


@pytest.mark.parametrize("service", ["catalog", "accounting", "vouchers", "reports", "audit"])
async def test_encoded_path_cannot_bypass_company_step_up(
    client, session, tenant_a, tenant_b, service
):
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        company = await session.get(Company, company_id)
        company.requires_step_up = True
        await session.commit()
        user_id = user.id
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read", "audit.read"])]
    )
    company_text = str(company_id)
    encoded_company = "%" + format(ord(company_text[0]), "02x") + company_text[1:]
    if service == "audit":
        suffix = f"/v1/audit-events?company_id={company_id}"
        paths = [
            prefix + suffix
            for prefix in (
                "/%61udit",
                "//audit",
                "/./audit",
                "/x/../audit",
                "HTTP://localhost/audit",
            )
        ]
    else:
        paths = [
            f"/{service}/v1/companies/{encoded_company}/items",
            f"/{service}/v1/comp%61nies/{company_id}/items",
            f"/{service}/v1/companies/unused/../{company_id}/items",
            f"//{service}//v1//companies/{company_id}/items",
            f"/{service}%2fv1%2fcompanies%2f{company_id}/items",
        ]
    for path in paths:
        response = await client.get(
            "/internal/v1/gateway/authorize", headers=headers | {"x-original-uri": path}
        )
        assert response.status_code == 403, (path, response.status_code, response.text)


@pytest.mark.parametrize("path", ["/catalog/%2531", "/catalog/%zz", "/catalog/%ff", "http://["])
async def test_ambiguous_or_malformed_gateway_uri_fails_closed(app, path):
    import uuid

    from billing_platform.errors import ValidationFailedError
    from fastapi import Request

    from identity.api.auth import Actor
    from identity.api.login import gateway_authorize

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/internal/v1/gateway/authorize",
            "headers": [(b"x-original-uri", path.encode())],
            "app": app,
        }
    )
    with pytest.raises(ValidationFailedError, match="gateway URI"):
        await gateway_authorize(request, Actor(uuid.uuid4(), uuid.uuid4()))

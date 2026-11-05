"""The gateway delegates both capture and owner field restrictions in one signed context."""

from billing_platform.db import tenant_scope

from identity.api.auth import Actor
from identity.services.accounting_context import company_context
from tests.api_support import actor_headers, grant
from tests.test_accounting_policy_api import PERMISSIONS, policy, seed


async def test_voucher_gateway_includes_owner_policy_denies(client, session, tenant_a, tenant_b):
    company, _, admin, reader, _ = await seed(session, tenant_a, tenant_b)
    auth = actor_headers(
        tenant_id=tenant_a, user_id=admin, grants=[grant([*PERMISSIONS, "vouchers.read"])]
    )
    owner = policy(reader, company)
    voucher = owner | {
        "entity_type": "vouchers.voucher",
        "field_key": "narration",
        "condition": None,
    }
    for body in (owner, voucher):
        result = await client.post("/v1/field-policies", headers=auth, json=body)
        assert result.status_code == 201, result.text
    with tenant_scope(tenant_a):
        context = await company_context(
            session, Actor(tenant_a, reader), company, entity_prefix="vouchers."
        )
        assert context.policy_namespaces == {"accounting", "vouchers"}
        assert {row["entity_type"] for row in context.policies} == {
            "accounting.party",
            "vouchers.voucher",
        }
        accounting = await company_context(session, Actor(tenant_a, reader), company)
        assert accounting.policy_namespaces == {"accounting"}
        assert {row["entity_type"] for row in accounting.policies} == {"accounting.party"}

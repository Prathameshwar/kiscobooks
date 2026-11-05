"""Pricing audit evidence is restricted to configured platform configuration managers."""

from billing_platform.db import tenant_scope

from audit.tasks.consume import handle_event
from tests.seed import audit_envelope
from tests.test_platform_events import headers


async def test_pricing_evidence_permission_boundary(client, session, tenant_a):
    for action in ("created", "updated", "deleted", "restored"):
        envelope = audit_envelope(
            tenant_id=tenant_a, action="platform.price_" + action, entity_type="platform_price"
        )
        envelope = envelope.model_copy(
            update={"payload": {**envelope.payload, "source_service": "identity"}}
        )
        with tenant_scope(tenant_a):
            await handle_event(session, envelope, consumer_name="pricing-test")
    await session.commit()
    response = await client.get(
        "/v1/platform-events", headers=headers(tenant_a, ["platform.config.manage"])
    )
    assert response.status_code == 200 and len(response.json()["items"]) == 4
    for permissions in (["platform.tenant.read"], ["audit.read", "audit.read_security"]):
        response = await client.get("/v1/platform-events", headers=headers(tenant_a, permissions))
        assert response.status_code == 403 or response.json()["items"] == []
    response = await client.get(
        "/v1/platform-events",
        headers=headers(tenant_a, ["platform.config.manage"], configured=False),
    )
    assert response.status_code == 403

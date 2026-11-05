from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from unittest.mock import patch

import httpx
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow

from notification.providers.inspection import Inspection
from notification.tasks.configuration import run_configuration_jobs
from tests.test_control import headers


async def test_complete_configuration_lifecycle_and_activation_replay(
    client: httpx.AsyncClient,
    app: Any,
    tenant_a: uuid.UUID,
    monkeypatch: Any,
) -> None:
    proof = headers(tenant_a)
    assert (await client.get("/v1/credential-bindings", headers=proof)).status_code == 200
    created = await client.post(
        "/v1/provider-accounts",
        headers=proof,
        json={
            "key": "primary",
            "channel": "email",
            "provider_key": "ses",
            "callback_key": "n" * 43,
            "display_name": "Primary",
            "credential_ref": "env:REVIEW",
            "region": "us-east-1",
        },
    )
    assert created.status_code == 201, created.text
    provider = created.json()["id"]
    monkeypatch.setenv("REVIEW", "{}")
    with patch(
        "notification.tasks.configuration.inspect_provider",
        return_value=Inspection(True, "checked"),
    ):
        job = await client.post(
            f"/v1/provider-accounts/{provider}/validate",
            headers={**proof, "Idempotency-Key": "provider"},
        )
        assert job.status_code == 202
        await run_configuration_jobs(app.state.session_factory, app.state.settings)
        status = await client.get(f"/v1/jobs/{job.json()['id']}", headers=proof)
        assert status.json()["status"] == "completed"
    sender = await client.post(
        "/v1/sender-identities",
        headers=proof,
        json={
            "provider_account_id": provider,
            "key": "sender",
            "sender_type": "email",
            "external_sender_id": "noreply@acme.example",
            "display_name": "Sender",
        },
    )
    assert sender.status_code == 201, sender.text
    sender_id = sender.json()["id"]
    assert (
        await client.get(f"/v1/sender-identities/{sender_id}", headers=proof)
    ).status_code == 200
    listed = await client.get(
        f"/v1/sender-identities?provider_account_id={provider}", headers=proof
    )
    assert listed.json()["items"][0]["id"] == sender_id
    assert (
        await client.put("/v1/channel-settings/email", headers=proof, json={"is_enabled": True})
    ).status_code == 409
    with patch(
        "notification.tasks.configuration.inspect_provider",
        return_value=Inspection(True, "verified", verification_status="verified"),
    ):
        job = await client.post(
            f"/v1/sender-identities/{sender_id}/verify",
            headers={**proof, "Idempotency-Key": "sender"},
        )
        assert job.status_code == 202
        await run_configuration_jobs(app.state.session_factory, app.state.settings)
    assert (
        await client.put("/v1/channel-settings/email", headers=proof, json={"is_enabled": True})
    ).status_code == 200
    assert (
        await client.get(f"/v1/provider-accounts/{provider}/callback-configuration", headers=proof)
    ).status_code == 200
    assert (
        await client.patch(
            f"/v1/sender-identities/{sender_id}", headers=proof, json={"display_name": "Updated"}
        )
    ).status_code == 200
    template = await client.post(
        "/v1/templates",
        headers=proof,
        json={
            "company_id": str(SCOPE_ALL),
            "key": "share",
            "event_key": "voucher.shared",
            "category": "transactional",
            "default_locale": "en",
        },
    )
    template_id = template.json()["id"]
    assert (await client.get(f"/v1/templates/{template_id}", headers=proof)).status_code == 200
    assert (
        await client.patch(
            f"/v1/templates/{template_id}", headers=proof, json={"description": "Shared document"}
        )
    ).status_code == 200
    variant = await client.post(
        f"/v1/templates/{template_id}/variants",
        headers=proof,
        json={"channel": "email", "locale": "en"},
    )
    variant_id = variant.json()["id"]
    assert (await client.get(f"/v1/templates/{template_id}/variants", headers=proof)).json()[
        "items"
    ]
    assert (await client.get(f"/v1/variants/{variant_id}", headers=proof)).status_code == 200
    assert (
        await client.patch(f"/v1/variants/{variant_id}", headers=proof, json={"is_active": True})
    ).status_code == 200
    versions = []
    for text in ("Your document is ready", "Your updated document is ready"):
        version = await client.post(
            f"/v1/variants/{variant_id}/versions", headers=proof, json={"body_text": text}
        )
        assert version.status_code == 201
        versions.append(version.json()["id"])
    assert (
        len(
            (await client.get(f"/v1/variants/{variant_id}/versions", headers=proof)).json()["items"]
        )
        == 2
    )
    assert (
        await client.get(f"/v1/template-versions/{versions[0]}", headers=proof)
    ).status_code == 200
    activation = {
        "template_version_id": versions[0],
        "valid_from": (utcnow() + dt.timedelta(seconds=2)).isoformat(),
    }
    first = await client.post(
        f"/v1/variants/{variant_id}/activate",
        headers={**proof, "Idempotency-Key": "activation"},
        json=activation,
    )
    replay = await client.post(
        f"/v1/variants/{variant_id}/activate",
        headers={**proof, "Idempotency-Key": "activation"},
        json=activation,
    )
    assert first.status_code == 201 and replay.json()["id"] == first.json()["id"]
    changed = await client.post(
        f"/v1/variants/{variant_id}/activate",
        headers={**proof, "Idempotency-Key": "activation"},
        json={**activation, "template_version_id": versions[1]},
    )
    assert changed.status_code == 409
    assert (await client.get(f"/v1/variants/{variant_id}/activations", headers=proof)).json()[
        "items"
    ]
    assignment = await client.post(
        "/v1/use-case-bindings",
        headers=proof,
        json={
            "company_id": str(SCOPE_ALL),
            "event_key": "voucher.shared",
            "trigger_key": "vouchers.voucher.share",
            "channel": "email",
            "template_id": template_id,
            "valid_from": utcnow().isoformat(),
        },
    )
    assert assignment.status_code == 201
    assignment_id = assignment.json()["id"]
    assert (
        await client.get(f"/v1/use-case-bindings/{assignment_id}", headers=proof)
    ).status_code == 200
    assert (await client.get("/v1/use-case-bindings", headers=proof)).json()["items"]
    route = await client.post(
        "/v1/routing-rules",
        headers=proof,
        json={
            "company_id": str(SCOPE_ALL),
            "event_key": "voucher.shared",
            "category": "transactional",
            "channel": "email",
            "provider_account_id": provider,
            "sender_identity_id": sender_id,
            "priority": 0,
            "weight": 1,
            "max_attempts": 3,
            "timeout_seconds": 10,
            "initial_backoff_seconds": 5,
            "max_backoff_seconds": 60,
        },
    )
    assert route.status_code == 201
    route_id = route.json()["id"]
    assert (await client.get(f"/v1/routing-rules/{route_id}", headers=proof)).status_code == 200
    assert (
        await client.patch(
            f"/v1/routing-rules/{route_id}", headers=proof, json={"is_active": False}
        )
    ).status_code == 200
    effective = await client.post(
        "/v1/effective-policy",
        headers=proof,
        json={
            "company_id": str(SCOPE_ALL),
            "event_key": "voucher.shared",
            "trigger_key": "vouchers.voucher.share",
            "channel": "email",
        },
    )
    assert effective.status_code == 200 and "no_eligible_route" in effective.json()["reasons"]
    ended = await client.post(
        f"/v1/use-case-bindings/{assignment_id}/end",
        headers=proof,
        json={"valid_to": (utcnow() + dt.timedelta(minutes=10)).isoformat()},
    )
    assert ended.status_code == 200
    # Rotating the bound identity invalidates provider and sender evidence together.
    rotated = await client.patch(
        f"/v1/provider-accounts/{provider}", headers=proof, json={"credential_ref": "env:PRIVATE"}
    )
    assert rotated.status_code == 200 and rotated.json()["status"] == "pending"
    refreshed_sender = await client.get(f"/v1/sender-identities/{sender_id}", headers=proof)
    assert refreshed_sender.json()["verification_status"] == "unverified"
    ended = await client.post(
        f"/v1/activations/{first.json()['id']}/end",
        headers=proof,
        json={"valid_to": (utcnow() + dt.timedelta(minutes=10)).isoformat()},
    )
    assert ended.status_code == 200


async def test_stale_sender_check_cannot_reverify_after_reactivation(
    client, app, session, tenant_a, monkeypatch
):
    from billing_platform.db import tenant_scope
    from billing_platform.ids import uuid7
    from sqlalchemy import select

    from notification.models import SenderIdentity
    from tests.notif_seed import seed_email_route

    await seed_email_route(session, tenant=tenant_a, company=uuid7(), subject=uuid7())
    with tenant_scope(tenant_a):
        sender = (await session.scalars(select(SenderIdentity))).one()
        sender_id = sender.id
    proof = headers(tenant_a)
    monkeypatch.setenv("SES", "{}")
    job = await client.post(
        f"/v1/sender-identities/{sender_id}/sync",
        headers={**proof, "Idempotency-Key": "stale-sender"},
    )
    assert job.status_code == 202

    async def remote_check(*args, **kwargs):
        for enabled in (False, True):
            changed = await client.patch(
                f"/v1/sender-identities/{sender_id}",
                headers=proof,
                json={"is_active": enabled},
            )
            assert changed.status_code == 200
        return Inspection(True, "verified", verification_status="verified")

    with patch("notification.tasks.configuration.inspect_provider", side_effect=remote_check):
        assert await run_configuration_jobs(app.state.session_factory, app.state.settings) == 1
    status = await client.get(f"/v1/jobs/{job.json()['id']}", headers=proof)
    assert status.json()["status"] == "failed"
    assert status.json()["reason_code"] == "configuration_changed_during_check"
    current = await client.get(f"/v1/sender-identities/{sender_id}", headers=proof)
    assert current.json()["is_active"] and current.json()["verification_status"] == "unverified"

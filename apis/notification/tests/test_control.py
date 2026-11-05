from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.domain.catalogue import validate_content, validate_schema, validate_variables
from notification.models import PlanningOutcome
from notification.providers.inspection import Inspection
from notification.tasks.configuration import run_configuration_jobs
from notification.tasks.consume import handle_send_command
from tests.api_support import actor_headers
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


def headers(tenant: uuid.UUID) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant,
        user_id=uuid7(),
        permissions=[
            "notification.provider.read",
            "notification.provider.manage",
            "notification.template.read",
            "notification.template.manage",
            "notification.route.read",
            "notification.route.manage",
            "notification.request.read",
        ],
    )


@pytest.mark.asyncio
async def test_catalogue_separates_platform_purposes(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    proof = headers(tenant_a)
    response = await client.get("/v1/use-cases", headers=proof)
    assert response.status_code == 200
    assert all(item["owner"] == "tenant" for item in response.json())
    assert "user.invited" not in str(response.json())
    assert (await client.get("/v1/provider-types", headers=proof)).json()["meta"] == "whatsapp"
    assert (await client.get("/v1/channels", headers=proof)).status_code == 200


@pytest.mark.asyncio
async def test_provider_references_are_owner_bound_and_validation_is_async(
    client: httpx.AsyncClient,
    app: Any,
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proof = headers(tenant_a)
    body = {
        "key": "test",
        "callback_key": "a" * 43,
        "channel": "sms",
        "provider_key": "twilio",
        "display_name": "Test",
        "credential_ref": "env:PLATFORM_SECRET",
        "callback_secret_ref": "env:VERIFY",
    }
    assert (await client.post("/v1/provider-accounts", json=body, headers=proof)).status_code == 422
    body["credential_ref"] = "env:REVIEW"
    created = await client.post("/v1/provider-accounts", json=body, headers=proof)
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    command_headers = {**proof, "Idempotency-Key": "same-validation"}
    first = await client.post(f"/v1/provider-accounts/{identity}/validate", headers=command_headers)
    second = await client.post(
        f"/v1/provider-accounts/{identity}/validate", headers=command_headers
    )
    assert first.status_code == 202 and first.json()["id"] == second.json()["id"]
    monkeypatch.setenv("REVIEW", '{"account_sid":"test","auth_token":"test"}')
    with patch(
        "notification.tasks.configuration.inspect_provider",
        return_value=Inspection(True, "checked"),
    ):
        assert await run_configuration_jobs(app.state.session_factory, app.state.settings) == 1
        assert await run_configuration_jobs(app.state.session_factory, app.state.settings) == 0
    after = await client.get(f"/v1/provider-accounts/{identity}", headers=proof)
    assert after.json()["status"] == "active"


@pytest.mark.asyncio
async def test_channel_disable_has_durable_planning_reason(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    proof = headers(tenant_a)
    assert (
        await client.put("/v1/channel-settings/email", json={"is_enabled": False}, headers=proof)
    ).status_code == 200
    with tenant_scope(tenant_a):
        planned = await handle_send_command(
            session, envelope(tenant_a, company, subject), cipher=CIPHER, key_ref=KEY_REF
        )
        await session.commit()
        outcome = await session.scalar(
            select(PlanningOutcome).where(PlanningOutcome.request_id == planned.request_id)
        )
        assert outcome is not None and outcome.reason_code == "channel_disabled"
        assert planned.deliveries_created == 0
    result = await client.get(f"/v1/requests/{planned.request_id}/outcomes", headers=proof)
    assert (
        result.status_code == 200 and result.json()["items"][0]["reason_code"] == "channel_disabled"
    )


@pytest.mark.asyncio
async def test_template_schema_preview_and_explicit_assignment(
    client: httpx.AsyncClient,
    tenant_a: uuid.UUID,
) -> None:
    proof = headers(tenant_a)
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    created = await client.post(
        "/v1/templates",
        headers=proof,
        json={
            "company_id": str(SCOPE_ALL),
            "key": "voucher",
            "event_key": "voucher.shared",
            "category": "transactional",
            "default_locale": "en",
            "variable_schema": schema,
        },
    )
    assert created.status_code == 201
    template = created.json()["id"]
    variant = (
        await client.post(
            f"/v1/templates/{template}/variants",
            headers=proof,
            json={"channel": "email", "locale": "en"},
        )
    ).json()["id"]
    invalid = await client.post(
        f"/v1/variants/{variant}/versions", headers=proof, json={"body_text": "{{ undeclared }}"}
    )
    assert invalid.status_code == 422
    v1 = await client.post(
        f"/v1/variants/{variant}/versions",
        headers=proof,
        json={"body_text": "Hello {{ name }}", "body_html": "<b>{{ name }}</b>"},
    )
    assert v1.status_code == 201
    preview = await client.post(
        f"/v1/template-versions/{v1.json()['id']}/preview",
        headers=proof,
        json={"variables": {"name": "<script>"}},
    )
    assert preview.json()["body_html"] == "<b>&lt;script&gt;</b>"
    assignment = {
        "company_id": str(SCOPE_ALL),
        "event_key": "voucher.shared",
        "trigger_key": "vouchers.voucher.share",
        "channel": "email",
        "template_id": template,
        "valid_from": (utcnow() - dt.timedelta(seconds=1)).isoformat(),
    }
    assert (
        await client.post("/v1/use-case-bindings", headers=proof, json=assignment)
    ).status_code == 201
    assert (
        await client.post("/v1/use-case-bindings", headers=proof, json=assignment)
    ).status_code == 409
    assignment["event_key"] = "user.invited"
    assert (
        await client.post("/v1/use-case-bindings", headers=proof, json=assignment)
    ).status_code == 422


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "https://untrusted.invalid"},
        {"type": "object", "required": ["unknown"]},
        {"type": "object", "properties": {"x": {"type": "object"}}},
        {"type": "object", "additionalProperties": True},
    ],
)
def test_variable_schema_rejects_unsupported_expressions(schema: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        validate_schema(schema)


def test_variables_and_channel_parameters_are_typed() -> None:
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    validate_variables(schema, {"count": 3})
    with pytest.raises(ValidationFailedError):
        validate_variables(schema, {"count": True})
    with pytest.raises(ValidationFailedError):
        validate_content(schema, ["{{ count }}"], {"template_parameters": ["unknown"]})

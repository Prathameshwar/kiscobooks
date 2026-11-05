from __future__ import annotations

import json
import time
import uuid
from typing import cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.service_auth import ServiceKey, service_request_bytes, sign_service_body
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.posting import OPERATIONS
from identity.config import CatalogSourceCredential, CatalogSourceScope
from identity.models import Company, PostingReservation
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies

SECRET = b"billing-posting-ephemeral-test-key-32"
KEY = ServiceKey("billing", "identity", OPERATIONS, SECRET)


def signed(
    method: str, path: str, body: bytes = b"", operation: str = "configuration"
) -> dict[str, str]:
    stamp = int(time.time())
    return {
        "content-type": "application/json",
        "x-source-key-id": "test",
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            KEY,
            key_id="test",
            operation="billing.posting." + operation,
            timestamp=stamp,
            body=service_request_bytes(method=method, path=path, query="", body=body),
        ),
    }


@pytest.mark.parametrize("outcome", ["confirmed", "aborted"])
async def test_reservation_freeze_replay_abort_and_confirm(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    outcome: str,
) -> None:
    company_id, other_id = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        actor = build_user(tenant_id=tenant_a)
        session.add(actor)
        await session.commit()
        user_id = actor.id
    settings = cast(FastAPI, app).state.settings
    settings.billing_reservation_credentials = {
        "test": CatalogSourceCredential(
            secret=SecretStr(SECRET.decode()),
            scopes=(CatalogSourceScope(tenant_id=tenant_a, company_id=company_id),),
        )
    }
    settings.billing_reservation_response_secret = SecretStr(
        "response-billing-ephemeral-test-key-32"
    )
    root = f"/internal/v1/tenants/{tenant_a}/companies/{company_id}/posting"
    config_path = root + "/configuration"
    assert (await client.get(config_path)).status_code == 401
    response = await client.get(config_path, headers=signed("GET", config_path))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    foreign = f"/internal/v1/tenants/{tenant_b}/companies/{other_id}/posting/configuration"
    assert (await client.get(foreign, headers=signed("GET", foreign))).status_code == 403
    operation = uuid.uuid4()
    body = {
        "operation_id": str(operation),
        "actor_user_id": str(user_id),
        "configuration_hash": response.json()["configuration_hash"],
        "features": [],
    }
    path = root + "/reservations"

    async def reserve(payload: dict[str, object]) -> httpx.Response:
        raw = json.dumps(payload).encode()
        return await client.post(path, content=raw, headers=signed("POST", path, raw, "reserve"))

    invalid = await reserve({**body, "configuration_hash": "0" * 64})
    assert invalid.status_code == 409, invalid.text
    first = await reserve(body)
    assert first.status_code == 200, first.text
    assert (await reserve(body)).json() == first.json()
    assert (await reserve({**body, "features": ["inventory"]})).status_code == 409
    auth = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[grant(["company.update"], scope_type="company", scope_id=company_id)],
    )
    editable = f"/v1/companies/{company_id}"
    assert (
        await client.patch(editable, headers=auth, json={"amount_precision": 3})
    ).status_code == 409
    display = await client.patch(
        editable, headers=auth, json={"display_name": "Safe display change"}
    )
    assert display.status_code == 200, display.text
    terminal = root + f"/reservations/{operation}/{outcome}"
    now = utcnow()
    result_body = {
        "terminal_reference": "billing-outbox-1",
        **({"posted_at": now.isoformat()} if outcome == "confirmed" else {}),
    }
    raw = json.dumps(result_body).encode()
    for _ in range(2):
        result = await client.post(
            terminal, content=raw, headers=signed("POST", terminal, raw, outcome)
        )
        assert result.status_code == 200, result.text
        assert result.json()["status"] == outcome
    opposite = "aborted" if outcome == "confirmed" else "confirmed"
    wrong = root + f"/reservations/{operation}/{opposite}"
    wrong_body = json.dumps(
        {
            "terminal_reference": "contradiction",
            **({"posted_at": now.isoformat()} if opposite == "confirmed" else {}),
        }
    ).encode()
    assert (
        await client.post(
            wrong, content=wrong_body, headers=signed("POST", wrong, wrong_body, opposite)
        )
    ).status_code == 409
    changed = await client.patch(editable, headers=auth, json={"amount_precision": 3})
    assert changed.status_code == (422 if outcome == "confirmed" else 200), changed.text
    with tenant_scope(tenant_a):
        session.expire_all()
        company = await session.get(Company, company_id)
        assert company is not None
        assert (
            (company.first_posted_at == now)
            if outcome == "confirmed"
            else (company.first_posted_at is None)
        )
        rows = list(await session.scalars(select(PostingReservation)))
        assert len(rows) == 1 and rows[0].status == outcome
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "identity.posting_reservation.terminal")
            )
        )
        assert len(events) == 1
    with tenant_scope(tenant_b):
        assert not list(await session.scalars(select(PostingReservation)))

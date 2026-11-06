"""Separate service credentials cannot terminate each other's posting reservations."""

import secrets
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI
from identity_posting import PostingClient, ReservationRejectedError
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import CatalogSourceCredential, CatalogSourceScope
from tests.factories import build_user, seed_two_companies


async def test_enrolled_accounting_posting_grant_requires_an_active_native_company(
    app: FastAPI, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    secret, response_secret = secrets.token_hex(32), secrets.token_hex(32)
    app.state.settings.accounting_reservation_credentials = {
        "enrolled": CatalogSourceCredential(
            secret=SecretStr(secret), scopes=(), allow_enrolled_companies=True
        )
    }
    app.state.settings.accounting_reservation_response_secret = SecretStr(response_secret)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://identity.test"
    ) as http:
        posting = PostingClient(
            http, key_id="enrolled", request_secret=secret.encode(),
            response_keys={"current": response_secret.encode()}, issuer="accounting",
        )
        assert (await posting.configuration(tenant_a, company)).company_id == company
        with pytest.raises(ReservationRejectedError) as refused:
            await posting.configuration(tenant_a, other)
        assert refused.value.status_code == 403
        from identity.models import Company

        with tenant_scope(tenant_a):
            row = await session.get(Company, company)
            assert row is not None
            row.status = "suspended"
            await session.commit()
        with pytest.raises(ReservationRejectedError) as suspended:
            await posting.configuration(tenant_a, company)
        assert suspended.value.status_code == 403


async def test_accounting_reservations_are_bound_to_the_service(
    app: FastAPI,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
    request_secret = secrets.token_hex(32)
    response_secret = secrets.token_hex(32)
    credentials = {
        "client": CatalogSourceCredential(
            secret=SecretStr(request_secret),
            scopes=(CatalogSourceScope(tenant_id=tenant_a, company_id=company),),
        )
    }
    app.state.settings.billing_reservation_credentials = credentials
    app.state.settings.billing_reservation_response_secret = SecretStr(response_secret)
    app.state.settings.accounting_reservation_credentials = credentials
    app.state.settings.accounting_reservation_response_secret = SecretStr(response_secret)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://identity.test"
    ) as http:
        billing = PostingClient(
            http,
            key_id="client",
            request_secret=request_secret.encode(),
            response_keys={"current": response_secret.encode()},
        )
        accounting = PostingClient(
            http,
            key_id="client",
            request_secret=request_secret.encode(),
            response_keys={"current": response_secret.encode()},
            issuer="accounting",
        )
        config = await accounting.configuration(tenant_a, company)
        operation = uuid7()
        params: dict[str, Any] = {
            "operation_id": operation,
            "actor_user_id": user.id,
            "configuration_hash": config.configuration_hash,
            "features": [],
        }
        receipt = await billing.reserve(tenant_a, company, **params)
        assert receipt.status == "pending"
        with pytest.raises(ReservationRejectedError) as denied:
            await accounting.terminal(
                tenant_a,
                company,
                operation_id=operation,
                outcome="aborted",
                reference="wrong-service",
            )
        assert denied.value.status_code == 404
        with pytest.raises(ReservationRejectedError):
            await accounting.reserve(tenant_a, company, **params)
        own = uuid7()
        params["operation_id"] = own
        reserved = await accounting.reserve(tenant_a, company, **params)
        assert reserved.status == "pending"
        assert await accounting.reserve(tenant_a, company, **params) == reserved
        confirmed = await accounting.terminal(
            tenant_a,
            company,
            operation_id=own,
            outcome="confirmed",
            reference="accounting-journal:" + str(own),
            posted_at=utcnow(),
        )
        assert confirmed.status == "confirmed"

        # A prepared journal can be canceled before Identity has ever seen reserve.
        # The cancellation must survive subsequent company edits, and block a late reserve.
        late = uuid7()
        params["operation_id"] = late
        from identity.models import Company

        with tenant_scope(tenant_a):
            stored_company = await session.get(Company, company)
            assert stored_company is not None
            stored_company.amount_precision = 3
            await session.commit()
        raw = await accounting._request(
            accounting._root(tenant_a, company) + f"/reservations/{late}/aborted",
            "aborted",
            {
                "terminal_reference": "accounting-journal:" + str(late),
                "posted_at": None,
                "intent": {
                    "operation_id": str(late),
                    "actor_user_id": str(user.id),
                    "configuration_hash": config.configuration_hash,
                    "features": [],
                },
            },
        )
        from identity_posting import Receipt

        assert Receipt.model_validate_json(raw).status == "aborted"
        assert (await accounting.reserve(tenant_a, company, **params)).status == "aborted"


def test_cancellation_openapi_contains_resolved_intent_schema() -> None:
    import json

    from identity.api.posting import TerminalRequest, contract_headers

    schema = contract_headers(TerminalRequest)
    assert "#/$defs/" not in json.dumps(schema)

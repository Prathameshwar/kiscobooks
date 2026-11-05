from __future__ import annotations

import base64
import time
import uuid
from typing import cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.models import CompanyBankAccount, RoleAssignment, UserApiToken
from identity.services.banks import EncryptionUnavailableError, decrypt_details, encrypt_details
from tests.api_support import actor_headers, grant
from tests.factories import build_role_permission, seed_two_companies
from tests.test_gap_login import bearer, seed_login


@pytest.fixture(scope="module")
def key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": "web"})


async def test_hash_only_token_consumption_live_revocation_and_no_reissue(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    key: RSAKey,
) -> None:
    await seed_login(factory, tenant_a, tenant_b)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        cast(FastAPI, app).state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        headers = bearer(key, auth_time=int(time.time()))
        response = await client.post(
            "/v1/session/api-tokens",
            headers=headers,
            json={"name": "Reporting", "permissions": ["user.read"]},
        )
        assert response.status_code == 201, response.text
        token = response.json()["token"]
        tid = response.json()["details"]["id"]
        assert response.headers["cache-control"] == "no-store"
        token_headers = {"Authorization": "Bearer " + token}
        assert (await client.get("/v1/users", headers=token_headers)).status_code == 200
        assert token not in (await client.get("/v1/session/api-tokens", headers=headers)).text
        assert (
            await client.post(
                "/v1/session/api-tokens",
                headers=token_headers,
                json={"name": "Chain", "permissions": ["user.read"]},
            )
        ).status_code == 403
        assert (
            await client.post(
                "/v1/session/api-tokens",
                headers=headers,
                json={"name": "Escalate", "permissions": ["company.update"]},
            )
        ).status_code == 403
        async with factory() as db, db.begin():
            with tenant_scope(tenant_a):
                row = await db.get(UserApiToken, uuid.UUID(tid))
                assert row is not None and token not in str(row.__dict__)
                events = list(await db.scalars(select(Outbox)))
                assert token not in str([e.payload for e in events])
                assignment = (await db.scalars(select(RoleAssignment))).one()
                assignment.is_active = False
        assert (await client.get("/v1/users", headers=token_headers)).status_code == 403
        assert (
            await client.post(
                f"/v1/api-tokens/{tid}/revoke", headers=headers, json={"reason": "rotate"}
            )
        ).status_code == 200
        assert (await client.get("/v1/session", headers=token_headers)).status_code == 401
        assert (
            await client.get("/v1/users", headers={"Authorization": "Bearer " + token[:-1] + "!"})
        ).status_code == 401
        assert (
            await client.get("/v1/users", headers={"Authorization": "Bearer jpat_short"})
        ).status_code == 401


async def test_encrypted_bank_scope_masking_tamper_and_key_rotation(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    application = cast(FastAPI, app)
    from pydantic import SecretStr

    application.state.settings.bank_active_key_id = "v1"
    application.state.settings.bank_encryption_keys = {
        "v1": SecretStr(base64.b64encode(bytes(range(32))).decode())
    }
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid.uuid4(),
        grants=[grant(["company.read", "company.update"], scope_type="company", scope_id=company)],
    )
    url = f"/v1/companies/{company}/bank-accounts"
    body = {
        "label": "Receipts",
        "account_name": "Private owner",
        "bank_name": "Test bank",
        "currency_code": "INR",
        "account_number": "123456789012",
        "is_primary": True,
    }
    response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 201, response.text
    bid = response.json()["id"]
    assert response.json()["account_last4"] == "9012"
    assert "123456789012" not in response.text
    assert "account_number" not in (await client.get(url, headers=headers)).text
    assert (
        await client.post(url + f"/{bid}/reveal", headers=headers, json={"reason": "payment setup"})
    ).status_code == 403
    assert (
        await client.get(f"/v1/companies/{other}/bank-accounts/{bid}", headers=headers)
    ).status_code == 403
    with tenant_scope(tenant_a):
        row = await session.get(CompanyBankAccount, uuid.UUID(bid))
        assert row is not None and row.account_number is None and row.iban is None
        assert row.details_ciphertext is not None and b"123456789012" not in row.details_ciphertext
        assert (
            decrypt_details(row, application.state.settings)["account_number"]
            == body["account_number"]
        )
        previous = row.company_id
        row.company_id = other
        with pytest.raises(EncryptionUnavailableError):
            decrypt_details(row, application.state.settings)
        row.company_id = previous
        application.state.settings.bank_encryption_keys["v2"] = SecretStr(
            base64.b64encode(bytes(reversed(range(32)))).decode()
        )
        application.state.settings.bank_active_key_id = "v2"
        clear = decrypt_details(row, application.state.settings)
        encrypt_details(row, application.state.settings, **clear)
        assert row.encryption_key_id == "v2"
        del application.state.settings.bank_encryption_keys["v1"]
        assert decrypt_details(row, application.state.settings) == clear
        await session.rollback()
    for enabled in [False, False, True]:
        result = await client.post(
            url + f"/{bid}/lifecycle",
            headers=headers,
            json={"is_active": enabled, "reason": "maintenance"},
        )
        assert result.status_code == 200, result.text


async def test_sensitive_reveal_requires_fresh_provider_and_is_audited(
    app: object,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    key: RSAKey,
) -> None:
    await seed_login(factory, tenant_a, tenant_b)
    from pydantic import SecretStr

    from tests.factories import build_company

    async with factory() as db, db.begin():
        with tenant_scope(tenant_a):
            company = build_company(tenant_id=tenant_a)
            db.add(company)
            assignment = (await db.scalars(select(RoleAssignment))).one()
            db.add(
                build_role_permission(
                    tenant_id=tenant_a, role_id=assignment.role_id, permission_key="company.update"
                )
            )
            cid = company.id
    application = cast(FastAPI, app)
    application.state.settings.bank_active_key_id = "test"
    application.state.settings.bank_encryption_keys = {
        "test": SecretStr(base64.b64encode(bytes(range(32))).decode())
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key.as_dict()]}))
    ) as provider:
        application.state.token_verifier = AccessTokenVerifier(
            OidcConfig("https://id.test/", "web", "https://id.test/jwks"), provider
        )
        headers = bearer(key, auth_time=int(time.time()))
        bank = await client.post(
            f"/v1/companies/{cid}/bank-accounts",
            headers=headers,
            json={
                "label": "Main",
                "account_name": "Owner",
                "bank_name": "Bank",
                "currency_code": "INR",
                "account_number": "123456789",
            },
        )
        assert bank.status_code == 201, bank.text
        url = f"/v1/companies/{cid}/bank-accounts/{bank.json()['id']}/reveal"
        assert (
            await client.post(
                url,
                headers=bearer(key, auth_time=int(time.time()) - 600),
                json={"reason": "settlement"},
            )
        ).status_code == 403
        response = await client.post(url, headers=headers, json={"reason": "settlement"})
        assert response.status_code == 200, response.text
        assert response.json()["account_number"] == "123456789"
        assert response.headers["cache-control"] == "no-store"
        async with factory() as db:
            with tenant_scope(tenant_a):
                events = list(
                    await db.scalars(
                        select(Outbox).where(Outbox.event_type == "company.bank_revealed")
                    )
                )
                assert len(events) == 1 and "123456789" not in str(events[0].payload)

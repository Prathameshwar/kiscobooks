from __future__ import annotations

import base64
import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyBankAccount
from identity.services.banks import EncryptionUnavailableError, aad, cipher, decrypt_details
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_companies


async def test_bank_primary_update_validation_and_storage_errors(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read", "company.update"])]
    )
    config = app.state.settings
    config.bank_active_key_id = "one"
    config.bank_encryption_keys = {
        "one": SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    }
    root = f"/v1/companies/{company}/bank-accounts"
    body = {
        "label": "Payments",
        "account_name": "Private owner",
        "bank_name": "Private bank",
        "currency_code": "INR",
        "account_number": "12345678",
        "is_primary": True,
    }
    first = await client.post(root, headers=headers, json=body)
    second = await client.post(root, headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    fid, sid = first.json()["id"], second.json()["id"]
    assert (await client.get(root + "/" + fid, headers=headers)).json()["is_primary"] is False
    updated = await client.put(
        root + "/" + fid, headers=headers, json={**body, "account_number": "98765432"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["account_last4"] == "5432"
    assert (await client.get(root + "/" + sid, headers=headers)).json()["is_primary"] is False
    for invalid in (
        {**body, "currency_code": "ZZZ"},
        {**body, "account_number": None},
        {**body, "account_number": "abcd\u00e9"},
    ):
        assert (await client.post(root, headers=headers, json=invalid)).status_code == 422
    assert (await client.get(root + f"/{uuid7()}", headers=headers)).status_code == 404
    assert (
        await client.post(f"/v1/companies/{company}/bank-encryption/rotate", headers=headers)
    ).status_code == 403
    assert (
        await client.post(
            root + "/" + fid + "/lifecycle",
            headers=headers,
            json={"is_active": False, "reason": "retired"},
        )
    ).status_code == 200
    assert (await client.put(root + "/" + fid, headers=headers, json=body)).status_code == 409
    with tenant_scope(tenant_a):
        row = await session.get(CompanyBankAccount, uuid.UUID(sid))
        assert row
        encrypted = row.details_ciphertext
        row.details_ciphertext = None
        with pytest.raises(EncryptionUnavailableError):
            decrypt_details(row, config)
        row.details_ciphertext = cipher(config, "one").encrypt(
            b'{"unexpected":"value"}', nonce=secrets.token_bytes(12), associated_data=aad(row)
        )
        with pytest.raises(EncryptionUnavailableError):
            decrypt_details(row, config)
        row.details_ciphertext = encrypted
    config.bank_encryption_keys = {"one": SecretStr("not-base64")}
    with pytest.raises(EncryptionUnavailableError):
        cipher(config, "one")
    config.bank_encryption_keys = {}
    assert (await client.post(root, headers=headers, json=body)).status_code == 503

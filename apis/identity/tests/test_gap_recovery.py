from __future__ import annotations

import base64
import datetime as dt
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.api.auth import Actor
from identity.config import Settings
from identity.models import CompanyBankAccount, CustomFieldValueIndex, ImpersonationSession
from identity.services.banks import decrypt_details
from identity.tasks.bank_encryption import rotate_batch
from identity.tasks.support_expiry import expire_batch
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company_bank_account,
    build_impersonation_session,
    seed_two_companies,
)


async def test_bank_backfill_rotation_replay_and_expiry_sweep(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    async with factory() as db:
        company, foreign = await seed_two_companies(db, tenant_a, tenant_b)
    actor = Actor(tenant_a, uuid.uuid4())
    cfg = Settings(
        database_url="sqlite+aiosqlite://",
        actor_signing_secret=SecretStr("test"),
        cursor_signing_secret=SecretStr("x" * 32),
        bank_active_key_id="one",
        bank_encryption_keys={"one": SecretStr(base64.b64encode(bytes(32)).decode())},
    )
    async with factory() as db, db.begin():
        with tenant_scope(tenant_a):
            db.add_all(
                [
                    build_company_bank_account(
                        tenant_id=tenant_a, company_id=company, is_primary=False
                    )
                    for _ in range(2)
                ]
            )
            row = build_impersonation_session(
                tenant_id=tenant_a,
                actor_user_id=actor.user_id,
                target_user_id=uuid.uuid4(),
                expires_at=utcnow() - dt.timedelta(seconds=1),
            )
            db.add(row)
            sid = row.id
        with tenant_scope(tenant_b):
            db.add(build_company_bank_account(tenant_id=tenant_b, company_id=foreign))
    for expected in (1, 1, 0):
        with tenant_scope(tenant_a):
            async with factory() as db, db.begin():
                assert await rotate_batch(db, actor, cfg, company, limit=1) == expected
    cfg.bank_active_key_id = "two"
    cfg.bank_encryption_keys["two"] = SecretStr(base64.b64encode(bytes(range(32))).decode())
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            assert await rotate_batch(db, actor, cfg, company) == 2
            rows = list(await db.scalars(select(CompanyBankAccount)))
            assert all(
                r.account_number is None
                and decrypt_details(r, cfg)["account_number"] == "000123456789"
                for r in rows
            )
    assert await expire_batch(factory) == 1
    assert await expire_batch(factory) == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            ended = await db.get(ImpersonationSession, sid)
            assert ended and ended.ended_reason == "expired" and ended.ended_at == ended.expires_at
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "user.impersonation_expired")
                )
            )
            assert len(events) == 1
    with tenant_scope(tenant_b):
        async with factory() as db:
            untouched = (await db.scalars(select(CompanyBankAccount))).one()
            assert untouched.details_ciphertext is None


async def test_index_rebuild_and_contract_change_are_consistent(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid.uuid4(),
        grants=[grant(["company.read", "company.update", "custom_field.manage"])],
    )
    body = {
        "label": "Code",
        "definition": {
            "key": "cf_code",
            "data_type": "text",
            "is_searchable": True,
            "validation": {"max_length": 30},
        },
    }
    created = await client.post("/v1/custom-field-definitions", json=body, headers=headers)
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    assert (
        await client.patch(
            f"/v1/companies/{company}", json={"custom_fields": {"cf_code": "ABC"}}, headers=headers
        )
    ).status_code == 200
    body["definition"]["validation"]["case_sensitive"] = False
    changed = await client.put(f"/v1/custom-field-definitions/{did}", json=body, headers=headers)
    assert changed.status_code == 200, changed.text
    params = {"custom_field": "cf_code", "custom_value": "abc"}
    assert (
        len((await client.get("/v1/companies", params=params, headers=headers)).json()["items"])
        == 1
    )
    with tenant_scope(tenant_a):
        await session.execute(delete(CustomFieldValueIndex))
        await session.commit()
    result = await client.post(
        f"/v1/custom-field-definitions/{did}/rebuild", headers=headers, json={"limit": 1}
    )
    assert result.status_code == 200, result.text
    assert result.json()["processed"] == 1
    assert (
        len((await client.get("/v1/companies", params=params, headers=headers)).json()["items"])
        == 1
    )
    assert (
        await client.post(
            f"/v1/custom-field-definitions/{did}/rebuild",
            headers=headers,
            json={"after": str(company), "definition_hash": "bad"},
        )
    ).status_code == 409

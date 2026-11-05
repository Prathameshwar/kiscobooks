"""Dated mapping corrections preserve used stock and exact command recovery."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.api.auth import delegated_access
from accounting.models.masters import Account, AccountingSetup
from accounting.models.stock import StockAccountPolicy, StockExecutionPlan
from accounting.tasks.stock_policy import effective
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_ledger_api import BASE as ACCOUNTING
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_stock_effects import authority, configure
from tests.test_stock_ledger import ledger, values

BASE = f"/v1/companies/{COMPANY}/stock"


def headers(key=None, **extra):
    return ledger_headers(
        permissions={"accounting.stock.read", "accounting.stock.configure"},
        features={"inventory"},
        key=key,
        **extra,
    )


async def prepared(client, app):
    await journal_setup(client, app)
    mapping = await configure(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            policy = await db.scalar(select(StockAccountPolicy))
            generation = await db.scalar(select(AccountingSetup.generation))
            return policy.id, {
                **{key: str(value) for key, value in mapping.items()},
                "expected_generation": generation,
                "valid_from": "2026-04-01",
                "reason": "Reviewed native inventory mapping",
            }


async def test_correct_unused_initial_date_and_exact_retry(client, app):
    identity, body = await prepared(client, app)
    config = await client.get(BASE + "/configuration", headers=headers())
    assert config.json()["correctable_policy_id"] == str(identity)
    body |= {"correct_unused_id": str(identity), "valid_from": "2026-03-01"}
    key = str(uuid7())
    saved = await client.post(BASE + "/account-policies", headers=headers(key), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == str(identity)
    assert saved.json()["valid_from"] == "2026-03-01"
    replay = await client.post(BASE + "/account-policies", headers=headers(key), json=body)
    assert replay.status_code == 200 and replay.json() == saved.json()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            policies = list(await db.scalars(select(StockAccountPolicy)))
            assert len(policies) == 1 and policies[0].row_version == 2


async def test_mapping_correction_cannot_target_other_company_or_hide_field_write(client, app):
    identity, body = await prepared(client, app)
    denied = await client.post(
        BASE + "/account-policies",
        headers=headers(str(uuid7())),
        json=body | {"correct_unused_id": str(uuid7())},
    )
    assert denied.status_code == 409
    denied = await client.post(
        BASE + "/account-policies",
        headers=headers(
            str(uuid7()),
            policies=[
                {
                    "entity_type": "accounting.stock_account_policy",
                    "field_key": "valid_from",
                    "access": "write",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ],
        ),
        json=body | {"correct_unused_id": str(identity), "valid_from": "2026-03-01"},
    )
    assert denied.status_code == 403, denied.text


async def test_stock_account_cannot_change_when_pre_scheduled_mapping_takes_effect(client, app):
    identity, body = await prepared(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            original = await db.get(StockAccountPolicy, identity)
            original.valid_to = dt.date(2026, 4, 30)
            future = StockAccountPolicy(
                **values(),
                valid_from=dt.date(2026, 5, 1),
                valid_to=None,
                reason="Future configuration entered before first stock",
                **{key: getattr(original, key) for key in body if key.endswith("account_id")},
            )
            # A second valid asset account deliberately makes this future mapping incompatible.
            account = await db.get(Account, original.inventory_account_id)
            replacement = Account(
                **values(),
                code="FUTURE_STOCK",
                name="Future inventory",
                group_id=account.group_id,
                kind="GENERAL",
                status="ACTIVE",
            )
            db.add(replacement)
            await db.flush()
            future.inventory_account_id = replacement.id
            db.add(future)
            await ledger(db, day=dt.date(2026, 4, 2), account_policy_id=identity)
        async with app.state.session_factory() as db:
            current = delegated_access(
                authority(),
                SECRET.encode(),
                tenant_id=TENANT,
                company_id=COMPANY,
                actor_user_id=USER,
            )
            with pytest.raises(ConflictError, match="reclassification"):
                await effective(db, current, dt.date(2026, 5, 2))


@pytest.mark.parametrize("prepared_only", [False, True])
async def test_used_or_inflight_mapping_is_not_correctable(client, app, prepared_only):
    identity, body = await prepared(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(
                db,
                day=dt.date(2026, 4, 2),
                account_policy_id=None if prepared_only else identity,
            )
            if prepared_only:
                db.add(
                    StockExecutionPlan(
                        **values(),
                        intent_id=owner.posting.intent_id,
                        execution_id=owner.posting.execution_id,
                        source_fence_id=uuid7(),
                        source_fence_expires_at=utcnow() + dt.timedelta(seconds=60),
                        semantic_hash="a" * 64,
                        source_facts={},
                        effects={},
                    )
                )
    configuration = await client.get(BASE + "/configuration", headers=headers())
    assert configuration.json()["correctable_policy_id"] is None
    denied = await client.post(
        BASE + "/account-policies",
        headers=headers(str(uuid7())),
        json=body | {"correct_unused_id": str(identity), "valid_from": "2026-05-01"},
    )
    assert denied.status_code == 409, denied.text


async def test_existing_ordinary_posted_gl_cannot_be_adopted_as_native_inventory(client, app):
    identity, body = await prepared(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            original = await db.get(Account, uuid.UUID(body["inventory_account_id"]))
            replacement = Account(
                **values(),
                code="UNCONTROLLED",
                name="Existing asset with manual entries",
                group_id=original.group_id,
                kind="GENERAL",
                status="ACTIVE",
            )
            db.add(replacement)
            await db.flush()
            account_id = replacement.id
    # Use the ordinary journal API before this account belongs to any stock mapping.
    accounts = (
        await client.get(ACCOUNTING + "/accounts?limit=200", headers=ledger_headers())
    ).json()["items"]
    other = next(row for row in accounts if row["kind"] == "CASH")
    created = await client.post(
        ACCOUNTING + "/journals",
        headers=ledger_headers(),
        json={
            "document_date": "2026-04-02",
            "posting_date": "2026-04-02",
            "description": "Existing ungoverned asset journal",
            "lines": [
                {
                    "account_id": str(account_id),
                    "side": "DEBIT",
                    "currency": "INR",
                    "amount": "10",
                    "exchange_rate": "1",
                },
                {
                    "account_id": other["id"],
                    "side": "CREDIT",
                    "currency": "INR",
                    "amount": "10",
                    "exchange_rate": "1",
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    posted = await client.post(
        ACCOUNTING + "/journals/" + created.json()["id"] + "/post",
        headers=ledger_headers(),
        json={"expected_version": created.json()["row_version"]},
    )
    assert posted.status_code == 200, posted.text
    configuration = (await client.get(BASE + "/configuration", headers=headers())).json()
    denied = await client.post(
        BASE + "/account-policies",
        headers=headers(str(uuid7())),
        json=body
        | {
            "inventory_account_id": str(account_id),
            "correct_unused_id": str(identity),
            "expected_generation": configuration["generation"],
        },
    )
    assert denied.status_code == 409, denied.text
    assert "manual posted history" in denied.json()["error"]["message"]

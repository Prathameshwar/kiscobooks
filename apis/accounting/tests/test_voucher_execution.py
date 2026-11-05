"""Contract adapter fault tests; the callback is not an activated financial profile."""

import asyncio
import datetime as dt
import hashlib
import secrets
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from sqlalchemy import func, select
from voucher_execution import ExecutionCommand
from voucher_execution.transport import ExecutionClient, command_digest

from accounting.models.voucher_execution import VoucherExecution, VoucherSourceGuard
from accounting.tasks.voucher_execution import execute
from tests.conftest import COMPANY, TENANT, USER
from tests.test_fiscal_api import BASE, change, fiscal_setup
from tests.test_ledger_api import ledger_headers
from tests.test_masters import prepare


def command(period=None, **values):
    content = {"lines": [{"line_key": str(uuid7()), "description": "contract fixture"}]}
    body = ExecutionCommand(
        tenant_id=TENANT,
        company_id=COMPANY,
        voucher_id=uuid7(),
        revision_id=uuid7(),
        operation_id=uuid7(),
        execution_id=uuid7(),
        purpose="POST",
        content_hash=hashlib.sha256(canonical_json(content)).hexdigest(),
        configuration_hash="b" * 64,
        company_configuration_hash="a" * 64,
        request_hash="0" * 64,
        source_payload=content,
        posting_date=dt.date(2026, 4, 2),
        period_versions={uuid.UUID(period["id"]): period["row_version"]} if period else {},
        actor_user_id=USER,
        authority_expires_at=utcnow() + dt.timedelta(minutes=2),
    )
    body = body.model_copy(update=values)
    return body.model_copy(update={"request_hash": command_digest(body)})


async def accepted(db, body):
    return ()


async def run(app, body, executor=accepted):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            return await execute(db, body, executor=executor)


async def test_signed_command_cancel_before_delivery_reconcile_and_scope(client, app):
    secret = secrets.token_bytes(32)
    key = "vouchers.execution.test"
    app.state.settings.voucher_execution_credentials[key] = SnapshotCredential(
        secret=SecretStr(secret.hex()),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    transport = ExecutionClient(client, "http://127.0.0.1", key, secret.hex().encode())
    body = command()
    cancelled = await transport.send(body, purpose="CANCEL")
    assert cancelled.outcome == "CANCELLED"
    assert await transport.send(body) == cancelled
    assert await transport.status(body) == cancelled
    rejected = await transport.send(command())
    assert rejected.rejection_code == "UNSUPPORTED_PROFILE"
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.send(command(company_id=uuid7()))
    assert error.value.response.status_code == 401
    with pytest.raises(httpx.HTTPStatusError) as conflict:
        await transport.send(body.model_copy(update={"content_hash": "e" * 64}))
    assert conflict.value.response.status_code == 409


async def test_committed_receipt_survives_lost_ack_close_expiry_and_different_attempt(
    client, app, monkeypatch
):
    periods = await fiscal_setup(client)
    opened = await change(client, periods[0], "OPEN")
    assert opened.status_code == 200
    zero = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero opening balances"},
        headers=ledger_headers(),
    )
    assert zero.status_code == 201, zero.text
    finalized = await client.post(
        BASE + f"/opening-batches/{zero.json()['id']}/finalize-zero",
        json={"expected_version": zero.json()["row_version"]},
        headers=ledger_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    body = command(opened.json())
    result = await run(app, body)
    assert result.outcome == "COMMITTED" and len(result.effects) == 1
    assert result.committed_generation is not None and result.committed_generation > 0
    closed = await change(client, opened.json(), "SOFT_CLOSED")
    assert closed.status_code == 200, closed.text
    with monkeypatch.context() as clock:
        clock.setattr(
            "accounting.tasks.voucher_execution.utcnow",
            lambda: dt.datetime(2027, 4, 1, tzinfo=dt.UTC),
        )
        assert await run(app, body) == result
    assert await run(app, body.model_copy(update={"purpose": "CANCEL"})) == result
    another = command(opened.json(), voucher_id=body.voucher_id)
    assert (await run(app, another)).rejection_code == "SOURCE_CONFLICT"
    stale = command(opened.json())
    assert (await run(app, stale)).rejection_code == "CLOSED_PERIOD"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherExecution.id))) == 3


async def test_callback_failure_rolls_back_and_same_attempt_recovers(client, app):
    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    body = command(opened)

    async def failed(db, body):
        raise RuntimeError("injected crash before owner commit")

    with pytest.raises(RuntimeError):
        await run(app, body, failed)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherExecution.id))) == 0
            assert await db.scalar(select(func.count(VoucherSourceGuard.id))) == 0
    result = await run(app, body)
    assert result.outcome == "COMMITTED"
    assert await run(app, body) == result


@pytest.mark.parametrize(
    "mutation,code",
    [
        ({"posting_date": dt.date(2027, 4, 1)}, "CLOSED_PERIOD"),
        ({"authority_expires_at": dt.datetime(2020, 1, 1, tzinfo=dt.UTC)}, "STALE_AUTHORITY"),
        ({"period_versions": {}}, "CLOSED_PERIOD"),
    ],
)
async def test_commit_rechecks_company_period_year_and_authority(client, app, mutation, code):
    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    assert (await run(app, command(opened, **mutation))).rejection_code == code


async def test_a_feature_enabled_after_books_setup_does_not_block_posting(client, app):
    # The live digest is checked against the delegated context (authority()); the setup-time
    # digest is not frozen book state, so a later feature change must not refuse every post.
    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    result = await run(app, command(opened, company_configuration_hash="c" * 64))
    assert (result.outcome, result.rejection_code) == ("COMMITTED", None)


async def test_missing_financial_setup_is_still_a_configuration_change(client, app):
    await prepare(client)
    assert (await run(app, command())).rejection_code == "CONFIGURATION_CHANGED"


async def test_owner_receipts_cannot_be_rewritten(client, app):
    result = await run(app, command(), None)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(select(VoucherExecution))
            row.result = {}
            with pytest.raises(ConflictError, match="immutable"):
                await db.commit()
            await db.rollback()
    assert result.outcome == "REJECTED"


@pytest.mark.mysql
async def test_native_close_race_and_duplicate_delivery(client, app, engine):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("requires native row locking")
    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    # The close race starts from a financially ready year, as the ordinary
    # committed-receipt case above does. An unfinished opening correctly refuses close.
    zero = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero opening balances"},
        headers=ledger_headers(),
    )
    assert zero.status_code == 201, zero.text
    finalized = await client.post(
        BASE + f"/opening-batches/{zero.json()['id']}/finalize-zero",
        json={"expected_version": zero.json()["row_version"]},
        headers=ledger_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    body = command(opened)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def held(db, body):
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.wait_for(release.wait(), 10)
        return ()

    posting = asyncio.create_task(run(app, body, held))
    await asyncio.wait_for(entered.wait(), 10)
    closing = asyncio.create_task(change(client, opened, "SOFT_CLOSED"))
    duplicate = asyncio.create_task(run(app, body, held))
    await asyncio.sleep(0.05)
    assert not closing.done()
    release.set()
    first, second, closed = await asyncio.gather(posting, duplicate, closing)
    assert first == second and first.outcome == "COMMITTED" and calls == 1
    assert closed.status_code == 200, closed.text
    assert (await run(app, command(opened))).rejection_code == "CLOSED_PERIOD"


async def test_authority_expiring_inside_callback_cannot_commit(client, app, monkeypatch):
    periods = await fiscal_setup(client)
    opened = (await change(client, periods[0], "OPEN")).json()
    body = command(opened)

    async def expired(db, command):
        monkeypatch.setattr(
            "accounting.tasks.voucher_execution.utcnow",
            lambda: command.authority_expires_at + dt.timedelta(seconds=1),
        )
        return ()

    with pytest.raises(ConflictError, match="expired before commit"):
        await run(app, body, expired)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherExecution.id))) == 0
            assert await db.scalar(select(func.count(VoucherSourceGuard.id))) == 0
    rejected = await run(app, body)
    assert rejected.rejection_code == "STALE_AUTHORITY"

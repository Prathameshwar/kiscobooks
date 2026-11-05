"""Opt-in production financial workflows through native MySQL and real audit transport."""

import asyncio
import importlib
import inspect
import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest
from billing_platform.broker import (
    BrokerSource,
    ConfirmedPublisher,
    confirmed_channel,
    declare_consumer_queue,
)
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.delivery import publish_batch
from billing_platform.service_auth import ServiceKey
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from accounting.events.audit_contract import AUDIT_EVENTS
from tests.conftest import TENANT

CASES = [
    ("test_voucher_money", "test_journal_posts_one_number_and_native_tender_with_lost_ack_replay"),
    ("test_voucher_money", "test_pure_bill_adjustment_and_reversal_create_no_cash_journal"),
    (
        "test_money_profiles",
        "test_contra_and_split_cheques_post_once_and_clearing_does_not_move_cash",
    ),
    ("test_workflows", "test_import_preview_rollback_apply_replay_and_stale"),
    ("test_ledger_api", "test_journal_posts_once_then_reverses_without_changing_history"),
    ("test_fiscal_api", "test_fiscal_setup_generation_transitions_and_history"),
    ("test_credit_api", "test_override_requires_other_approver_and_binds_source"),
    ("test_charges_api", "test_charge_preview_approval_posting_coverage_and_reversal"),
    ("test_charges_api", "test_stale_calculation_rejected_and_waiver_keeps_coverage"),
]
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(
    not (
        os.environ.get("ACCOUNTING_TEST_DATABASE_URL")
        and os.environ.get("IDENTITY_TEST_BROKER_URL")
    ),
    reason="explicit disposable native Accounting schema and local broker required",
)
@pytest.mark.parametrize("module_name,function_name", CASES)
async def test_financial_command_to_native_audit(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    function_name: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "apis/audit/src"))
    from audit.models import AuditEvent
    from audit.tasks.consume import receive_audit
    from audit.tasks.verify import verify_tenant_chain

    url = make_url(os.environ["ACCOUNTING_TEST_DATABASE_URL"])
    assert url.host in {"127.0.0.1", "localhost"} and (url.database or "").startswith(
        "accounting_test_"
    )
    broker_url = os.environ["IDENTITY_TEST_BROKER_URL"]
    assert "@127.0.0.1:5672/bill_identity_test" in broker_url
    schema = "audit_financial_test_" + uuid.uuid4().hex  # generated identifier, no caller input
    audit_url = url.set(database=schema).render_as_string(hide_password=False)
    admin = create_engine(url.set(database=None).render_as_string(hide_password=False))
    engine = create_engine(audit_url)
    factory = create_session_factory(engine)
    name = "audit-financial-proof-" + uuid.uuid4().hex
    async with admin.connect() as connection:
        await connection.execute(text(f"CREATE DATABASE `{schema}`"))
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                str(ROOT / "apis/audit/.venv/Scripts/python.exe"),
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT / "dbs/audit",
            env=dict(os.environ, AUDIT_DATABASE_URL=audit_url),
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        assert result.returncode == 0, result.stderr[-1000:]
        workflow = getattr(importlib.import_module("tests." + module_name), function_name)
        args = {"client": client, "app": app}
        await workflow(**{key: args[key] for key in inspect.signature(workflow).parameters})
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                expected = list(
                    await db.scalars(select(Outbox).where(Outbox.event_type.in_(AUDIT_EVENTS)))
                )
        assert expected
        user = os.environ["IDENTITY_TEST_BROKER_USER"]
        key = ServiceKey("accounting", "audit", AUDIT_EVENTS, secrets.token_bytes(32))
        async with confirmed_channel(broker_url) as channel:
            queue = await declare_consumer_queue(
                channel,
                exchange_name=name,
                queue_name=name,
                dead_letter_exchange=name + ".dlx",
                routes=tuple(sorted(AUDIT_EVENTS)),
                single_active_consumer=True,
            )
            exchange = await channel.get_exchange(name)
            try:
                publisher = ConfirmedPublisher(exchange, key_id="native", key=key, broker_user=user)
                count = 0
                while True:
                    sent = await publish_batch(
                        app.state.session_factory, publisher, event_types=AUDIT_EVENTS
                    )
                    count += sent.confirmed
                    if not sent.confirmed:
                        break
                assert count == len(expected)
                for _ in range(count):
                    message = await queue.get(timeout=5)
                    assert message is not None
                    await receive_audit(
                        factory,
                        message,
                        sources={"native": BrokerSource(key, user)},
                        consumer_name=name,
                    )
                with tenant_scope(TENANT):
                    async with factory() as db:
                        stored = list(await db.scalars(select(AuditEvent)))
                        assert {r.message_id for r in stored} == {r.message_id for r in expected}
                        assert await verify_tenant_chain(db, TENANT, page_size=7) == []
                        assert all(r.event_type == r.payload["action"] for r in expected)
                output = ROOT / ".test_artifacts/audit-financial"
                output.mkdir(parents=True, exist_ok=True)
                (output / (function_name + ".json")).write_text(
                    json.dumps(
                        {
                            "workflow": function_name,
                            "events": count,
                            "actions": sorted({r.event_type for r in expected}),
                            "chain_breaks": 0,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            finally:
                await queue.delete(if_unused=False, if_empty=False)
                dead = await channel.get_queue(name + ".dead")
                await dead.delete(if_unused=False, if_empty=False)
                dlx = await channel.get_exchange(name + ".dlx")
                await dlx.delete(if_unused=False)
                await exchange.delete(if_unused=False)
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f"DROP DATABASE `{schema}`"))
        await admin.dispose()

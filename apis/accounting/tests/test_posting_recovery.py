"""Outbox delivery and durable prepared-intent recovery."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.command_transaction import command_transaction
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from fastapi import FastAPI
from identity_posting import Receipt, ReservationError
from sqlalchemy import select

from accounting.api.auth import Access
from accounting.models.ledger import Journal
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.journal_posting import post
from accounting.tasks.posting_delivery import EVENT_TYPES, deliver
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import (
    Authority,
    create_journal,
    journal_setup,
    ledger_headers,
    post_journal,
)


class FailingTerminal(Authority):
    fail_terminal = True

    async def terminal(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        outcome: str,
        reference: str,
        posted_at: dt.datetime | None = None,
        intent: dict[str, Any] | None = None,
    ) -> Receipt:
        if self.fail_terminal:
            raise ReservationError("simulated terminal outage")
        return await super().terminal(
            tenant_id,
            company_id,
            operation_id=operation_id,
            outcome=outcome,
            reference=reference,
            posted_at=posted_at,
            intent=intent,
        )


async def test_outbox_confirmation_failure_is_retained_then_retried(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    authority = FailingTerminal()
    app.state.posting_client = authority
    row = await create_journal(client, body)
    assert (await post_journal(client, row)).status_code == 200
    first = await deliver(app.state.session_factory, app.state.posting_client)
    assert first.deferred == 1 and first.confirmed == 0
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            event = await db.scalar(select(Outbox).where(Outbox.event_type.in_(EVENT_TYPES)))
            assert (
                event is not None
                and event.last_error == "ReservationError"
                and event.published_at is None
            )
            event.available_at = utcnow() - dt.timedelta(seconds=1)
    authority.fail_terminal = False
    second = await deliver(app.state.session_factory, app.state.posting_client)
    assert second.confirmed == 1 and second.deferred == 0
    assert authority.receipts[uuid.UUID(row["id"])].status == "confirmed"
    assert (await deliver(app.state.session_factory, app.state.posting_client)).confirmed == 0


async def test_voided_prepared_intent_is_aborted_even_before_remote_reservation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, authority = await journal_setup(client, app)
    row = await create_journal(client, body)
    authority.fail = True
    assert (await post_journal(client, row)).status_code == 503
    current = (await client.get(BASE + f"/journals/{row['id']}", headers=ledger_headers())).json()
    canceled = await client.post(
        BASE + f"/journals/{row['id']}/void",
        json={"expected_version": current["row_version"], "reason": "Discard failed operation"},
        headers=ledger_headers(),
    )
    assert canceled.status_code == 200, canceled.text
    authority.fail = False
    result = await deliver(app.state.session_factory, app.state.posting_client)
    assert result.confirmed == 1 and authority.receipts[uuid.UUID(row["id"])].status == "aborted"
    assert (await post_journal(client, row)).status_code == 409


async def test_post_cannot_join_a_transaction_before_calling_identity(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    _, _, authority = await journal_setup(client, app)
    h = ledger_headers()
    actor = decode_actor_context(h["X-Actor-Context"], h["X-Actor-Signature"], SECRET.encode())
    context = verify_company_context(
        h["X-Company-Context"], h["X-Company-Signature"], SECRET.encode()
    )
    current = Access(actor, context)
    async with command_transaction(
        app.state.session_factory, tenant_id=TENANT, company_id=COMPANY, actor_id=actor.user_id
    ):
        with pytest.raises(ConflictError, match="independent"):
            await post(
                app.state.session_factory,
                current,
                uuid7(),
                ExpectedVersion(expected_version=1),
                str(uuid.uuid4()),
                app.state.posting_client,
            )
    assert authority.calls == 0


async def test_prepared_actor_and_receipt_identity_are_rechecked(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, authority = await journal_setup(client, app)
    row = await create_journal(client, body)
    authority.fail = True
    assert (await post_journal(client, row)).status_code == 503
    assert (await post_journal(client, row, user=uuid7())).status_code == 409
    authority.fail = False
    authority.receipts[uuid.UUID(row["id"])] = Receipt(
        operation_id=uuid7(),
        reservation_id=uuid7(),
        status="pending",
        configuration_hash="a" * 64,
        features=[],
        confirmed_at=None,
    )
    invalid = await post_journal(client, row)
    assert invalid.status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            stored = await db.get(Journal, uuid.UUID(row["id"]))
            assert stored is not None and stored.status == "PREPARED" and stored.number is None


async def test_journal_post_replay_uses_current_read_and_write_authority(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    row = await create_journal(client, body)
    key = str(uuid.uuid4())
    assert (await post_journal(client, row, key=key)).status_code == 200
    policy = {
        "entity_type": "accounting.journal",
        "field_key": "number",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    replay = await post_journal(client, row, key=key, policies=[policy])
    assert replay.status_code == 200 and "number" not in replay.json()
    assert (
        await post_journal(client, row, key=key, permissions=frozenset({"ledger.read"}))
    ).status_code == 403

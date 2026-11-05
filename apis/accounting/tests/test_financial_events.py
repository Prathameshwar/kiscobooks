"""Financial source payloads are versioned, scoped and committed once."""

import secrets
from decimal import Decimal

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from accounting.events.financial_contract import EVENT_TYPES, JournalPosted, PeriodChanged
from accounting.tasks.financial_publisher import FinancialPublisherSettings, configuration
from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import create_journal, journal_setup, post_journal


async def test_financial_outbox_and_publisher_contract(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    row = await create_journal(client, body)
    assert (await post_journal(client, row)).status_code == 200
    assert (await post_journal(client, row)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.tenant_id == TENANT, Outbox.event_type.in_(EVENT_TYPES)
                    )
                )
            )
    posted = [
        JournalPosted.model_validate(row.payload)
        for row in events
        if row.event_type.endswith(".posted")
    ]
    assert len(posted) == 1 and posted[0].company_id == COMPANY
    assert sum(
        line.base_amount if line.side == "DEBIT" else -line.base_amount for line in posted[0].lines
    ) == Decimal(0)
    periods = [
        PeriodChanged.model_validate(row.payload)
        for row in events
        if row.event_type.endswith(".changed")
    ]
    assert len(periods) == 13 and sum(period.status == "OPEN" for period in periods) == 1
    config = configuration(
        FinancialPublisherSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            financial_broker_url=SecretStr("amqp://fixture.invalid"),
            financial_broker_user="accounting_financial",
            financial_event_secret=SecretStr(secrets.token_hex(32)),
        )
    )
    assert config.key.operations == EVENT_TYPES and config.key.audience == "financial-services"

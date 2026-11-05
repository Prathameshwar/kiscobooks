"""Persist old held evidence for compatibility tests; new HTTP creation always posts."""

import datetime as dt
import uuid

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.domain.master_opening import entry
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import Account
from accounting.schemas.master_opening import MasterOpeningInput
from tests.conftest import COMPANY, TENANT, USER
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import ledger_headers


async def legacy_held(client, app):
    created = await client.post(
        BASE + "/parties/create-with-details",
        json={
            "code": "LEGACY",
            "name": "Legacy supplier",
            "legal_name": "Legacy supplier",
            "country_code": "IN",
            "role": "SUPPLIER",
        },
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            account = await db.scalar(
                select(Account).where(Account.party_id == uuid.UUID(created.json()["id"]))
            )
            date = dt.date(2026, 4, 1)
            value = entry(
                MasterOpeningInput(amount="100", side="CREDIT", opening_date=date),
                account_id=account.id,
                role="SUPPLIER",
                party=True,
                currency="INR",
                base_currency="INR",
                opening_date=date,
            )
            db.add(
                MasterOpeningBalance(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    created_by=USER,
                    updated_by=USER,
                    row_version=1,
                    account_id=account.id,
                    source_key=value.source_key,
                    status="PENDING",
                    opening_date=date,
                    entry=value.model_dump(mode="json"),
                )
            )
            await db.commit()

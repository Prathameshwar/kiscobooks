"""Creation completes native money execution; retries never duplicate the opening."""

from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.models.ledger import Journal, JournalLine
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import Account, Party
from accounting.models.subledger import OpeningBatch, OpenItem
from tests.conftest import TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_master_opening_api import opening, party


@pytest.mark.parametrize(
    "role,side",
    [("SUPPLIER", "CREDIT"), ("SUPPLIER", "DEBIT"), ("CUSTOMER", "DEBIT"), ("CUSTOMER", "CREDIT")],
)
async def test_creation_posts_exact_balanced_opening_and_bills_once(client, app, role, side):
    _, _, authority = await journal_setup(client, app, zero_opening=False)
    headers = ledger_headers()
    body = party(role=role, opening=opening(amount="100.0001", side=side))
    for _ in range(2):
        result = await client.post(
            BASE + "/parties/create-with-details", json=body, headers=headers
        )
        assert result.status_code == 201, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journals = list(await db.scalars(select(Journal)))
            assert len(journals) == 1 and journals[0].status == "POSTED"
            assert journals[0].total_debit == Decimal("100.0001")
            lines = list(await db.scalars(select(JournalLine)))
            assert len(lines) == 2 and {line.side for line in lines} == {"DEBIT", "CREDIT"}
            assert all(line.base_amount == Decimal("100.0001") for line in lines)
            item = await db.scalar(select(OpenItem))
            assert item and item.amount == Decimal("100.0001")
            assert (await db.scalar(select(MasterOpeningBalance))).status == "POSTED"
            assert (await db.scalar(select(OpeningBatch))).status == "FINALIZED"
            assert authority.receipts[journals[0].id].status == "confirmed"
            delivery = await db.scalar(
                select(Outbox).where(
                    Outbox.aggregate_id == journals[0].id,
                    Outbox.event_type == "accounting.company_posting.confirm",
                )
            )
            assert delivery.published_at is not None


async def test_later_master_opening_posts_after_company_opening_finalization(client, app):
    await journal_setup(client, app)
    for code in ("FIRST", "SECOND"):
        result = await client.post(
            BASE + "/parties/create-with-details",
            json=party(code, opening=opening()),
            headers=ledger_headers(),
        )
        assert result.status_code == 201, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                len(list(await db.scalars(select(Journal).where(Journal.status == "POSTED")))) == 2
            )


async def test_creation_retry_continues_existing_posting_after_authority_outage(client, app):
    _, _, authority = await journal_setup(client, app, zero_opening=False)
    authority.fail = True
    headers = ledger_headers()
    body = party(opening=opening())
    first = await client.post(BASE + "/parties/create-with-details", json=body, headers=headers)
    assert first.status_code == 503, first.text
    authority.fail = False
    retry = await client.post(BASE + "/parties/create-with-details", json=body, headers=headers)
    assert retry.status_code == 201, retry.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journals = list(await db.scalars(select(Journal)))
            assert len(journals) == 1 and journals[0].status == "POSTED"


@pytest.mark.parametrize(
    "permission", ["ledger.post_journal", "period.post", "accounting.finance.manage"]
)
async def test_missing_posting_permission_creates_nothing(client, app, permission):
    await journal_setup(client, app, zero_opening=False)
    response = await client.post(
        BASE + "/parties/create-with-details",
        json=party(opening=opening()),
        headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {permission}),
    )
    assert response.status_code == 403, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(Party.id).where(Party.code == "OPEN-1")) is None
            assert await db.scalar(select(Journal.id)) is None


async def test_bank_account_profile_and_opening_complete_together(client, app):
    await journal_setup(client, app, zero_opening=False)
    bank = uuid7()
    headers = ledger_headers(bank_ids={bank})
    groups = (await client.get(BASE + "/account-groups?limit=100", headers=headers)).json()["items"]
    group = next(row for row in groups if row["code"] == "BANKS")
    response = await client.post(
        BASE + "/accounts",
        headers=headers,
        json={
            "code": "BANK-OPEN",
            "name": "Opening bank",
            "kind": "BANK",
            "group_id": group["id"],
            "bank_profile": {"company_bank_id": str(bank)},
            "opening": opening(side="DEBIT"),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ACTIVE" and response.json()["used_at"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(Journal))).status == "POSTED"


async def test_invalid_offset_rolls_back_creation(client, app):
    await journal_setup(client, app, zero_opening=False)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            offset = await db.scalar(
                select(Account).where(Account.code == "OPENING_BALANCE_OFFSET")
            )
            offset.status = "INACTIVE"
            await db.commit()
    response = await client.post(
        BASE + "/parties/create-with-details",
        json=party(opening=opening()),
        headers=ledger_headers(),
    )
    assert response.status_code == 409, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(Party.id).where(Party.code == "OPEN-1")) is None


async def test_posted_creation_cannot_be_included_again_in_worksheet(client, app):
    from tests.test_financial_opening_api import ROOT, body_for

    body = await body_for(client, app)
    response = await client.post(
        BASE + "/parties/create-with-details",
        json=party(opening=opening()),
        headers=ledger_headers(),
    )
    assert response.status_code == 201, response.text
    held = (
        await client.get(BASE + "/opening-batches/master-balances", headers=ledger_headers())
    ).json()["items"][0]
    body["entries"] = [
        body["entries"][0] | {"amount": "100", "base_amount": "100"},
        held["entry"] | {"source_key": "attempt-another-source"},
    ]
    response = await client.post(ROOT + "/preview", json=body, headers=ledger_headers())
    assert response.status_code == 422, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            native = (await db.scalar(select(OpeningBatch))).payload
    legacy = await client.post(BASE + "/opening-batches", json=native, headers=ledger_headers())
    assert legacy.status_code == 422, legacy.text


async def test_confirmation_outage_returns_retry_then_completes_original_journal(client, app):
    from identity_posting import ReservationError

    from tests.test_ledger_api import Authority

    class DelayedConfirmation(Authority):
        unavailable = True

        async def terminal(self, *args, **kwargs):
            if self.unavailable:
                raise ReservationError("confirmation unavailable")
            return await super().terminal(*args, **kwargs)

    await journal_setup(client, app, zero_opening=False)
    authority = DelayedConfirmation()
    app.state.posting_client = authority
    headers = ledger_headers()
    body = party(opening=opening())
    response = await client.post(BASE + "/parties/create-with-details", json=body, headers=headers)
    assert response.status_code == 503, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(Journal))).status == "POSTED"
            assert (
                await db.scalar(
                    select(Outbox).where(Outbox.event_type == "accounting.company_posting.confirm")
                )
            ).published_at is None
    authority.unavailable = False
    response = await client.post(BASE + "/parties/create-with-details", json=body, headers=headers)
    assert response.status_code == 201, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert len(list(await db.scalars(select(Journal)))) == 1
            assert (
                await db.scalar(
                    select(Outbox).where(Outbox.event_type == "accounting.company_posting.confirm")
                )
            ).published_at is not None


async def test_native_reversal_updates_master_opening_evidence(client, app):
    from tests.test_ledger_api import post_journal

    await journal_setup(client, app, zero_opening=False)
    created = await client.post(
        BASE + "/parties/create-with-details",
        json=party(opening=opening()),
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            identity = (await db.scalar(select(Journal))).id
    reverse = await client.post(
        BASE + f"/journals/{identity}/reversal",
        json={"posting_date": "2026-04-01", "reason": "Correct opening"},
        headers=ledger_headers(),
    )
    assert reverse.status_code == 201, reverse.text
    posted = await post_journal(client, reverse.json())
    assert posted.status_code == 200, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(MasterOpeningBalance))).status == "REVERSED"

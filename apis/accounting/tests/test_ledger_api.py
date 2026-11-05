"""Journal persistence, posting boundaries, reversal and protected balance tests."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from identity_posting import Receipt, ReservationError
from sqlalchemy import func, select

from accounting.models.ledger import DocumentSequence, Journal, JournalLine
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import (
    BASE,
    FINANCE_PERMISSIONS,
    change,
    finance_headers,
    fiscal_setup,
)

LEDGER_PERMISSIONS = FINANCE_PERMISSIONS | {
    "ledger.read",
    "ledger.post_journal",
    "accounting.credit.read",
    "accounting.credit.manage",
    "accounting.credit.override_approve",
    "accounting.charges.read",
    "accounting.charges.manage",
    "accounting.charges.approve",
    "accounting.statement.read",
    "accounting.statement.import",
    "accounting.statement.review",
    "accounting.bank_match.manage",
    "accounting.bank_session.finalize",
}


def ledger_headers(**kwargs: Any) -> dict[str, str]:
    values: dict[str, Any] = {"permissions": LEDGER_PERMISSIONS} | kwargs
    return finance_headers(**values)


class Authority:
    """Service-boundary test double; persistence and transactions use the real database."""

    def __init__(self) -> None:
        self.receipts: dict[uuid.UUID, Receipt] = {}
        self.calls = 0
        self.fail = False

    async def reserve(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        configuration_hash: str,
        features: list[str],
    ) -> Receipt:
        self.calls += 1
        if self.fail:
            raise ReservationError("simulated authority outage")
        if operation_id not in self.receipts:
            self.receipts[operation_id] = Receipt(
                operation_id=operation_id,
                reservation_id=uuid7(),
                status="pending",
                configuration_hash=configuration_hash,
                features=features,
                confirmed_at=None,
            )
        return self.receipts[operation_id]

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
        if operation_id not in self.receipts and intent is not None:
            await self.reserve(
                tenant_id,
                company_id,
                operation_id=operation_id,
                actor_user_id=uuid.UUID(intent["actor_user_id"]),
                configuration_hash=intent["configuration_hash"],
                features=intent["features"],
            )
        row = self.receipts[operation_id].model_copy(
            update={"status": outcome, "confirmed_at": posted_at}
        )
        self.receipts[operation_id] = row
        return row


async def journal_setup(
    client: httpx.AsyncClient, app: FastAPI, *, zero_opening: bool = True
) -> tuple[dict[str, Any], dict[str, Any], Authority]:
    periods = await fiscal_setup(client)
    opened = await change(client, periods[0], "OPEN")
    assert opened.status_code == 200
    accounts = (await client.get(BASE + "/accounts?limit=200", headers=ledger_headers())).json()[
        "items"
    ]
    cash = next(row for row in accounts if row["kind"] == "CASH")
    general = next(row for row in accounts if row["kind"] == "GENERAL")
    body = {
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "description": "Initial cash movement",
        "lines": [
            {
                "account_id": cash["id"],
                "side": "DEBIT",
                "currency": "INR",
                "amount": "100.25",
                "exchange_rate": "1",
            },
            {
                "account_id": general["id"],
                "side": "CREDIT",
                "currency": "INR",
                "amount": "100.25",
                "exchange_rate": "1",
            },
        ],
    }
    if zero_opening:
        zero = await client.post(
            BASE + "/opening-batches",
            json={"posting_date": "2026-04-01", "description": "Zero initial balances"},
            headers=ledger_headers(),
        )
        assert zero.status_code == 201, zero.text
        finalized = await client.post(
            BASE + f"/opening-batches/{zero.json()['id']}/finalize-zero",
            json={"expected_version": zero.json()["row_version"]},
            headers=ledger_headers(),
        )
        assert finalized.status_code == 200, finalized.text
    authority = Authority()
    app.state.posting_client = authority
    return body, opened.json(), authority


async def create_journal(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    created = await client.post(BASE + "/journals", json=body, headers=ledger_headers())
    assert created.status_code == 201, created.text
    return cast(dict[str, Any], created.json())


async def post_journal(
    client: httpx.AsyncClient, row: dict[str, Any], **kwargs: Any
) -> httpx.Response:
    return await client.post(
        BASE + f"/journals/{row['id']}/post",
        json={"expected_version": row["row_version"]},
        headers=ledger_headers(**kwargs),
    )


async def test_journal_posts_once_then_reverses_without_changing_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, period, authority = await journal_setup(client, app)
    preview = await client.post(BASE + "/journals/preview", json=body, headers=ledger_headers())
    assert preview.status_code == 200 and Decimal(preview.json()["total_debit"]) == Decimal(
        "100.25"
    ), preview.text
    draft = await create_journal(client, body)
    assert draft["number"] is None and draft["status"] == "DRAFT"
    path = BASE + "/ledger/balance"
    query = {"as_of": "2026-04-02", "currency": "INR", "account_id": body["lines"][0]["account_id"]}
    before = await client.get(path, params=query, headers=ledger_headers())
    assert before.status_code == 200 and Decimal(before.json()["balance"]) == 0, before.text
    key = str(uuid.uuid4())
    posted = await post_journal(client, draft, key=key)
    assert posted.status_code == 200 and posted.json()["number"].endswith("/000001"), posted.text
    assert posted.json()["status"] == "POSTED"
    replay = await post_journal(client, draft, key=key)
    assert (
        replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    assert authority.calls == 1
    again = await post_journal(client, draft)
    assert again.status_code == 200 and again.json()["number"] == posted.json()["number"]
    current = await client.get(path, params=query, headers=ledger_headers())
    assert current.status_code == 200 and Decimal(current.json()["balance"]) == Decimal(
        "100.25"
    ), current.text
    old = await client.get(path, params=query | {"as_of": "2026-04-01"}, headers=ledger_headers())
    assert Decimal(old.json()["balance"]) == 0
    reversal = await client.post(
        BASE + f"/journals/{draft['id']}/reversal",
        json={"posting_date": "2026-04-03", "reason": "Correct mistaken journal"},
        headers=ledger_headers(),
    )
    assert reversal.status_code == 201, reversal.text
    reversed_post = await post_journal(client, reversal.json())
    assert reversed_post.status_code == 200, reversed_post.text
    after = await client.get(path, params=query | {"as_of": "2026-04-03"}, headers=ledger_headers())
    assert after.status_code == 200 and Decimal(after.json()["balance"]) == 0, after.text
    assert Decimal(
        (await client.get(path, params=query, headers=ledger_headers())).json()["balance"]
    ) == Decimal("100.25")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 2
            )
            values = list(await db.scalars(select(JournalLine.amount)))
            assert len(values) == 4 and all(type(value) is Decimal for value in values)
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "accounting.company_posting.confirm")
                )
            )
            assert len(events) == 2
    edit = await client.put(
        BASE + f"/journals/{draft['id']}",
        json=body | {"expected_version": posted.json()["row_version"]},
        headers=ledger_headers(),
    )
    assert edit.status_code == 409
    duplicate = await client.post(
        BASE + f"/journals/{draft['id']}/reversal",
        json={"posting_date": "2026-04-03", "reason": "Duplicate correction"},
        headers=ledger_headers(),
    )
    assert duplicate.status_code == 409
    history = await client.get(BASE + f"/history/journals/{draft['id']}", headers=ledger_headers())
    assert history.status_code == 200 and {row["action"] for row in history.json()["items"]} == {
        "create",
        "prepare",
        "post",
    }


async def test_new_year_posts_without_annual_opening_or_closing_prior_year(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    first = await post_journal(client, await create_journal(client, body))
    assert first.status_code == 200, first.text

    year = await client.post(
        BASE + "/fiscal-years/generate",
        json={"start_year": 2027},
        headers=ledger_headers(),
    )
    assert year.status_code == 200, year.text
    periods = await client.get(
        BASE + "/fiscal-periods",
        params={"fiscal_year_id": year.json()["id"]},
        headers=ledger_headers(),
    )
    assert periods.status_code == 200, periods.text
    next_period = min(periods.json()["items"], key=lambda row: row["start_date"])
    assert (await change(client, next_period, "OPEN")).status_code == 200

    next_body = body | {
        "document_date": "2027-03-31",
        "posting_date": "2027-04-02",
        "description": "Next year, prior-year document",
    }
    later = await post_journal(client, await create_journal(client, next_body))
    assert later.status_code == 200, later.text
    assert first.json()["number"].endswith("FY2026-2027/000001")
    assert later.json()["number"].endswith("FY2027-2028/000001")
    assert first.json()["fiscal_period_id"] != later.json()["fiscal_period_id"]
    balance = BASE + "/ledger/balance"
    query = {"currency": "INR", "account_id": body["lines"][0]["account_id"]}
    old = await client.get(
        balance, params=query | {"as_of": "2027-03-31"}, headers=ledger_headers()
    )
    current = await client.get(
        balance, params=query | {"as_of": "2027-04-02"}, headers=ledger_headers()
    )
    assert old.status_code == current.status_code == 200
    assert Decimal(old.json()["balance"]) == Decimal("100.25")
    assert Decimal(current.json()["balance"]) == Decimal("200.50")


async def test_journal_outage_preserves_intent_and_retry(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, period, authority = await journal_setup(client, app)
    draft = await create_journal(client, body)
    key = str(uuid.uuid4())
    authority.fail = True
    result = await post_journal(client, draft, key=key)
    assert result.status_code == 503, result.text
    current = await client.get(BASE + f"/journals/{draft['id']}", headers=ledger_headers())
    assert current.json()["status"] == "PREPARED" and current.json()["number"] is None
    assert (await change(client, period, "SOFT_CLOSED")).status_code == 409
    authority.fail = False
    retried = await post_journal(client, draft, key=key)
    assert retried.status_code == 200 and retried.json()["number"].endswith("/000001"), retried.text


async def test_journal_validation_scope_and_period_guards(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, period, authority = await journal_setup(client, app)
    assert (await client.post(BASE + "/journals", json=body)).status_code == 401
    assert (
        await client.post(BASE + "/journals", json=body, headers=finance_headers())
    ).status_code == 403
    for value in (0.1, True, "0.00001", "NaN", "-1"):
        invalid = {**body, "lines": [dict(body["lines"][0], amount=value), body["lines"][1]]}
        assert (
            await client.post(BASE + "/journals", json=invalid, headers=ledger_headers())
        ).status_code == 422
    draft = await create_journal(client, body)
    assert (
        await post_journal(client, draft, user=uuid7(), permissions=frozenset({"ledger.read"}))
    ).status_code == 403
    other = uuid7()
    assert (
        await client.get(
            f"/v1/companies/{other}/journals/{draft['id']}", headers=ledger_headers(company=other)
        )
    ).status_code == 403
    assert (
        await client.get(BASE + f"/journals/{draft['id']}", headers=ledger_headers(tenant=uuid7()))
    ).status_code == 404
    app.state.posting_client = None
    assert (await post_journal(client, draft)).status_code == 503
    app.state.posting_client = authority
    voided = await client.post(
        BASE + f"/journals/{draft['id']}/void",
        json={"expected_version": draft["row_version"], "reason": "Unused draft"},
        headers=ledger_headers(),
    )
    assert voided.status_code == 200 and voided.json()["status"] == "VOID"
    soft_closed_res = await change(client, period, "SOFT_CLOSED")
    assert soft_closed_res.status_code == 200
    period = soft_closed_res.json()
    second = await create_journal(client, body)
    permitted = LEDGER_PERMISSIONS - {"period.post_adjustment"}
    assert (await post_journal(client, second, permissions=permitted)).status_code == 403

    # Void second so that the period has no draft journals and can be CLOSED
    await client.post(
        BASE + f"/journals/{second['id']}/void",
        json={"expected_version": second["row_version"], "reason": "Unused second"},
        headers=ledger_headers(),
    )

    # Assert that draft creation on a LOCKED or CLOSED period is blocked
    closed_res = await change(client, period, "CLOSED")
    assert closed_res.status_code == 200, closed_res.text
    third = await client.post(BASE + "/journals", json=body, headers=ledger_headers())
    assert third.status_code == 409


async def test_financial_write_denial_rolls_back_posted_effects_and_number(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, authority = await journal_setup(client, app)
    draft = await create_journal(client, body)
    policy = {
        "entity_type": "accounting.journal",
        "field_key": "number",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    denied = await post_journal(client, draft, policies=[policy])
    assert denied.status_code == 403, denied.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 0
            )
            assert await db.scalar(select(func.count(DocumentSequence.id))) == 0
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "accounting.company_posting.confirm"
                    )
                )
                == 0
            )
    result = await post_journal(client, draft)
    assert result.status_code == 200 and result.json()["number"].endswith("/000001"), result.text
    assert authority.calls == 2


async def test_balances_exports_and_lines_honor_financial_field_denies(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    draft = await create_journal(client, body)
    assert (await post_journal(client, draft)).status_code == 200
    policy = {
        "entity_type": "accounting.journal_line",
        "field_key": "amount",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    for path in ("/journal-lines", "/exports/journal-lines"):
        result = await client.get(BASE + path, headers=ledger_headers(policies=[policy]))
        assert result.status_code == 200 and all(
            "amount" not in line for line in result.json()["items"]
        ), result.text
    total = await client.get(
        BASE + "/ledger/balance?as_of=2026-04-02&currency=INR",
        headers=ledger_headers(policies=[policy]),
    )
    assert total.status_code == 403
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            for model in (Journal, JournalLine, DocumentSequence):
                assert not list(await db.scalars(select(model)))


async def test_posting_numbers_cannot_be_allocated_outside_posting(client, app):
    await fiscal_setup(client)
    response = await client.post(
        BASE + "/document-sequences/allocate",
        json={"fiscal_year_id": str(uuid7()), "series_key": "TAX_INV"},
        headers=ledger_headers(),
    )
    assert response.status_code == 404
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert not list(await db.scalars(select(DocumentSequence)))

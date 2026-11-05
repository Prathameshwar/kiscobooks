"""Reviewed FX quotes are scoped, exact, and never silently substituted."""

from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from sqlalchemy import select

from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import finance_headers
from tests.test_ledger_api import journal_setup, ledger_headers, post_journal
from tests.test_masters import activate, post, prepare


async def test_rate_book_requires_allowance_checker_and_exact_date(client) -> None:
    await prepare(client)
    maker, checker = uuid7(), uuid7()
    root = f"/v1/companies/{COMPANY}/exchange-rates"

    def headers(user=maker, *, allowed=True):
        return finance_headers(
            user=user,
            features={"multi_currency"},
            allowed_currencies={"USD"} if allowed else set(),
        )

    body = {
        "from_currency": "USD",
        "to_currency": "INR",
        "purpose": "ACCOUNTING",
        "effective_date": "2026-05-01",
        "rate": "83.125000000000",
        "source_kind": "MANUAL",
        "source_reference": "Reviewed bank quote 2026-05-01",
    }
    assert (
        await client.post(root + "/candidates", json=body, headers=headers(allowed=False))
    ).status_code == 409
    created = await client.post(root + "/candidates", json=body, headers=headers())
    assert created.status_code == 201, created.text
    quote_id = created.json()["id"]
    decision = {"expected_version": 1, "reason": "Verified source quotation"}
    assert (
        await client.post(root + f"/{quote_id}/approve", json=decision, headers=headers())
    ).status_code == 409
    approved = await client.post(
        root + f"/{quote_id}/approve", json=decision, headers=headers(checker)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    detail = await client.get(root + f"/quotes/{quote_id}", headers=headers())
    assert detail.status_code == 200 and detail.json()["approval_reason"] == decision["reason"]
    same_day = await client.post(root + "/candidates", json=body, headers=headers())
    assert same_day.status_code == 201, same_day.text
    duplicate = await client.post(
        root + f"/{same_day.json()['id']}/approve", json=decision, headers=headers(checker)
    )
    assert duplicate.status_code == 409, duplicate.text

    query = "from_currency=USD&purpose=ACCOUNTING&effective_date=2026-05-01"
    effective = await client.get(root + "/effective?" + query, headers=headers())
    assert effective.status_code == 200, effective.text
    assert effective.json()["id"] == quote_id
    missing = await client.get(
        root + "/effective?from_currency=USD&purpose=ACCOUNTING&effective_date=2026-05-02",
        headers=headers(),
    )
    assert missing.status_code == 404, missing.text
    conversion = await client.post(
        root + "/conversion-preview",
        json={
            "amount": "2.0000",
            "from_currency": "USD",
            "purpose": "ACCOUNTING",
            "effective_date": "2026-05-01",
        },
        headers=headers(),
    )
    assert conversion.status_code == 200, conversion.text
    assert conversion.json()["converted_amount"] == "166.2500"
    withdrawn = await client.post(
        root + f"/{quote_id}/withdraw",
        json={"expected_version": 2, "reason": "Superseded source"},
        headers=headers(checker),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert (await client.get(root + "/effective?" + query, headers=headers())).status_code == 404


async def test_csv_rate_import_is_atomic_and_requires_review(client) -> None:
    await prepare(client)
    root = f"/v1/companies/{COMPANY}/exchange-rates"
    headers = finance_headers(features={"multi_currency"})
    csv_text = (
        "from_currency,to_currency,purpose,effective_date,rate\n"
        "USD,INR,ACCOUNTING,2026-05-01,83.25\n"
    )
    result = await client.post(
        root + "/imports/csv",
        json={"csv_text": csv_text, "source_reference": "May treasury upload"},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    assert len(result.json()) == 1
    assert result.json()[0]["status"] == "CANDIDATE"
    listed = await client.get(root + "?status=CANDIDATE&limit=1", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [result.json()[0]["id"]]
    bad = await client.post(
        root + "/imports/csv",
        json={
            "csv_text": csv_text + "USD,INR,ACCOUNTING,2026-05-02,not-a-rate\n",
            "source_reference": "Bad upload",
        },
        headers=headers,
    )
    assert bad.status_code == 422, bad.text
    duplicate_header = await client.post(
        root + "/imports/csv",
        json={
            "csv_text": csv_text.replace("rate\n", "rate,rate\n"),
            "source_reference": "Ambiguous upload",
        },
        headers=headers,
    )
    assert duplicate_header.status_code == 422, duplicate_header.text


async def test_posted_foreign_journal_keeps_approved_quote_usage(client, app) -> None:
    body, _, _ = await journal_setup(client, app)
    root = f"/v1/companies/{COMPANY}"
    quoted = await client.post(
        root + "/exchange-rates/candidates",
        json={
            "from_currency": "USD",
            "to_currency": "INR",
            "purpose": "ACCOUNTING",
            "effective_date": "2026-04-02",
            "rate": "83",
            "source_kind": "MANUAL",
            "source_reference": "Reviewed spot quote",
        },
        headers=finance_headers(features={"multi_currency"}),
    )
    assert quoted.status_code == 201, quoted.text
    approved = await client.post(
        root + f"/exchange-rates/{quoted.json()['id']}/approve",
        json={"expected_version": 1, "reason": "Independent treasury review"},
        headers=finance_headers(user=uuid7(), features={"multi_currency"}),
    )
    assert approved.status_code == 200, approved.text
    general_id = body["lines"][1]["account_id"]
    general = await client.get(root + f"/accounts/{general_id}", headers=ledger_headers())
    assert general.status_code == 200, general.text
    h = ledger_headers(features={"multi_currency"})
    accounts = []
    for index in (1, 2):
        account = await post(
            client,
            "/accounts",
            {
                "code": f"USD_JOURNAL_{index}",
                "name": f"Foreign journal account {index}",
                "group_id": general.json()["group_id"],
                "kind": "GENERAL",
                "currency_mode": "FIXED",
                "currency": "USD",
            },
            h=ledger_headers(features={"multi_currency"}),
        )
        accounts.append(
            await activate(
                client, "/accounts", account, h=ledger_headers(features={"multi_currency"})
            )
        )
    foreign = body | {
        "lines": [
            {
                "account_id": account["id"],
                "side": "DEBIT" if index == 0 else "CREDIT",
                "currency": "USD",
                "amount": "1.0000",
                "exchange_rate": "83",
            }
            for index, account in enumerate(accounts)
        ]
    }
    wrong = await client.post(
        root + "/journals/preview",
        json=foreign | {"lines": [line | {"exchange_rate": "84"} for line in foreign["lines"]]},
        headers=h,
    )
    assert wrong.status_code == 409, wrong.text
    created = await client.post(
        root + "/journals", json=foreign, headers=ledger_headers(features={"multi_currency"})
    )
    assert created.status_code == 201, created.text
    posted = await post_journal(client, created.json(), features={"multi_currency"})
    assert posted.status_code == 200, posted.text
    lines = await client.get(root + "/journal-lines?journal_id=" + created.json()["id"], headers=h)
    assert lines.status_code == 200, lines.text
    assert len(lines.json()["items"]) == 2
    for line in lines.json()["items"]:
        usage = await client.get(root + f"/exchange-rates/usages/{line['id']}", headers=h)
        assert usage.status_code == 200, usage.text
        assert usage.json()["quote_id"] == quoted.json()["id"]
    retired = await client.post(
        root + f"/exchange-rates/{quoted.json()['id']}/withdraw",
        json={"expected_version": 2, "reason": "Later correction"},
        headers=finance_headers(user=uuid7(), features={"multi_currency"}),
    )
    assert retired.status_code == 200, retired.text
    replay = await post_journal(client, created.json(), features={"multi_currency"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == posted.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "accounting.exchange_rate_usage.create"
                    )
                )
            )
    assert len(events) == 2

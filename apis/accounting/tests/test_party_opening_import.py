"""Opening balances imported with ready customers and suppliers: held, never posted."""

import base64
import json
import uuid
from typing import Any, cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.import_contracts import CONTROLS
from billing_platform.import_files import document
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.ledger import Journal
from accounting.models.party_opening import PartyOpeningBalance
from tests.conftest import TENANT, headers
from tests.test_fiscal_api import BASE, facts, finance_headers, fiscal_setup
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_masters import prepare

HELD = BASE + "/opening-batches/party-balances"


def party_row(code: str, **opening: Any) -> dict[str, Any]:
    return {
        "code": code,
        "name": "Name " + code,
        "legal_name": "Legal " + code,
        "country_code": "IN",
    } | opening


def source(rows: list[tuple[str, dict[str, Any]]]) -> dict[str, str]:
    """One CSV row per (resource, payload); every row is its own aggregate."""
    lines = [
        [
            f"row-{index}",
            f"set-{index}",
            resource,
            "CREATE",
            "",
            "",
            "",
            "",
            "",
            "",
            json.dumps(data),
        ]
        for index, (resource, data) in enumerate(rows)
    ]
    raw = document("CSV", [("Records", [*CONTROLS, "_payload"], lines)])
    return {
        "filename": "parties.csv",
        "format": "CSV",
        "content_base64": base64.b64encode(raw).decode(),
    }


async def post(
    client: httpx.AsyncClient,
    path: str,
    body: dict[str, Any],
    h: dict[str, str],
    status: int,
    *,
    fresh: bool = True,
) -> dict[str, Any]:
    """Each request is its own command unless the caller replays one on purpose."""
    sent = h | {"Idempotency-Key": str(uuid.uuid4())} if fresh else h
    response = await client.post(BASE + path, json=body, headers=sent)
    assert response.status_code == status, response.text
    return cast(dict[str, Any], response.json())


async def stage(
    client: httpx.AsyncClient,
    rows: list[tuple[str, dict[str, Any]]],
    h: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A job has one template, so every row shares one resource."""
    h = h or finance_headers()
    (resource,) = {name for name, _ in rows}
    template = await post(
        client,
        "/import-templates",
        {
            "definition": "parties",
            "parameters": {"resource": resource, "role": resource.upper()},
        },
        h,
        201,
    )
    return await post(
        client, "/import-jobs", {"template_id": template["id"], "files": [source(rows)]}, h, 201
    )


async def validate(
    client: httpx.AsyncClient, job: dict[str, Any], h: dict[str, str] | None = None
) -> dict[str, Any]:
    return await post(
        client,
        f"/import-jobs/{job['id']}/validate",
        {"expected_version": job["row_version"]},
        h or finance_headers(),
        200,
    )


async def commit(
    client: httpx.AsyncClient, ready: dict[str, Any], job: dict[str, Any], h: dict[str, str]
) -> dict[str, Any]:
    body = {"expected_version": ready["row_version"], "review_digest": ready["review_digest"]}
    return await post(client, f"/import-jobs/{job['id']}/commit", body, h, 200, fresh=False)


async def report(client: httpx.AsyncClient, job: dict[str, Any], h: dict[str, str]) -> str:
    options = {"kind": "RESULT"}
    ticket = await post(client, f"/import-jobs/{job['id']}/download-ticket", options, h, 200)
    got = await client.post(
        f"{BASE}/import-jobs/{job['id']}/download",
        json=options | {"token": ticket["token"]},
        headers=h,
    )
    assert got.status_code == 200, got.text
    return got.text


async def imported(
    client: httpx.AsyncClient, rows: list[tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    h = finance_headers()
    job = await stage(client, rows, h)
    ready = await validate(client, job, h)
    assert ready["state"] == "READY", ready
    applied = await commit(client, ready, job, h)
    assert applied["state"] == "SUCCEEDED", applied
    return applied


async def held(client: httpx.AsyncClient, query: str = "") -> list[dict[str, Any]]:
    response = await client.get(HELD + query, headers=finance_headers())
    assert response.status_code == 200, response.text
    return cast(list[dict[str, Any]], response.json()["items"])


async def accounts(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Full detail of every party ledger account; the list projection is deliberately lean."""
    response = await client.get(BASE + "/accounts?kind=PARTY&limit=200", headers=finance_headers())
    assert response.status_code == 200, response.text
    details = []
    for item in response.json()["items"]:
        got = await client.get(f"{BASE}/accounts/{item['id']}", headers=finance_headers())
        assert got.status_code == 200, got.text
        details.append(got.json())
    return details


async def test_a_supplier_balance_creates_its_ledger_account_and_posts_nothing(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    row = party_row(
        "SUP1",
        opening_balance_type="TO_PAY",
        opening_amount="1250.50",
        opening_account_code="CR-SUP1",
    )
    h = finance_headers()
    job = await stage(client, [("supplier", row)], h)
    ready = await validate(client, job, h)
    assert ready["state"] == "READY", ready
    # A dry run leaves no party, no ledger account and no held line.
    assert await held(client) == [] and await accounts(client) == []
    applied = await commit(client, ready, job, h)
    assert applied["state"] == "SUCCEEDED" and applied["completed_count"] == 1
    replay = await commit(client, ready, job, h)
    assert replay["id"] == applied["id"]

    (account,) = await accounts(client)
    assert (account["code"], account["name"], account["status"]) == (
        "CR-SUP1",
        "Name SUP1",
        "ACTIVE",
    )
    assert (account["kind"], account["party_role"], account["currency_mode"]) == (
        "PARTY",
        "SUPPLIER",
        "BASE",
    )
    (line,) = await held(client)
    assert line["status"] == "PENDING" and line["included"] is False
    assert (line["role"], line["side"], line["currency"]) == ("SUPPLIER", "CREDIT", "INR")
    assert (line["amount"], line["base_amount"], line["exchange_rate"]) == (
        "1250.5000",
        "1250.5000",
        "1.00000000",
    )
    assert line["account_id"] == account["id"] and line["party_id"] == account["party_id"]
    assert (line["document_kind"], line["document_reference"]) == ("ON_ACCOUNT", "Opening balance")
    assert line["document_date"] is None and line["due_date"] is None
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert not await db.scalar(select(func.count(Journal.id)))
            events = await db.scalar(
                select(func.count(Outbox.id)).where(
                    Outbox.event_type == "accounting.party_opening_balance.create"
                )
            )
            assert events == 1


async def test_a_customer_bill_is_held_as_one_dated_invoice(client: httpx.AsyncClient) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [
            (
                "customer",
                party_row(
                    "CUS1",
                    opening_balance_type="TO_RECEIVE",
                    opening_amount="900",
                    opening_bill_reference="INV-2025-77",
                    opening_bill_date="2026-02-10",
                    opening_bill_due_date="2026-03-12",
                ),
            )
        ],
    )
    (line,) = await held(client)
    assert (line["role"], line["side"], line["document_kind"]) == ("CUSTOMER", "DEBIT", "INVOICE")
    assert line["document_reference"] == "INV-2025-77"
    assert (line["document_date"], line["due_date"]) == ("2026-02-10", "2026-03-12")
    (account,) = await accounts(client)
    assert account["code"] == "CUS1" and account["party_role"] == "CUSTOMER"


async def test_dr_and_cr_are_accepted_and_a_row_without_a_balance_still_gets_its_account(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [
            ("supplier", party_row("S-DR", opening_balance_type="DR", opening_amount="5")),
            ("supplier", party_row("S-NONE")),
        ],
    )
    await imported(
        client, [("customer", party_row("C-CR", opening_balance_type="CR", opening_amount="6"))]
    )
    lines = await held(client)
    sides = {line["role"]: line["side"] for line in lines}
    assert sides == {"SUPPLIER": "DEBIT", "CUSTOMER": "CREDIT"}
    assert len(lines) == 2  # the row without a balance holds nothing
    # Every party role has exactly one account (docs/party-ledger-mandatory-plan.md): the row
    # without opening columns gets the standard account too, just with nothing held against it.
    by_code = {row["code"]: row for row in await accounts(client)}
    assert set(by_code) == {"S-DR", "S-NONE", "C-CR"}
    assert {code: row["party_role"] for code, row in by_code.items()} == {
        "S-DR": "SUPPLIER",
        "S-NONE": "SUPPLIER",
        "C-CR": "CUSTOMER",
    }
    assert {row["status"] for row in by_code.values()} == {"ACTIVE"}
    assert {line["account_id"] for line in lines}.isdisjoint({by_code["S-NONE"]["id"]})
    parties = (await client.get(BASE + "/parties?limit=50", headers=finance_headers())).json()
    assert len(parties["items"]) == 3
    assert {row["party_id"] for row in by_code.values()} == {row["id"] for row in parties["items"]}


async def test_the_template_offers_the_opening_columns_only_for_ready_parties(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    h = finance_headers()
    columns = {
        "opening_balance_type",
        "opening_amount",
        "opening_currency",
        "opening_exchange_rate",
        "opening_base_amount",
        "opening_account_code",
        "opening_bill_reference",
        "opening_bill_date",
        "opening_bill_due_date",
    }
    for resource in ("supplier", "customer"):
        template = await post(
            client,
            "/import-templates",
            {
                "definition": "parties",
                "parameters": {"resource": resource, "role": resource.upper()},
            },
            h,
            201,
        )
        schema = template["snapshot"]["schemas"][resource + ":CREATE"]
        assert columns <= set(schema["properties"])
        assert "opening_amount" not in schema.get("required", [])
        assert "opening_amount" in template["snapshot"]["instructions"]
    plain = await post(
        client,
        "/import-templates",
        {"definition": "parties", "parameters": {"resource": "party"}},
        h,
        201,
    )
    # The plain party resource can no longer create (a party always arrives with its role and its
    # account, through the ready resources), so its template has no CREATE schema at all.
    schemas = plain["snapshot"]["schemas"]
    assert "party:CREATE" not in schemas
    assert not any(
        name.startswith("opening_") for schema in schemas.values() for name in schema["properties"]
    )


async def test_invalid_opening_columns_keep_the_whole_row_out(client: httpx.AsyncClient) -> None:
    await fiscal_setup(client)
    h = finance_headers()
    cases = {
        "opening_exchange_rate": party_row(
            "BAD1", opening_balance_type="DR", opening_amount="5", opening_exchange_rate="2"
        ),
        "opening_bill_date": party_row(
            "BAD2",
            opening_balance_type="DR",
            opening_amount="5",
            opening_bill_reference="B",
            opening_bill_date="2026-04-02",
            opening_bill_due_date="2026-04-30",
        ),
        "opening_balance_type": party_row("BAD3", opening_amount="5"),
        "opening_currency": party_row(
            "BAD4",
            opening_balance_type="DR",
            opening_amount="5",
            opening_currency="USD",
            opening_exchange_rate="83",
            opening_base_amount="415",
        ),
    }
    for field, row in cases.items():
        job = await stage(client, [("supplier", row)], h)
        result = await validate(client, job, h)
        assert result["state"] == "INVALID", (field, result)
        assert field in await report(client, job, h), field
    assert await held(client) == [] and await accounts(client) == []
    assert (await client.get(BASE + "/parties", headers=h)).json()["items"] == []


async def test_a_ledger_account_code_that_is_taken_rejects_the_party_too(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [("supplier", party_row("DUP", opening_balance_type="TO_PAY", opening_amount="1"))],
    )
    h = finance_headers()
    job = await stage(
        client,
        [
            (
                "supplier",
                party_row(
                    "OTHER",
                    opening_balance_type="TO_PAY",
                    opening_amount="1",
                    opening_account_code="DUP",
                ),
            )
        ],
        h,
    )
    result = await validate(client, job, h)
    assert result["state"] == "INVALID"
    assert "opening_account_code" in await report(client, job, h)
    codes = {
        row["code"] for row in (await client.get(BASE + "/parties", headers=h)).json()["items"]
    }
    assert codes == {"DUP"}


async def test_a_row_without_a_balance_is_refused_when_its_default_ledger_code_is_taken(
    client: httpx.AsyncClient,
) -> None:
    """The account is never optional, so a plain row's default code (its party code) can collide."""
    await fiscal_setup(client)
    await imported(
        client,
        [
            (
                "supplier",
                party_row(
                    "FIRST",
                    opening_balance_type="TO_PAY",
                    opening_amount="1",
                    opening_account_code="TAKEN",
                ),
            )
        ],
    )
    h = finance_headers()
    job = await stage(client, [("supplier", party_row("TAKEN"))], h)
    result = await validate(client, job, h)
    assert result["state"] == "INVALID"
    assert "ledger.code" in await report(client, job, h)
    codes = {
        row["code"] for row in (await client.get(BASE + "/parties", headers=h)).json()["items"]
    }
    assert codes == {"FIRST"}
    assert [row["code"] for row in await accounts(client)] == ["TAKEN"]


async def test_a_balance_needs_finance_authority_beyond_the_import_right(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    weak = headers(finance=facts())  # import and party rights, but no accounting.finance.manage
    row = party_row("WEAK", opening_balance_type="TO_PAY", opening_amount="5")
    job = await stage(client, [("supplier", row)], weak)
    result = await validate(client, job, weak)
    assert result["state"] == "INVALID"
    assert "permission_denied" in await report(client, job, weak)
    assert (await client.get(BASE + "/parties", headers=finance_headers())).json()["items"] == []
    # The same actor can still import the party when no balance is given.
    plain = await stage(client, [("supplier", party_row("PLAIN"))], weak)
    assert (await validate(client, plain, weak))["state"] == "READY"


async def test_a_finalized_opening_no_longer_takes_balances(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)  # finalizes a zero opening
    h = ledger_headers()
    job = await stage(
        client,
        [("supplier", party_row("LATE", opening_balance_type="TO_PAY", opening_amount="5"))],
        h,
    )
    result = await validate(client, job, h)
    assert result["state"] == "INVALID"
    assert "opening_amount" in await report(client, job, h)
    plain = await stage(client, [("supplier", party_row("LATE2"))], h)
    assert (await validate(client, plain, h))["state"] == "READY"


async def test_a_foreign_balance_needs_the_multicurrency_feature(client: httpx.AsyncClient) -> None:
    await fiscal_setup(client)
    row = party_row(
        "USD1",
        opening_balance_type="TO_PAY",
        opening_amount="10",
        opening_currency="USD",
        opening_exchange_rate="83.2",
        opening_base_amount="832",
    )
    h = finance_headers()
    job = await stage(client, [("supplier", row)], h)
    assert (await validate(client, job, h))["state"] == "INVALID"
    rich = finance_headers(features={"multi_currency"}, allowed_currencies={"USD"})
    job = await stage(client, [("supplier", row)], rich)
    ready = await validate(client, job, rich)
    assert ready["state"] == "READY", ready
    await commit(client, ready, job, rich)
    (line,) = await held(client)
    assert (line["currency"], line["exchange_rate"], line["base_amount"]) == (
        "USD",
        "83.20000000",
        "832.0000",
    )
    (account,) = await accounts(client)
    assert (account["currency_mode"], account["currency"]) == ("FIXED", "USD")


async def test_a_held_balance_drops_into_a_balanced_declaration_and_then_cannot_be_withdrawn(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    h = ledger_headers()
    row = party_row(
        "SUP9",
        opening_balance_type="TO_PAY",
        opening_amount="100.25",
        opening_bill_reference="BILL-9",
        opening_bill_date="2026-03-01",
        opening_bill_due_date="2026-03-20",
    )
    job = await stage(client, [("supplier", row)], h)
    ready = await validate(client, job, h)
    await commit(client, ready, job, h)
    (line,) = (await client.get(HELD, headers=h)).json()["items"]
    cash = next(value["account_id"] for value in body["lines"] if value["side"] == "DEBIT")
    declaration = {
        "posting_date": "2026-04-01",
        "currency": "INR",
        "covered_through": "2026-03-31",
        "source_system": "legacy",
        "source_id": "opening-1",
        "reason": "Reviewed migration",
        "entries": [
            {
                "source_key": line["source_key"],
                "account_id": line["account_id"],
                "side": line["side"],
                "currency": line["currency"],
                "amount": line["amount"],
                "exchange_rate": line["exchange_rate"],
                "documents": [
                    {
                        "reference": line["document_reference"],
                        "amount": line["amount"],
                        "document_kind": line["document_kind"],
                        "document_date": line["document_date"],
                        "due_date": line["due_date"],
                    }
                ],
            },
            {
                "source_key": "cash-side",
                "account_id": cash,
                "side": "DEBIT",
                "currency": "INR",
                "amount": line["amount"],
                "exchange_rate": "1",
            },
        ],
    }
    root = BASE + "/opening-batches/workspaces"
    preview = await client.post(root + "/preview", json=declaration, headers=h)
    assert preview.status_code == 200, preview.text
    saved = await client.post(root, json=declaration, headers=ledger_headers(key="w-1"))
    assert saved.status_code == 201, saved.text
    (after,) = (await client.get(HELD, headers=h)).json()["items"]
    assert after["included"] is True
    refused = await client.post(
        f"{HELD}/{line['id']}/withdraw",
        json={"expected_version": line["row_version"], "reason": "Not wanted"},
        headers=ledger_headers(key="w-2"),
    )
    assert refused.status_code == 409, refused.text
    # An unfinished declaration does not close the door: a later import still holds its balance.
    later = party_row("SUP10", opening_balance_type="TO_PAY", opening_amount="7")
    fresh = ledger_headers()
    job = await stage(client, [("supplier", later)], fresh)
    ready = await validate(client, job, fresh)
    assert ready["state"] == "READY", ready
    await commit(client, ready, job, fresh)
    rows = (await client.get(HELD, headers=h)).json()["items"]
    assert sorted(row["included"] for row in rows) == [False, True]


async def test_withdrawing_is_versioned_idempotent_audited_and_final(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [("supplier", party_row("W1", opening_balance_type="TO_PAY", opening_amount="5"))],
    )
    (line,) = await held(client)
    path = f"{HELD}/{line['id']}/withdraw"
    body = {"expected_version": line["row_version"], "reason": "Entered twice"}
    stale = await client.post(
        path, json=body | {"expected_version": 9}, headers=finance_headers(key="stale")
    )
    assert stale.status_code == 409, stale.text
    done = await client.post(path, json=body, headers=finance_headers(key="withdraw-1"))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "WITHDRAWN" and done.json()["row_version"] == 2
    replay = await client.post(path, json=body, headers=finance_headers(key="withdraw-1"))
    assert replay.status_code == 200 and replay.json() == done.json()
    again = await client.post(
        path,
        json=body | {"expected_version": 2},
        headers=finance_headers(key="withdraw-2"),
    )
    assert again.status_code == 409, again.text
    assert [row["status"] for row in await held(client, "?status=WITHDRAWN")] == ["WITHDRAWN"]
    assert await held(client, "?status=PENDING") == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = await db.scalar(
                select(func.count(Outbox.id)).where(
                    Outbox.event_type == "accounting.party_opening_balance.withdraw"
                )
            )
            assert events == 1


async def test_withdraw_input_and_authority_are_checked(client: httpx.AsyncClient) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [("supplier", party_row("W2", opening_balance_type="TO_PAY", opening_amount="5"))],
    )
    (line,) = await held(client)
    path = f"{HELD}/{line['id']}/withdraw"
    body = {"expected_version": 1, "reason": "Entered twice"}
    assert (await client.post(path, json=body)).status_code == 401
    weak = headers(finance=facts(), key="weak")
    assert (await client.post(path, json=body, headers=weak)).status_code == 403
    for bad in ({**body, "reason": "no"}, {**body, "reason": "a\tb c"}, {**body, "extra": 1}):
        invalid = await client.post(path, json=bad, headers=finance_headers(key="bad-" + str(bad)))
        assert invalid.status_code == 422, invalid.text
    missing = await client.post(
        f"{HELD}/{uuid7()}/withdraw", json=body, headers=finance_headers(key="missing")
    )
    assert missing.status_code in {403, 404}


async def test_held_balances_are_isolated_by_company_and_tenant(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [("supplier", party_row("ISO", opening_balance_type="TO_PAY", opening_amount="5"))],
    )
    (line,) = await held(client)
    other_company = uuid.uuid4()
    other = finance_headers(company=other_company)
    rows = await client.get(
        f"/v1/companies/{other_company}/opening-batches/party-balances", headers=other
    )
    assert rows.status_code in {200, 403} and (
        rows.status_code == 403 or rows.json()["items"] == []
    )
    cross = await client.post(
        f"/v1/companies/{other_company}/opening-batches/party-balances/{line['id']}/withdraw",
        json={"expected_version": 1, "reason": "Not mine"},
        headers=finance_headers(company=other_company, key="cross"),
    )
    assert cross.status_code in {403, 404}
    stranger = finance_headers(tenant=uuid.uuid4())
    leaked = await client.get(HELD, headers=stranger)
    assert leaked.status_code in {200, 401, 403}
    assert leaked.status_code != 200 or leaked.json()["items"] == []
    # The session filter, not the route, is what keeps another tenant out of the table.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert len((await db.scalars(select(PartyOpeningBalance))).all()) == 1
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            assert (await db.scalars(select(PartyOpeningBalance))).all() == []


async def test_held_balance_list_contract(client: httpx.AsyncClient) -> None:
    await fiscal_setup(client)
    assert (await client.get(HELD)).status_code == 401
    assert (
        await client.get(HELD, headers=headers(permissions=set(), finance=facts()))
    ).status_code == 403
    await imported(
        client,
        [
            ("supplier", party_row(f"P{index}", opening_balance_type="TO_PAY", opening_amount="1"))
            for index in range(3)
        ],
    )
    await imported(
        client,
        [("customer", party_row("PC", opening_balance_type="TO_RECEIVE", opening_amount="2"))],
    )
    first = await client.get(HELD + "?limit=3", headers=finance_headers())
    assert first.status_code == 200
    page = first.json()
    assert len(page["items"]) == 3 and page["page"]["has_more"] is True
    rest = await client.get(
        HELD + "?limit=3&cursor=" + page["page"]["next_cursor"], headers=finance_headers()
    )
    assert len(rest.json()["items"]) == 1
    assert {row["id"] for row in page["items"]}.isdisjoint(
        {row["id"] for row in rest.json()["items"]}
    )
    assert len(await held(client, "?role=CUSTOMER")) == 1
    for bad in ("?limit=201", "?q=abc", "?sort=amount", "?status=DONE", "?unknown=1"):
        assert (await client.get(HELD + bad, headers=finance_headers())).status_code == 422, bad


async def test_staged_rows_are_immutable_and_never_deleted(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    import pytest
    from billing_platform.errors import ConflictError

    await fiscal_setup(client)
    await imported(
        client,
        [("supplier", party_row("IMM", opening_balance_type="TO_PAY", opening_amount="5"))],
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(select(PartyOpeningBalance))
            assert row is not None
            row.amount = row.amount + 1
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()
        async with app.state.session_factory() as db:
            row = await db.scalar(select(PartyOpeningBalance))
            assert row is not None
            await db.delete(row)
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()
        async with app.state.session_factory() as db:
            row = await db.scalar(select(PartyOpeningBalance))
            assert row is not None
            row.status = "WITHDRAWN"
            await db.flush()
            await db.commit()
        async with app.state.session_factory() as db:
            row = await db.scalar(select(PartyOpeningBalance))
            assert row is not None
            row.status = "PENDING"
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()


async def test_a_row_without_a_balance_needs_no_financial_setup(client: httpx.AsyncClient) -> None:
    """Most ready rows carry no balance; they must not start needing a financial context."""
    await prepare(client)  # chart of accounts only: no financial setup, no finance context
    h = headers()
    job = await stage(client, [("supplier", party_row("NOCTX"))], h)
    ready = await validate(client, job, h)
    assert ready["state"] == "READY", ready
    assert (await commit(client, ready, job, h))["state"] == "SUCCEEDED"
    parties = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    assert [row["code"] for row in parties] == ["NOCTX"]
    # The party's account is never optional, and creating it needs no financial context either:
    # the standard account, held against nothing.
    accounts_ = await client.get(BASE + "/accounts?kind=PARTY", headers=headers())
    (account,) = accounts_.json()["items"]
    assert (account["code"], account["status"]) == ("NOCTX", "ACTIVE")
    assert account["party_id"] == parties[0]["id"]

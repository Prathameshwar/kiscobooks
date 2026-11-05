"""Opening balances from party imports: gating, authority, audit, rollback and round trips."""

import base64
import json
import uuid
from pathlib import Path
from typing import Any, cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.import_contracts import CONTROLS
from billing_platform.import_files import document
from fastapi import FastAPI
from sqlalchemy import func, select

from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import BASE, FINANCE_PERMISSIONS, finance_headers, fiscal_setup
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_party_opening_import import (
    HELD,
    accounts,
    commit,
    held,
    imported,
    party_row,
    post,
    report,
    source,
    stage,
    validate,
)

CREATE = "accounting.party_opening_balance.create"
WITHDRAW = "accounting.party_opening_balance.withdraw"
CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "audit-events.json"
READY_SUPPLIER = {
    "definition": "parties",
    "parameters": {"resource": "supplier", "role": "SUPPLIER"},
}


async def refused_without_account_rights(
    client: httpx.AsyncClient, rows: list[tuple[str, dict[str, Any]]]
) -> None:
    """A ready-party import needs account rights from the actor, before any job can exist.

    The ledger account is never optional, so the right is required for every ready row (a row
    with no balance too), and it is checked when the template and the job are made.
    """
    weak = finance_headers(permissions=FINANCE_PERMISSIONS - {"accounting.account.manage"})
    refused = await client.post(BASE + "/import-templates", json=READY_SUPPLIER, headers=weak)
    assert refused.status_code == 403, refused.text
    assert "accounting.account.manage" in refused.text
    # A template made by someone who may create accounts does not lend that right to the actor
    # who creates the job from it.
    template = await post(client, "/import-templates", READY_SUPPLIER, finance_headers(), 201)
    job = await client.post(
        BASE + "/import-jobs",
        json={"template_id": template["id"], "files": [source(rows)]},
        headers=weak,
    )
    assert job.status_code == 403, job.text
    assert "accounting.account.manage" in job.text


async def events(app: FastAPI, event: str) -> list[dict[str, Any]]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = await db.scalars(select(Outbox).where(Outbox.event_type == event))
            return [cast(dict[str, Any], row.payload) for row in rows]


def console_entry(line: dict[str, Any]) -> dict[str, Any]:
    """What the worksheet builds from a held line: base value explicit on entry and document."""
    dated = line["document_kind"] != "ON_ACCOUNT"
    return {
        "source_key": line["source_key"],
        "account_id": line["account_id"],
        "side": line["side"],
        "currency": line["currency"],
        "amount": line["amount"],
        "exchange_rate": line["exchange_rate"],
        "base_amount": line["base_amount"],
        "documents": [
            {
                "line_sequence": 1,
                "reference": line["document_reference"],
                "amount": line["amount"],
                "base_amount": line["base_amount"],
                "document_kind": line["document_kind"],
                **(
                    {"document_date": line["document_date"], "due_date": line["due_date"]}
                    if dated
                    else {}
                ),
            }
        ],
    }


def declaration(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "posting_date": "2026-04-01",
        "currency": "INR",
        "covered_through": "2026-03-31",
        "source_system": "legacy",
        "source_id": "opening-rules",
        "reason": "Reviewed migration",
        "entries": entries,
    }


def counter_entry(account_id: str, amount: str) -> dict[str, Any]:
    return {
        "source_key": "counter-side",
        "account_id": account_id,
        "side": "DEBIT",
        "currency": "INR",
        "amount": amount,
        "base_amount": amount,
        "exchange_rate": "1",
    }


async def test_audit_events_carry_references_amounts_and_the_withdrawal_reason(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    h = finance_headers()
    row = party_row("AUD1", opening_balance_type="TO_PAY", opening_amount="12.5")
    job = await stage(client, [("supplier", row)], h)
    ready = await validate(client, job, h)
    assert await events(app, CREATE) == []  # the dry run leaves no event behind
    await commit(client, ready, job, h)
    (created,) = await events(app, CREATE)
    assert created["category"] == "money" and created["reason"] is None
    assert set(created["changes"]) == {
        "status",
        "party_id",
        "role",
        "account_id",
        "side",
        "currency",
        "amount",
        "base_amount",
        "base_currency",
    }
    text = json.dumps(created)
    assert not any(secret in text for secret in ("Name AUD1", "Legal AUD1", "AUD1"))
    (line,) = await held(client)
    path = f"{HELD}/{line['id']}/withdraw"
    body = {"expected_version": line["row_version"], "reason": "  Entered twice  "}
    done = await client.post(path, json=body, headers=finance_headers(key="withdraw-audit"))
    assert done.status_code == 200, done.text
    (withdrawn,) = await events(app, WITHDRAW)
    assert withdrawn["reason"] == "Entered twice"
    assert withdrawn["changes"] == {"status": {"from": "PENDING", "to": "WITHDRAWN"}}
    assert withdrawn["actor_user_id"] and withdrawn["entity_id"] == line["id"]
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for event, payload in ((CREATE, created), (WITHDRAW, withdrawn)):
        assert set(payload["changes"]) <= set(contract[event]["safe_fields"]), event
        assert contract[event]["category"] == "money"


async def test_a_withdrawn_line_cannot_come_back_through_a_stale_worksheet(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    h = ledger_headers()
    await imported(
        client,
        [("supplier", party_row("STALE", opening_balance_type="TO_PAY", opening_amount="100.25"))],
    )
    (line,) = (await client.get(HELD, headers=h)).json()["items"]
    withdrawn = await client.post(
        f"{HELD}/{line['id']}/withdraw",
        json={"expected_version": line["row_version"], "reason": "Not wanted"},
        headers=ledger_headers(key="stale-withdraw"),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    cash = next(value["account_id"] for value in body["lines"] if value["side"] == "DEBIT")
    stale = declaration([console_entry(line), counter_entry(cash, line["amount"])])
    root = BASE + "/opening-batches/workspaces"
    for path, key in ((root + "/preview", None), (root, "stale-save")):
        rejected = await client.post(
            path, json=stale, headers=ledger_headers(**({"key": key} if key else {}))
        )
        assert rejected.status_code == 422, rejected.text
        assert "withdrawn" in rejected.text
    # The same worksheet without the withdrawn line still previews.
    general = next(value["account_id"] for value in body["lines"] if value["side"] == "CREDIT")
    clean = declaration(
        [
            {**counter_entry(cash, "5"), "source_key": "plain-1"},
            {**counter_entry(general, "5"), "source_key": "plain-2", "side": "CREDIT"},
        ]
    )
    assert (await client.post(root + "/preview", json=clean, headers=h)).status_code == 200


async def test_a_legacy_draft_opening_does_not_take_held_balances(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app, zero_opening=False)
    legacy = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero initial balances"},
        headers=ledger_headers(),
    )
    assert legacy.status_code == 201, legacy.text  # a DRAFT batch with no worksheet behind it
    h = ledger_headers()
    row = party_row("LEGACY", opening_balance_type="TO_PAY", opening_amount="5")
    job = await stage(client, [("supplier", row)], h)
    assert (await validate(client, job, h))["state"] == "INVALID"
    assert "opening_amount" in await report(client, job, h)
    assert await held(client) == [] and await accounts(client) == []


async def test_capture_field_policy_and_account_rights_each_gate_a_balance(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    row = party_row("GATE", opening_balance_type="TO_PAY", opening_amount="5")
    deny_amount = {
        "entity_type": "accounting.journal_line",
        "field_key": "amount",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    # The field policy is checked when the job validates, so the whole flow runs under it.
    gate = finance_headers(policies=[deny_amount])
    job = await stage(client, [("supplier", row)], gate)
    assert (await validate(client, job, gate))["state"] == "INVALID"
    assert "permission_denied" in await report(client, job, gate)
    # The ledger account is never optional, so the account right is no longer discovered when the
    # row validates: the template and the job are refused with 403 before any row is read.
    await refused_without_account_rights(client, [("supplier", row)])
    assert await held(client) == [] and await accounts(client) == []
    assert (await client.get(BASE + "/parties", headers=finance_headers())).json()["items"] == []


async def test_a_ready_row_without_a_balance_needs_account_rights_too(
    client: httpx.AsyncClient,
) -> None:
    """Account rights gate every ready row, because every ready row creates its account."""
    await fiscal_setup(client)
    await refused_without_account_rights(client, [("supplier", party_row("NOACC"))])
    assert await accounts(client) == []
    assert (await client.get(BASE + "/parties", headers=finance_headers())).json()["items"] == []


def one_set(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Rows that share a set commit or fail together."""
    lines = [
        [f"row-{i}", "one-set", "supplier", "CREATE", "", "", "", "", "", "", json.dumps(data)]
        for i, data in enumerate(rows)
    ]
    raw = document("CSV", [("Records", [*CONTROLS, "_payload"], lines)])
    return {
        "filename": "suppliers.csv",
        "format": "CSV",
        "content_base64": base64.b64encode(raw).decode(),
    }


async def test_a_later_row_failing_in_the_same_set_leaves_no_trace(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    h = finance_headers()
    template = await client.post(
        BASE + "/import-templates",
        json={"definition": "parties", "parameters": {"resource": "supplier", "role": "SUPPLIER"}},
        headers=h,
    )
    assert template.status_code == 201, template.text
    good = party_row("SET1", opening_balance_type="TO_PAY", opening_amount="9")
    bad = party_row(
        "SET2", opening_balance_type="TO_PAY", opening_amount="9", opening_currency="USD"
    )
    del bad["legal_name"]  # fails after the first row has already staged its balance
    created = await client.post(
        BASE + "/import-jobs",
        json={"template_id": template.json()["id"], "files": [one_set([good, bad])]},
        headers=finance_headers(),
    )
    assert created.status_code == 201, created.text
    result = await validate(client, created.json(), h)
    assert result["state"] == "INVALID"
    assert await held(client) == [] and await accounts(client) == []
    assert (await client.get(BASE + "/parties", headers=h)).json()["items"] == []
    assert await events(app, CREATE) == [] and await events(app, "accounting.party.create") == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            from accounting.models.party_opening import PartyOpeningBalance

            assert not await db.scalar(select(func.count(PartyOpeningBalance.id)))


async def test_an_account_code_alone_is_reported_against_the_amount(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    h = finance_headers()
    job = await stage(client, [("supplier", party_row("CODEONLY", opening_account_code="X-1"))], h)
    assert (await validate(client, job, h))["state"] == "INVALID"
    assert "opening_amount" in await report(client, job, h)
    only_currency = party_row("CCYONLY", opening_currency="INR")
    job = await stage(client, [("supplier", only_currency)], h)
    assert (await validate(client, job, h))["state"] == "INVALID"
    assert "opening_amount" in await report(client, job, h)
    assert await accounts(client) == []


async def test_a_foreign_held_line_round_trips_through_preview_and_save(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    rich = {"features": {"multi_currency"}, "allowed_currencies": {"USD"}}
    h = ledger_headers(**rich)
    row = party_row(
        "FX1",
        opening_balance_type="TO_PAY",
        opening_amount="10",
        opening_currency="USD",
        opening_exchange_rate="83.2",
        opening_base_amount="832",
        opening_bill_reference="FX-BILL-1",
        opening_bill_date="2026-03-01",
        opening_bill_due_date="2026-03-30",
    )
    job = await stage(client, [("supplier", row)], h)
    ready = await validate(client, job, h)
    assert ready["state"] == "READY", ready
    await commit(client, ready, job, h)
    (line,) = (await client.get(HELD, headers=h)).json()["items"]
    assert (line["currency"], line["base_amount"], line["document_kind"]) == (
        "USD",
        "832.0000",
        "BILL",
    )
    cash = next(value["account_id"] for value in body["lines"] if value["side"] == "DEBIT")
    entries = [console_entry(line), counter_entry(cash, "832")]
    root = BASE + "/opening-batches/workspaces"
    preview = await client.post(root + "/preview", json=declaration(entries), headers=h)
    assert preview.status_code == 200, preview.text
    saved = await client.post(
        root, json=declaration(entries), headers=ledger_headers(key="fx-save", **rich)
    )
    assert saved.status_code == 201, saved.text
    (after,) = (await client.get(HELD, headers=h)).json()["items"]
    assert after["included"] is True


async def test_list_and_withdraw_failures_have_exact_statuses_and_bound_cursors(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    await imported(
        client,
        [
            ("supplier", party_row(f"CUR{n}", opening_balance_type="TO_PAY", opening_amount="1"))
            for n in range(3)
        ],
    )
    other = uuid.uuid4()
    foreign = await client.get(
        f"/v1/companies/{other}/opening-batches/party-balances", headers=finance_headers()
    )
    # The signed company context belongs to another company, so the actor is not authenticated here.
    assert foreign.status_code == 401, foreign.text
    cross = await client.post(
        f"/v1/companies/{other}/opening-batches/party-balances/{uuid.uuid4()}/withdraw",
        json={"expected_version": 1, "reason": "Not mine"},
        headers=finance_headers(key="cross-company"),
    )
    assert cross.status_code == 401, cross.text
    missing = await client.post(
        f"{HELD}/{uuid.uuid4()}/withdraw",
        json={"expected_version": 1, "reason": "No such line"},
        headers=finance_headers(key="missing-line"),
    )
    assert missing.status_code == 404, missing.text
    first = (await client.get(HELD + "?limit=1", headers=finance_headers())).json()
    cursor = first["page"]["next_cursor"]
    assert cursor
    assert (
        await client.get(f"{HELD}?limit=1&cursor={cursor}", headers=finance_headers())
    ).status_code == 200
    tampered = cursor[:-2] + ("AA" if not cursor.endswith("AA") else "BB")
    for bad in (
        f"{HELD}?limit=1&cursor={tampered}",
        f"{HELD}?limit=1&role=SUPPLIER&cursor={cursor}",  # a cursor is bound to its own query
        f"{HELD}?limit=2&cursor={cursor}",
    ):
        rejected = await client.get(bad, headers=finance_headers())
        assert rejected.status_code == 422, (bad, rejected.text)

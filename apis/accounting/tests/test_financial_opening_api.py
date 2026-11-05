"""Native company opening declaration lifecycle and conservative access boundaries."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers

ROOT = BASE + "/opening-batches/workspaces"


async def body_for(client: httpx.AsyncClient, app: FastAPI) -> dict[str, Any]:
    native, _, _ = await journal_setup(client, app, zero_opening=False)
    return {
        "posting_date": "2026-04-01",
        "currency": "INR",
        "covered_through": "2026-03-31",
        "source_system": "legacy",
        "source_id": "opening-1",
        "reason": "Reviewed migration",
        "entries": [
            line | {"source_key": "entry-" + str(index)}
            for index, line in enumerate(native["lines"])
        ],
    }


async def test_workspace_retains_revision_and_only_prepares_native_drafts(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    preview = await client.post(ROOT + "/preview", json=body, headers=ledger_headers())
    assert preview.status_code == 200, preview.text
    result = await client.post(ROOT, json=body, headers=ledger_headers(key="opening-workspace"))
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved["status"] == "DRAFT" and saved["journal_ids"] == []
    replay = await client.post(ROOT, json=body, headers=ledger_headers(key="opening-workspace"))
    assert replay.json()["id"] == saved["id"]
    rows = await client.get(ROOT + f"/{saved['id']}/entries?limit=1", headers=ledger_headers())
    assert rows.status_code == 200 and len(rows.json()["items"]) == 1, rows.text
    assert "payload" not in rows.json()["items"][0]
    entry_id = rows.json()["items"][0]["id"]
    link_path = ROOT + f"/{saved['id']}/entries/{entry_id}/posting-link"
    lineage = await client.get(link_path, headers=ledger_headers())
    assert (
        lineage.status_code == 200 and lineage.json()["journal_status"] == "NOT_PREPARED"
    ), lineage.text
    assert lineage.json()["source_key"] == rows.json()["items"][0]["source_key"]
    action = {
        "expected_version": saved["expected_version"],
        "manifest_hash": saved["manifest_hash"],
        "reason": "Prepare reviewed opening",
    }
    prepared = await client.post(
        ROOT + f"/{saved['id']}/prepare-drafts", json=action, headers=ledger_headers()
    )
    assert prepared.status_code == 200, prepared.text
    assert len(prepared.json()["journal_ids"]) == 1 and prepared.json()["posted_journals"] == 0
    lineage = await client.get(link_path, headers=ledger_headers())
    assert (
        lineage.status_code == 200
        and lineage.json()["journal_id"] == prepared.json()["journal_ids"][0]
    ), lineage.text
    action["expected_version"] = prepared.json()["expected_version"]
    rejected = await client.post(
        ROOT + f"/{saved['id']}/finalize", json=action, headers=ledger_headers()
    )
    assert rejected.status_code == 409, rejected.text


async def test_legacy_zero_cannot_finalize_a_nonzero_workspace(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    result = await client.post(ROOT, json=await body_for(client, app), headers=ledger_headers())
    assert result.status_code == 201, result.text
    saved = result.json()
    rejected = await client.post(
        BASE + f"/opening-batches/{saved['id']}/finalize-zero",
        json={"expected_version": saved["expected_version"]},
        headers=ledger_headers(),
    )
    assert rejected.status_code == 409, rejected.text


async def test_stale_revision_and_undeclared_reference_are_rejected(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    result = await client.post(ROOT, json=body, headers=ledger_headers())
    assert result.status_code == 201, result.text
    saved = result.json()
    request = {
        "expected_version": saved["expected_version"] - 1,
        "manifest_hash": saved["manifest_hash"],
        "reason": "Replace stale version",
        "declaration": body,
    }
    rejected = await client.post(
        ROOT + f"/{saved['id']}/replace", json=request, headers=ledger_headers()
    )
    assert rejected.status_code == 409, rejected.text
    invalid = await client.get(ROOT + f"/{saved['id']}/entries?limit=201", headers=ledger_headers())
    assert invalid.status_code == 422


async def test_post_confirm_reconcile_finalize_and_trade(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from accounting.tasks.posting_delivery import deliver
    from tests.test_ledger_api import create_journal, post_journal
    from tests.test_openings_sources import party_accounts

    body = await body_for(client, app)
    _, customer, _ = await party_accounts(client)
    body["entries"][0]["account_id"] = customer["id"]
    body["entries"][0]["documents"] = [
        {
            "source_key": "bill-one",
            "document_kind": "INVOICE",
            "reference": "OLD-100",
            "amount": "100.25",
            "original_amount": "200",
            "base_amount": "100.25",
            "document_date": "2026-03-01",
            "due_date": "2026-03-20",
        }
    ]
    created = await client.post(ROOT, json=body, headers=ledger_headers())
    assert created.status_code == 201, created.text
    saved = created.json()

    def action(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Reviewed opening",
        }

    path = ROOT + "/" + saved["id"]
    prepared = await client.post(
        path + "/prepare-drafts", json=action(saved), headers=ledger_headers()
    )
    assert prepared.status_code == 200, prepared.text
    journal = await client.get(
        BASE + "/journals/" + prepared.json()["journal_ids"][0], headers=ledger_headers()
    )
    posted = await post_journal(client, journal.json())
    assert posted.status_code == 200, posted.text
    pending = await client.get(path + "/reconciliation", headers=ledger_headers())
    assert pending.status_code == 200, pending.text
    assert pending.json()["gl_matches"] and pending.json()["party_items_match"]
    assert pending.json()["confirmation_pending"] and not pending.json()["ready_to_finalize"]
    saved = (await client.get(path, headers=ledger_headers())).json()
    blocked = await client.post(path + "/finalize", json=action(saved), headers=ledger_headers())
    assert blocked.status_code == 409, blocked.text
    outcome = await deliver(app.state.session_factory, app.state.posting_client)
    assert outcome.confirmed == 1
    ready = await client.get(path + "/reconciliation", headers=ledger_headers())
    assert ready.json()["ready_to_finalize"], ready.text
    finalized = await client.post(path + "/finalize", json=action(saved), headers=ledger_headers())
    assert (
        finalized.status_code == 200 and finalized.json()["status"] == "FINALIZED"
    ), finalized.text
    native = {
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "description": "After migrated opening",
        "lines": [
            {
                key: value
                for key, value in line.items()
                if key != "source_key" and key != "documents"
            }
            for line in body["entries"]
        ],
    }
    # The party balance must continue through its source workflow; ordinary journal
    # readiness can be verified using two non-party setup accounts.
    accounts = (await client.get(BASE + "/accounts?limit=200", headers=ledger_headers())).json()[
        "items"
    ]
    native["lines"][0]["account_id"] = next(row["id"] for row in accounts if row["kind"] == "CASH")
    trading = await post_journal(client, await create_journal(client, native))
    assert trading.status_code == 200, trading.text


async def test_import_review_commit_replay_cancel_and_private_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    path = BASE + "/financial-opening-imports"
    from tests.test_ledger_api import LEDGER_PERMISSIONS

    denied = await client.post(
        path,
        json={"source_key": "unauthorized-file", "format": "CSV", "content_base64": "not-base64"},
        headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"accounting.finance.manage"}),
    )
    assert denied.status_code == 403, denied.text
    request = {"source_key": "migration-file-one", "format": "JSON", "document": body}
    staged = await client.post(path, json=request, headers=ledger_headers())
    assert staged.status_code == 201, staged.text
    row = staged.json()
    assert row["state"] == "STAGED" and not row["journal_ids"]
    captured = await client.get(path + f"/{row['id']}/declaration", headers=ledger_headers())
    assert captured.status_code == 200, captured.text
    assert captured.json()["source_id"] == body["source_id"]
    assert [entry["source_key"] for entry in captured.json()["entries"]] == [
        entry["source_key"] for entry in body["entries"]
    ]
    assert "no-store" in captured.headers["cache-control"]
    from tests.test_field_policy import policy

    hidden_source = await client.get(
        path + f"/{row['id']}/declaration",
        headers=ledger_headers(
            policies=[policy("amount", access="read", entity="accounting.journal_line")]
        ),
    )
    assert hidden_source.status_code == 403, hidden_source.text
    from billing_platform.ids import uuid7

    foreign_company = uuid7()
    foreign_source = await client.get(
        path.replace(BASE, f"/v1/companies/{foreign_company}") + f"/{row['id']}/declaration",
        headers=ledger_headers(company=foreign_company),
    )
    assert foreign_source.status_code in {403, 404}, foreign_source.text
    reviewed = await client.post(
        path + f"/{row['id']}/validate",
        json={"expected_version": row["row_version"]},
        headers=ledger_headers(),
    )
    assert reviewed.status_code == 200 and reviewed.json()["state"] == "READY", reviewed.text
    row = reviewed.json()
    command = {"expected_version": row["row_version"], "review_hash": row["review_hash"]}
    h = ledger_headers()
    committed = await client.post(path + f"/{row['id']}/commit", json=command, headers=h)
    assert committed.status_code == 200, committed.text
    row = committed.json()
    assert row["drafts_complete"] and row["effect_kind"] == "DECLARATION_AND_DRAFTS_ONLY"
    replay = await client.post(path + f"/{row['id']}/commit", json=command, headers=h)
    assert replay.status_code == 200 and replay.json()["batch_id"] == row["batch_id"], replay.text
    history = await client.get(path + "?limit=1", headers=ledger_headers())
    assert history.status_code == 200 and "document" not in history.json()["items"][0], history.text
    ticket = await client.get(path + f"/{row['id']}/report-ticket", headers=ledger_headers())
    assert ticket.status_code == 200, ticket.text
    report = await client.get(ticket.json()["download_path"], headers=ledger_headers())
    assert report.status_code == 200 and "no-store" in report.headers["cache-control"], report.text
    cancelled = await client.post(
        path + f"/{row['id']}/cancel",
        json={"expected_version": row["row_version"]},
        headers=ledger_headers(),
    )
    assert (
        cancelled.status_code == 200 and cancelled.json()["batch_id"] == row["batch_id"]
    ), cancelled.text
    expired = await client.get(ticket.json()["download_path"], headers=ledger_headers())
    assert expired.status_code in {400, 422}, expired.text


async def test_revision_voids_only_unposted_drafts_and_retains_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    row = (await client.post(ROOT, json=body, headers=ledger_headers())).json()
    path = ROOT + "/" + row["id"]
    action = {
        "expected_version": row["expected_version"],
        "manifest_hash": row["manifest_hash"],
        "reason": "Review before replace",
    }
    prepared = await client.post(path + "/prepare-drafts", json=action, headers=ledger_headers())
    assert prepared.status_code == 200, prepared.text
    old_id = prepared.json()["journal_ids"][0]
    action["expected_version"] = prepared.json()["expected_version"]
    replaced = await client.post(
        path + "/replace",
        json=action | {"declaration": body | {"reason": "Corrected evidence"}},
        headers=ledger_headers(),
    )
    assert replaced.status_code == 200 and not replaced.json()["journal_ids"], replaced.text
    original = await client.get(BASE + "/journals/" + old_id, headers=ledger_headers())
    assert original.json()["status"] == "VOID", original.text
    revisions = await client.get(path + "/revisions", headers=ledger_headers())
    assert len(revisions.json()["items"]) == 2, revisions.text


async def test_capture_read_replay_export_scope_and_field_denials(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from billing_platform.ids import uuid7

    from tests.test_field_policy import policy
    from tests.test_ledger_api import LEDGER_PERMISSIONS

    body = await body_for(client, app)
    denied = await client.post(
        ROOT,
        json=body,
        headers=ledger_headers(
            policies=[policy("amount", access="write", entity="accounting.journal_line")]
        ),
    )
    assert denied.status_code == 403, denied.text
    h = ledger_headers()
    saved = await client.post(ROOT, json=body, headers=h)
    assert saved.status_code == 201, saved.text
    row = saved.json()
    path = ROOT + "/" + row["id"]
    hidden = ledger_headers(
        policies=[policy("base_amount", entity="accounting.journal_line")], key=h["Idempotency-Key"]
    )
    for suffix in ("", "/entries", "/declaration", "/reconciliation", "/export-ticket"):
        result = await client.get(path + suffix, headers=hidden)
        assert result.status_code == 403, (suffix, result.text)
    replay = await client.post(ROOT, json=body, headers=hidden)
    assert replay.status_code == 403, replay.text
    for entity, field in (
        ("account", "party_role"),
        ("journal_line", "description"),
        ("journal_line", "opening_base_amount"),
    ):
        forbidden = await client.get(
            path + "/declaration",
            headers=ledger_headers(policies=[policy(field, entity="accounting." + entity)]),
        )
        assert forbidden.status_code == 403, (entity, field, forbidden.text)
    wrong_company = uuid7()
    wrong = await client.get(
        path.replace(BASE, f"/v1/companies/{wrong_company}"),
        headers=ledger_headers(company=wrong_company),
    )
    assert wrong.status_code in {403, 404}, wrong.text
    ticket = await client.get(path + "/export-ticket", headers=ledger_headers())
    assert ticket.status_code == 200, ticket.text
    restricted = ledger_headers(permissions=LEDGER_PERMISSIONS - {"accounting.export.read"})
    download = await client.get(ticket.json()["download_path"], headers=restricted)
    assert download.status_code == 403, download.text
    alternate = await client.get(
        ticket.json()["download_path"], headers=ledger_headers(user=uuid7())
    )
    assert alternate.status_code in {400, 422}, alternate.text


async def test_foreign_bills_preserve_individual_historical_base_values(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from decimal import Decimal

    from billing_platform.db import tenant_scope
    from billing_platform.ids import uuid7
    from sqlalchemy import select

    from accounting.models.exchange_rates import ExchangeRateUsage
    from accounting.models.subledger import OpenItem
    from tests.conftest import TENANT
    from tests.test_ledger_api import post_journal
    from tests.test_openings_sources import party_accounts

    body = await body_for(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    body["entries"][0].update(
        account_id=customer["id"],
        currency="USD",
        amount="20",
        exchange_rate="90",
        base_amount="1700",
        documents=[
            {
                "source_key": "old-a",
                "document_kind": "INVOICE",
                "reference": "OLD-A",
                "amount": "10",
                "base_amount": "800",
                "document_date": "2025-11-01",
                "due_date": "2025-12-01",
            },
            {
                "source_key": "old-b",
                "document_kind": "INVOICE",
                "reference": "OLD-B",
                "amount": "10",
                "base_amount": "900",
                "document_date": "2026-03-01",
                "due_date": "2026-04-15",
            },
        ],
    )
    body["entries"][1]["amount"] = "1700"

    def h() -> dict[str, str]:
        return ledger_headers(features={"multi_currency"})

    rate_path = BASE + "/exchange-rates"
    quote = await client.post(
        rate_path + "/candidates",
        json={
            "from_currency": "USD",
            "to_currency": "INR",
            "purpose": "ACCOUNTING",
            "effective_date": "2026-04-01",
            "rate": "90",
            "source_kind": "MANUAL",
            "source_reference": "Current cutover quote, not original bill evidence",
        },
        headers=ledger_headers(features={"multi_currency"}, user=uuid7()),
    )
    assert quote.status_code == 201, quote.text
    approved = await client.post(
        rate_path + f"/{quote.json()['id']}/approve",
        json={
            "expected_version": quote.json()["row_version"],
            "reason": "Reviewed treasury quotation",
        },
        headers=ledger_headers(features={"multi_currency"}, user=uuid7()),
    )
    assert approved.status_code == 200, approved.text

    saved = await client.post(ROOT, json=body, headers=h())
    assert saved.status_code == 201, saved.text
    row = saved.json()
    prepared = await client.post(
        ROOT + f"/{row['id']}/prepare-drafts",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Reviewed carrying values",
        },
        headers=h(),
    )
    assert prepared.status_code == 200, prepared.text
    journal = (
        await client.get(BASE + "/journals/" + prepared.json()["journal_ids"][0], headers=h())
    ).json()
    posted = await post_journal(client, journal, features={"multi_currency"})
    assert posted.status_code == 200, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            items = list(await db.scalars(select(OpenItem).order_by(OpenItem.reference)))
            assert [item.base_amount for item in items] == [Decimal("800"), Decimal("900")]
            assert items[0].terms["source_key"] == "old-a"
            assert await db.scalar(select(ExchangeRateUsage.id)) is None
    result = await client.get(ROOT + f"/{row['id']}/reconciliation", headers=h())
    assert result.status_code == 200 and result.json()["party_items_match"], result.text


@pytest.mark.mysql
async def test_concurrent_company_openings_have_one_owner(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    import asyncio

    if app.state.engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("company serialization requires native MySQL row locks")
    body = await body_for(client, app)
    results = await asyncio.gather(
        *(client.post(ROOT, json=body, headers=ledger_headers()) for _ in range(2))
    )
    assert sorted(result.status_code for result in results) == [201, 409], [
        result.text for result in results
    ]


async def test_posted_correction_preserves_history_and_replacement_lineage(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from accounting.tasks.posting_delivery import deliver
    from tests.test_ledger_api import post_journal

    body = await body_for(client, app)
    row = (await client.post(ROOT, json=body, headers=ledger_headers())).json()
    path = ROOT + "/" + row["id"]
    prepared = await client.post(
        path + "/prepare-drafts",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Prepare cutover",
        },
        headers=ledger_headers(),
    )
    assert prepared.status_code == 200, prepared.text
    journal = (
        await client.get(
            BASE + "/journals/" + prepared.json()["journal_ids"][0], headers=ledger_headers()
        )
    ).json()
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    reversal = await client.post(
        BASE + f"/journals/{journal['id']}/reversal",
        json={"posting_date": "2026-04-01", "reason": "Correct source opening"},
        headers=ledger_headers(),
    )
    assert reversal.status_code == 201, reversal.text
    reversed_post = await post_journal(client, reversal.json())
    assert reversed_post.status_code == 200, reversed_post.text
    previous = await client.get(path, headers=ledger_headers())
    assert (
        previous.json()["status"] == "REVERSED" and previous.json()["posted_journals"] == 0
    ), previous.text
    replacement = await client.post(
        ROOT,
        json=body | {"replacement_of_id": row["id"], "source_id": "corrected-migration"},
        headers=ledger_headers(),
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["id"] != row["id"]
    await deliver(app.state.session_factory, app.state.posting_client)


async def test_reviewed_import_requires_revalidation_after_account_change(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body = await body_for(client, app)
    path = BASE + "/financial-opening-imports"
    staged = await client.post(
        path, json={"source_key": "review-drift", "document": body}, headers=ledger_headers()
    )
    assert staged.status_code == 201, staged.text
    job = staged.json()
    reviewed = await client.post(
        path + f"/{job['id']}/validate",
        json={"expected_version": job["row_version"]},
        headers=ledger_headers(),
    )
    assert reviewed.status_code == 200 and reviewed.json()["state"] == "READY", reviewed.text
    job = reviewed.json()
    account_path = BASE + "/accounts/" + body["entries"][0]["account_id"]
    account = (await client.get(account_path, headers=ledger_headers())).json()
    changed = await client.patch(
        account_path,
        json={"expected_version": account["row_version"], "name": account["name"] + " reviewed"},
        headers=ledger_headers(),
    )
    assert changed.status_code == 200, changed.text
    rejected = await client.post(
        path + f"/{job['id']}/commit",
        json={"expected_version": job["row_version"], "review_hash": job["review_hash"]},
        headers=ledger_headers(),
    )
    assert rejected.status_code == 409, rejected.text


async def test_customer_supplier_debts_advances_and_credits_stay_separate(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from billing_platform.db import tenant_scope
    from sqlalchemy import select

    from accounting.models.subledger import OpenItem
    from tests.conftest import TENANT
    from tests.test_ledger_api import post_journal
    from tests.test_openings_sources import party_accounts

    body = await body_for(client, app)
    _, customer, supplier = await party_accounts(client)
    body["entries"] = []
    for number, (account, side, kind, amount) in enumerate(
        [
            (customer, "DEBIT", "INVOICE", "100"),
            (supplier, "CREDIT", "BILL", "100"),
            (customer, "CREDIT", "ADVANCE", "25"),
            (supplier, "DEBIT", "ADVANCE", "25"),
            (customer, "CREDIT", "CREDIT_NOTE", "10"),
            (supplier, "DEBIT", "CREDIT_NOTE", "10"),
        ]
    ):
        body["entries"].append(
            {
                "source_key": f"entry-{number}",
                "account_id": account["id"],
                "side": side,
                "currency": "INR",
                "amount": amount,
                "exchange_rate": "1",
                "documents": [
                    {
                        "source_key": f"doc-{number}",
                        "document_kind": kind,
                        "reference": f"OLD-{number}",
                        "amount": amount,
                        "document_date": "2026-03-01",
                        "due_date": "2026-03-31",
                    }
                ],
            }
        )
    saved = await client.post(ROOT, json=body, headers=ledger_headers())
    assert saved.status_code == 201, saved.text
    row = saved.json()
    path = ROOT + "/" + row["id"]
    prepared = await client.post(
        path + "/prepare-drafts",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Review party directions",
        },
        headers=ledger_headers(),
    )
    assert prepared.status_code == 200, prepared.text
    journal = (
        await client.get(
            BASE + "/journals/" + prepared.json()["journal_ids"][0], headers=ledger_headers()
        )
    ).json()
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(OpenItem).order_by(OpenItem.reference)))
            assert [row.role for row in rows] == [
                "CUSTOMER",
                "SUPPLIER",
                "CUSTOMER",
                "SUPPLIER",
                "CUSTOMER",
                "SUPPLIER",
            ]
            assert [row.direction for row in rows] == [
                "DEBT",
                "DEBT",
                "CREDIT",
                "CREDIT",
                "CREDIT",
                "CREDIT",
            ]
    result = await client.get(path + "/reconciliation", headers=ledger_headers())
    assert result.status_code == 200 and result.json()["party_items_match"], result.text


async def test_capability_limits_are_explicit_and_credit_cash_requires_review(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from billing_platform.ids import uuid7

    body = await body_for(client, app)
    capability = await client.get(BASE + "/opening-batches/capabilities", headers=ledger_headers())
    assert capability.status_code == 200, capability.text
    assert (
        capability.json()["ytd_summary_supported"] is True
        and capability.json()["unknown_history_supported"] is True
    )
    for changes in ({"coverage_mode": "YTD_SUMMARY"}, {"clearing_account_id": str(uuid7())}):
        rejected = await client.post(
            ROOT + "/preview", json=body | changes, headers=ledger_headers()
        )
        assert rejected.status_code in {404, 422}, rejected.text
    body["entries"][0]["side"] = "CREDIT"
    body["entries"][1]["side"] = "DEBIT"
    rejected = await client.post(ROOT + "/preview", json=body, headers=ledger_headers())
    assert rejected.status_code == 422, rejected.text
    reviewed = await client.post(
        ROOT + "/preview",
        json=body
        | {"credit_cash_reviewed": True, "credit_cash_reason": "Reviewed migration exception"},
        headers=ledger_headers(),
    )
    assert reviewed.status_code == 200, reviewed.text

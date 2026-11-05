import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from reporting_contract.contract import FactPage
from test_foundation import generation

from reports.domain.reconcile import reconcile
from reports.domain.statements import CODES, calculate
from reports.models import core as m
from reports.schemas.requests import RunRequest
from reports.tasks import ingest, runs
from reports.tasks.common import company_lock, get


async def test_corrected_summary_has_new_rule_evidence_and_preserves_old_definition(
    app, client, prefix
):
    from reports.domain.statements import RULES

    old_hash = "a" * 64
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            old = m.ReportDefinition(
                tenant_id=TENANT,
                company_id=COMPANY,
                code="ACCOUNT_SUMMARY",
                version=1,
                rule_hash=old_hash,
            )
            db.add(old)
            await db.flush()
            old_id = old.id
        async with app.state.session_factory() as db, db.begin():
            current = await runs.definition(db, TENANT, COMPANY, "ACCOUNT_SUMMARY")
            assert current.version == 2
            assert current.id != old_id
            assert current.rule_hash == RULES["ACCOUNT_SUMMARY"]
            retained = await db.get(m.ReportDefinition, old_id)
            assert retained.rule_hash == old_hash
    definitions = await client.get(prefix + "/report-definitions", headers=headers())
    summary = next(row for row in definitions.json() if row["code"] == "ACCOUNT_SUMMARY")
    assert summary["version"] == 2


def bank_dataset():
    facts, ids = financial_dataset()
    facts = [
        source("account", row.source_id, row.data | {"kind": "BANK"})
        if row.entity == "account" and str(row.source_id) == ids["cash"]
        else row
        for row in facts
    ]
    journals = {str(row.source_id): row.data for row in facts if row.entity == "journal"}
    for row in list(facts):
        if row.entity != "journal_line" or row.data["account_id"] != ids["cash"]:
            continue
        date = journals[row.data["journal_id"]]["posting_date"]
        identity = uuid.uuid4()
        facts.append(
            source(
                "bank_instrument",
                identity,
                {
                    "intent_id": None,
                    "journal_line_id": str(row.source_id),
                    "account_id": ids["cash"],
                    "tender_key": str(uuid.uuid4()),
                    "mode": "BANK_TRANSFER",
                    "reference": "LEGACY-REF",
                    "instrument_date": None,
                    "booking_date": date,
                    "recognition": "BOOK_DATE",
                    "currency": "INR",
                    "amount": row.data["amount"],
                },
            )
        )
        facts.append(
            source(
                "bank_instrument_event",
                uuid.uuid4(),
                {
                    "instrument_id": str(identity),
                    "action": "BOOKED",
                    "event_date": date,
                    "reference": None,
                    "reason": "Recorded bank reference",
                },
            )
        )
        if journals[row.data["journal_id"]]["kind"] == "OPENING":
            facts.append(
                source(
                    "bank_instrument_event",
                    uuid.uuid4(),
                    {
                        "instrument_id": str(identity),
                        "action": "CLEARED",
                        "event_date": "2026-04-02",
                        "reference": "OPENING-STATEMENT",
                        "reason": "Opening already cleared",
                    },
                )
            )
    return sorted(facts, key=lambda row: (row.entity, str(row.source_id))), ids


def test_bank_reconciliation_carries_opening_and_outstanding_instruments_across_years():
    facts, ids = bank_dataset()
    reconcile(facts, financial_manifest(facts).control)
    query = RunRequest(
        code="BANK_RECONCILIATION",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2027, 4, 1),
        date_to=dt.date(2027, 4, 30),
        account_id=uuid.UUID(ids["cash"]),
        statement_balance="100",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[-1]["book_balance"] == "210.0000"
    assert rows[-1]["uncleared_signed"] == "110.0000"
    assert rows[-1]["reconciled"] and evidence["differences"] == []
    changed = query.model_copy(update={"statement_balance": "90"})
    _, evidence = calculate(facts, changed, dt.date(2026, 4, 1))
    assert evidence["differences"] == ["-10.0000"]
    missing = [row for row in facts if row.entity != "bank_instrument"]
    with pytest.raises(ConflictError, match="instrument evidence"):
        calculate(missing, query, dt.date(2026, 4, 1))


def test_evidence_report_rechecks_frozen_statement_and_book_totals():
    from decimal import Decimal

    from reports.domain.statements import Facts

    facts, ids = bank_dataset()
    lines = {str(row.source_id): row.data for row in facts if row.entity == "journal_line"}
    selected = next(
        row
        for row in facts
        if row.entity == "bank_instrument"
        and row.data["booking_date"] <= "2026-04-30"
        and lines[row.data["journal_line_id"]]["side"] == "DEBIT"
    )
    amount = selected.data["amount"]
    import_id, entry_id, match_id, session_id = [uuid.uuid4() for _ in range(4)]
    facts.extend(
        [
            source(
                "bank_statement_import",
                import_id,
                {
                    "account_id": ids["cash"],
                    "mapping_id": str(uuid.uuid4()),
                    "file_sha256": "a" * 64,
                    "currency": "INR",
                    "period_from": "2026-04-01",
                    "period_to": "2026-04-30",
                    "opening_balance": "0",
                    "closing_balance": amount,
                    "row_count": 1,
                    "status": "COMMITTED",
                },
            ),
            source(
                "bank_statement_entry",
                entry_id,
                {
                    "import_id": str(import_id),
                    "account_id": ids["cash"],
                    "line_number": 2,
                    "transaction_date": "2026-04-03",
                    "side": "CREDIT",
                    "amount": amount,
                    "currency": "INR",
                    "transaction_id": "TX-1",
                    "row_sha256": "b" * 64,
                    "review_status": "NEW",
                    "running_balance": amount,
                },
            ),
            source(
                "bank_match_event",
                match_id,
                {
                    "statement_entry_id": str(entry_id),
                    "instrument_id": str(selected.source_id),
                    "amount": amount,
                    "bank_date": "2026-04-03",
                    "group_id": str(uuid.uuid4()),
                    "reverses_id": None,
                },
            ),
        ]
    )
    query = RunRequest(
        code="BANK_RECONCILIATION_EVIDENCE",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2026, 4, 1),
        date_to=dt.date(2026, 4, 30),
        account_id=uuid.UUID(ids["cash"]),
        session_id=session_id,
        basis="TRANSACTION",
        currency="INR",
    )
    book = sum(
        (
            line["signed"]
            for line in Facts(facts).lines(query)
            if line["posting_date"] <= query.date_to
        ),
        Decimal(0),
    )
    instruments = [
        row
        for row in facts
        if row.entity == "bank_instrument" and row.data["booking_date"] <= "2026-04-30"
    ]
    snapshot = {
        "balance_agrees": True,
        "rows_covered": True,
        "statement_movement": f"{Decimal(amount):.4f}",
        "book_balance": f"{book:.4f}",
        "outstanding_book_amount": f"{book - Decimal(amount):.4f}",
        "source_sha256": "c" * 64,
        "entry_ids": [str(entry_id)],
        "instrument_ids": [str(row.source_id) for row in instruments],
        "import_ids": [str(import_id)],
    }
    facts.append(
        source(
            "bank_reconciliation_session",
            session_id,
            {
                "account_id": ids["cash"],
                "currency": "INR",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "generation": 1,
                "opening_balance": "0",
                "closing_balance": amount,
                "status": "FINALIZED",
                "snapshot": snapshot,
            },
        )
    )
    reconcile(facts, financial_manifest(facts).control)
    rows, _evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[-1]["row_kind"] == "BANK_SESSION_CONTROL"
    assert rows[-1]["closing_balance"] == amount
    corrupted = [row for row in facts if row.entity != "bank_match_event"]
    with pytest.raises(ConflictError, match="unmatched"):
        calculate(corrupted, query, dt.date(2026, 4, 1))


def test_bank_reconciliation_worklist_has_dated_book_residuals():
    facts, ids = bank_dataset()
    query = RunRequest(
        code="BANK_RECONCILIATION_WORKLIST",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2026, 4, 1),
        date_to=dt.date(2026, 4, 30),
        account_id=uuid.UUID(ids["cash"]),
        basis="TRANSACTION",
        currency="INR",
    )
    rows, _evidence = calculate(facts, query, dt.date(2026, 4, 1))
    book_rows = [row for row in rows if row["row_kind"] == "BOOK_ACTIVITY"]
    assert book_rows
    assert any(row["status"] == "BOOK_ONLY" for row in book_rows)
    assert all(row["age_days"] >= 0 for row in book_rows)


def test_reversed_bank_instrument_covers_original_and_reversal_without_replaying_cash():
    facts, ids = bank_dataset()
    original = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "expense"
    )
    reversal = uuid.uuid4()
    facts.append(
        source(
            "journal",
            reversal,
            original.data
            | {
                "kind": "REVERSAL",
                "number": "reverse-expense",
                "posting_date": "2026-04-05",
                "document_date": "2026-04-05",
                "reversal_of_id": str(original.source_id),
            },
        )
    )
    for row in list(facts):
        if row.entity == "journal_line" and row.data["journal_id"] == str(original.source_id):
            facts.append(
                source(
                    "journal_line",
                    uuid.uuid4(),
                    row.data
                    | {
                        "journal_id": str(reversal),
                        "side": "CREDIT" if row.data["side"] == "DEBIT" else "DEBIT",
                    },
                )
            )
            if row.data["account_id"] == ids["cash"]:
                instrument = next(
                    item
                    for item in facts
                    if item.entity == "bank_instrument"
                    and item.data["journal_line_id"] == str(row.source_id)
                )
                facts.append(
                    source(
                        "bank_instrument_event",
                        uuid.uuid4(),
                        {
                            "instrument_id": str(instrument.source_id),
                            "action": "REVERSED",
                            "event_date": "2026-04-05",
                            "reference": None,
                            "reason": "Correct erroneous expense",
                        },
                    )
                )
    query = RunRequest(
        code="BANK_RECONCILIATION",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2026, 4, 1),
        date_to=dt.date(2026, 4, 30),
        account_id=uuid.UUID(ids["cash"]),
        statement_balance="100",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[-1]["book_balance"] == "220.0000" and rows[-1]["uncleared_signed"] == "120.0000"
    assert evidence["differences"] == []
    assert any(row.get("state") == "REVERSED" for row in rows)


def test_receipt_register_splits_modes_without_multiplying_receipt_and_filters_party():
    facts, ids = bank_dataset()
    receipt = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "receipt"
    )
    line = next(
        row
        for row in facts
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(receipt.source_id)
        and row.data["account_id"] == ids["cash"]
    )
    instrument = next(
        row
        for row in facts
        if row.entity == "bank_instrument" and row.data["journal_line_id"] == str(line.source_id)
    )
    facts = [row for row in facts if row != instrument]
    facts.extend(
        [
            source(
                "bank_instrument",
                instrument.source_id,
                instrument.data | {"amount": "40", "mode": "NEFT"},
            ),
            source(
                "bank_instrument",
                uuid.uuid4(),
                instrument.data | {"amount": "80", "mode": "CHEQUE"},
            ),
        ]
    )
    party = next(row.source_id for row in facts if row.entity == "party")
    query = RunRequest(
        code="RECEIPT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2026, 4, 1),
        date_to=dt.date(2026, 4, 30),
        party_id=party,
        role="CUSTOMER",
    )
    rows, _ = calculate(facts, query, dt.date(2026, 4, 1))
    assert sorted(row["amount"] for row in rows) == ["40.0000", "80.0000"]
    assert {row["mode"] for row in rows} == {"NEFT", "CHEQUE"}
    # An older receipt without instrument capture is visible with an explicit missing mode.
    legacy, _ = calculate(
        [row for row in facts if row.entity != "bank_instrument"], query, dt.date(2026, 4, 1)
    )
    assert (
        len(legacy) == 1
        and legacy[0]["mode"] == "UNSPECIFIED"
        and legacy[0]["amount"] == "120.0000"
    )


def test_foreign_split_tenders_preserve_base_rounding_residual():
    from decimal import Decimal

    from reports.domain.registers import instrument_values

    line = {"amount": "3.0000", "base_amount": "250.0000"}
    tenders = [("a", {"amount": "1.0000"}), ("b", {"amount": "2.0000"})]
    assert [amount for _, _, amount in instrument_values(line, tenders, "BASE")] == [
        Decimal("83.3333"),
        Decimal("166.6667"),
    ]
    assert [amount for _, _, amount in instrument_values(line, tenders, "TRANSACTION")] == [
        Decimal(1),
        Decimal(2),
    ]
    with pytest.raises(ConflictError, match="exceed"):
        instrument_values(line, [("a", {"amount": "4"})], "BASE")


async def test_all_financial_runs_have_frozen_rows_and_signed_downloads(client, prefix, app):
    record = await generation(client, prefix)
    facts, ids = bank_dataset()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await company_lock(db, TENANT, COMPANY)
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            manifest = financial_manifest(facts, identity=row.snapshot_id)
            bundle = await ingest.bundle(db, row, manifest)
            await ingest.stage(db, bundle, FactPage(manifest_id=manifest.id, items=facts), 0)
            await db.flush()
            await ingest.apply(db, row, bundle)
            await db.flush()
            row.target_sequence = row.applied_sequence
            await ingest.activate(db, row)
    for code in CODES:
        if code in {"BANK_RECONCILIATION_EVIDENCE", "BANK_RECONCILIATION_WORKLIST"}:
            continue  # Requires a finalized Accounting session; covered by its dedicated fixture.
        request = {
            "generation_id": record["id"],
            "code": code,
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        }
        if code == "BANK_RECONCILIATION":
            request |= {"account_id": ids["cash"], "statement_balance": "100"}
        if code == "BALANCE_CONTINUITY":
            request |= {"date_from": "2027-04-01", "date_to": "2028-03-31"}
        key = headers()
        created = await client.post(prefix + "/report-runs", json=request, headers=key)
        assert created.status_code == 202, created.text
        identity = created.json()["id"]
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db, db.begin():
                await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(identity)))
        replay = await client.post(prefix + "/report-runs", json=request, headers=key)
        assert replay.json()["id"] == identity
        result = await client.get(prefix + "/report-runs/" + identity, headers=headers())
        assert result.status_code == 200 and result.json()["status"] == "COMPLETE"
        assert result.json()["evidence"]["report_code"] == code
        downloaded = await client.get(
            prefix + "/report-runs/" + identity + "/download",
            params={"token": result.json()["download_token"]},
            headers=headers(),
        )
        assert downloaded.status_code == 200
        assert (
            await client.get(
                prefix + "/report-runs/" + identity + "/rows?limit=200", headers=headers()
            )
        ).status_code == 200

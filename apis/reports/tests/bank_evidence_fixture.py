"""Balanced, minimal bank statement/session with complete source lineage."""

import datetime as dt
import uuid

from fixtures import source
from test_money_reports import bank_dataset

from reports.schemas.requests import RunRequest


def evidence_dataset():
    facts, ids = bank_dataset()
    instrument = next(
        row
        for row in facts
        if row.entity == "bank_instrument" and row.data["booking_date"] == "2026-04-01"
    )
    ids |= {name: str(uuid.uuid4()) for name in ("import", "entry", "match", "session")}
    facts.extend(
        [
            source(
                "bank_statement_import",
                uuid.UUID(ids["import"]),
                {
                    "account_id": ids["cash"],
                    "mapping_id": str(uuid.uuid4()),
                    "file_sha256": "a" * 64,
                    "currency": "INR",
                    "period_from": "2026-04-01",
                    "period_to": "2026-04-30",
                    "opening_balance": "0",
                    "closing_balance": "100",
                    "row_count": 1,
                    "status": "COMMITTED",
                },
            ),
            source(
                "bank_statement_entry",
                uuid.UUID(ids["entry"]),
                {
                    "import_id": ids["import"],
                    "account_id": ids["cash"],
                    "line_number": 2,
                    "transaction_date": "2026-04-03",
                    "side": "CREDIT",
                    "amount": "100",
                    "currency": "INR",
                    "transaction_id": "TX-1",
                    "row_sha256": "b" * 64,
                    "review_status": "NEW",
                    "running_balance": "100",
                },
            ),
            source(
                "bank_match_event",
                uuid.UUID(ids["match"]),
                {
                    "statement_entry_id": ids["entry"],
                    "instrument_id": str(instrument.source_id),
                    "amount": "100",
                    "bank_date": "2026-04-03",
                    "group_id": str(uuid.uuid4()),
                    "reverses_id": None,
                },
            ),
            source(
                "bank_reconciliation_session",
                uuid.UUID(ids["session"]),
                {
                    "account_id": ids["cash"],
                    "currency": "INR",
                    "period_from": "2026-04-01",
                    "period_to": "2026-04-30",
                    "generation": 1,
                    "opening_balance": "0",
                    "closing_balance": "100",
                    "status": "FINALIZED",
                    "snapshot": {
                        "balance_agrees": True,
                        "rows_covered": True,
                        "statement_movement": "100.0000",
                        "book_balance": "180.0000",
                        "outstanding_book_amount": "80.0000",
                        "source_sha256": "c" * 64,
                        "entry_ids": [ids["entry"]],
                        "instrument_ids": [
                            str(row.source_id)
                            for row in facts
                            if row.entity == "bank_instrument"
                            and row.data["booking_date"] <= "2026-04-30"
                        ],
                        "import_ids": [ids["import"]],
                    },
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
        session_id=uuid.UUID(ids["session"]),
        basis="TRANSACTION",
        currency="INR",
    )
    return facts, query, ids

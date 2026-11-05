"""Report scope diagnostics over disposable frozen fixture evidence."""

import datetime as dt
import uuid
from decimal import Decimal

from financial_fixture import financial_dataset
from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest

from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import page
from test_native_ledger import prepared


def test_filtered_ledger_preserves_full_balance_but_has_no_scope_annotation():
    facts, ids = financial_dataset()
    query = RunRequest(
        code="ACCOUNT_LEDGER",
        generation_id=uuid.uuid4(),
        account_id=ids["cash"],
        date_from=dt.date(2026, 4, 2),
        date_to=dt.date(2027, 4, 30),
    )
    full, _ = calculate(facts, query, dt.date(2026, 4, 1))
    full_entries = {row["line_id"]: row for row in full if row["row_kind"] == "ENTRY"}
    for identity in {row["journal_id"] for row in full_entries.values()}:
        selected, _ = calculate(
            facts,
            query.model_copy(update={"journal_id": uuid.UUID(identity)}),
            dt.date(2026, 4, 1),
        )
        opening = sum(
            (
                Decimal(row["balance"])
                for row in selected
                if row["row_kind"] == "OPENING"
            ),
            Decimal(0),
        )
        entries = [row for row in selected if row["row_kind"] == "ENTRY"]
        shown = opening + sum(
            (Decimal(row["debit"]) - Decimal(row["credit"]) for row in entries),
            Decimal(0),
        )
        if entries and shown != Decimal(entries[-1]["balance"]):
            assert all(
                row["balance"] == full_entries[row["line_id"]]["balance"]
                for row in entries
            )
            assert all("balance_scope" not in row for row in entries)
            return
    raise AssertionError(
        "Fixture must contain omitted movements before a selected journal"
    )


async def test_native_filtered_ledger_has_the_same_unlabelled_full_balance(app):
    identities, facts, ids = await prepared(app)
    query = RunRequest(
        code="ACCOUNT_LEDGER",
        generation_id=identities[2],
        account_id=ids["cash"],
        date_from=dt.date(2026, 4, 2),
        date_to=dt.date(2027, 4, 30),
    )
    full, _ = calculate(facts, query, dt.date(2026, 4, 1))
    full_entries = {row["line_id"]: row for row in full if row["row_kind"] == "ENTRY"}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for identity in {row["journal_id"] for row in full_entries.values()}:
                selected_query = query.model_copy(
                    update={"journal_id": uuid.UUID(identity)}
                )
                rows, cursor = await page(db, context, selected_query, 200)
                assert cursor is None
                assert rows == calculate(facts, selected_query, context.coverage)[0]
                entries = [row for row in rows if row["row_kind"] == "ENTRY"]
                opening = sum(
                    (
                        Decimal(row["balance"])
                        for row in rows
                        if row["row_kind"] == "OPENING"
                    ),
                    Decimal(0),
                )
                shown = opening + sum(
                    (Decimal(row["debit"]) - Decimal(row["credit"]) for row in entries),
                    Decimal(0),
                )
                if entries and shown != Decimal(entries[-1]["balance"]):
                    assert all(
                        row["balance"] == full_entries[row["line_id"]]["balance"]
                        for row in entries
                    )
                    assert all("balance_scope" not in row for row in entries)
                    return
    raise AssertionError(
        "Fixture must contain omitted movements before a selected journal"
    )

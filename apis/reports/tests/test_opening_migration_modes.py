"""Disclosed YTD aggregates and unknown-date ageing match frozen and native paths."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from sqlalchemy import select
from test_source_versions import staged

from reports.domain.statements import calculate
from reports.models.source_versions import ReportSourceCut
from reports.queries.native_context import NativeContext
from reports.queries.native_open_items import execute as item_execute
from reports.queries.native_statements import execute
from reports.schemas.requests import RunRequest
from reports.tasks.source_publication import publish


def ytd_dataset():
    facts, ids = financial_dataset()
    opening = next(
        row for row in facts if row.entity == "journal" and row.data["kind"] == "OPENING"
    )
    changed = []
    for row in facts:
        if row.entity == "opening_batch":
            continue
        data = row.data
        if row.entity == "financial_setup":
            data = data | {"books_begin_date": "2026-04-02"}
        if row.entity == "journal" and row.source_id == opening.source_id:
            data = data | {"document_date": "2026-04-02", "posting_date": "2026-04-02"}
        if (
            row.entity == "journal_line"
            and data["journal_id"] == str(opening.source_id)
            and data["side"] == "CREDIT"
        ):
            data = data | {"account_id": ids["income"]}
        changed.append(source(row.entity, row.source_id, data))
    changed.append(
        source(
            "opening_batch",
            uuid.uuid4(),
            {
                "status": "FINALIZED",
                "posting_date": "2026-04-02",
                "journal_id": str(opening.source_id),
                "replacement_of_id": None,
                "finalized_at": "2026-04-02T12:00:00Z",
                "journal_ids": [str(opening.source_id)],
                "coverage": {
                    "mode": "YTD_SUMMARY",
                    "posting_date": "2026-04-02",
                    "covered_through": "2026-04-01",
                    "originating_year_start": "2026-04-01",
                    "source_system": "legacy",
                    "source_id": "migration-ytd",
                    "manifest_hash": "b" * 64,
                    "ytd_summary": [
                        {
                            "account_id": ids["income"],
                            "side": "CREDIT",
                            "currency": "INR",
                            "amount": "100",
                            "base_amount": "100",
                        }
                    ],
                },
            },
        )
    )
    return changed, ids


def request(identity, code="PROFIT_LOSS", **changes):
    return RunRequest.model_validate(
        {
            "generation_id": str(identity),
            "code": code,
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        }
        | changes
    )


async def prepared(app, facts, coverage):
    control = financial_manifest(facts).control.model_copy(update={"coverage_start": coverage})
    identities, _ = await staged(app, source=facts, control=control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
            assert cut is not None
        await publish(app.state.session_factory, COMPANY, cut.id)
    return identities[2]


async def test_ytd_summary_is_disclosed_and_never_double_counts_profit_or_earnings(app):
    facts, ids = ytd_dataset()
    coverage = dt.date(2026, 4, 2)
    generation = await prepared(app, facts, coverage)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, generation)
            query = request(generation)
            actual = await execute(db, context, query, 100000)
            assert actual == calculate(facts, query, coverage)
            assert actual[0][-1]["amount"] == "260.0000"
            assert actual[1]["imported_ytd_included"] is True
            assert "ytd_summary" not in actual[1]["migration_coverage"]
            income = next(row for row in actual[0] if row.get("account_id") == ids["income"])
            assert income["imported_ytd_amount"] == "100.0000"
            post_only = request(generation, date_from="2026-04-02")
            actual = await execute(db, context, post_only, 100000)
            assert actual[0][-1]["amount"] == "160.0000" and not actual[1]["imported_ytd_included"]
            balance = await execute(
                db, context, request(generation, "BALANCE_SHEET", date_from="2026-04-02"), 100000
            )
            assert balance[0][-1]["difference"] == "0.0000"
            assert (
                next(
                    row["amount"]
                    for row in balance[0]
                    if row["row_kind"] == "CURRENT_YEAR_EARNINGS"
                )
                == "260.0000"
            )
            carried = await execute(
                db,
                context,
                request(generation, "BALANCE_SHEET", date_from="2027-04-01", date_to="2027-04-30"),
                100000,
            )
            assert (
                next(
                    row["amount"]
                    for row in carried[0]
                    if row["row_kind"] == "PRIOR_UNTRANSFERRED_EARNINGS"
                )
                == "260.0000"
            )
            with pytest.raises(ConflictError, match="coverage"):
                await execute(db, context, request(generation, date_from="2026-03-01"), 100000)


async def test_unknown_due_dates_have_an_explicit_native_ageing_bucket(app):
    facts, _ = financial_dataset()
    facts = [
        source(
            row.entity,
            row.source_id,
            row.data
            | {
                "document_date": None,
                "due_date": None,
                "terms": {"tracking": "ON_ACCOUNT", "history_unknown": True},
            },
        )
        if row.entity == "open_item" and row.data["direction"] == "DEBT"
        else row
        for row in facts
    ]
    coverage = dt.date(2026, 4, 1)
    generation = await prepared(app, facts, coverage)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, generation)
            for code in ("OUTSTANDING_BILLS", "AGING"):
                query = request(generation, code)
                actual = await item_execute(db, context, query, 100000)
                assert actual == calculate(facts, query, coverage)
                if code == "AGING":
                    assert actual[0][0]["UNKNOWN"] == "150.0000"
                else:
                    unknown = next(row for row in actual[0] if row["direction"] == "DEBT")
                    assert unknown["aging_bucket"] == "UNKNOWN" and unknown["days_overdue"] is None


async def test_inconsistent_ytd_source_cannot_publish(app):
    facts, _ = ytd_dataset()
    altered = []
    for row in facts:
        if row.entity == "opening_batch":
            coverage = row.data["coverage"] | {
                "ytd_summary": [
                    row.data["coverage"]["ytd_summary"][0] | {"amount": "99", "base_amount": "99"}
                ]
            }
            row = source(row.entity, row.source_id, row.data | {"coverage": coverage})
        altered.append(row)
    with pytest.raises(ConflictError, match="nominal opening GL"):
        await prepared(app, altered, dt.date(2026, 4, 2))

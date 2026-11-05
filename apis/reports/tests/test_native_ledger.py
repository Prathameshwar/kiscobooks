"""Native ledgers must match the reference at every page and scope boundary."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from conftest import COMPANY, TENANT
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from sqlalchemy import select
from test_source_versions import staged

from reports.domain.statements import calculate
from reports.models.source_links import ReportJournalLink
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery, page
from reports.schemas.requests import RunRequest
from reports.tasks.source_publication import publish


async def prepared(app, *, tenant=TENANT, company=COMPANY, dataset=None):
    facts, ids = financial_dataset() if dataset is None else dataset
    journals = [row.source_id for row in facts if row.entity == "journal"][:2]
    facts.append(
        source(
            "voucher_execution",
            uuid.uuid4(),
            {
                "voucher_id": str(uuid.uuid4()),
                "revision_id": str(uuid.uuid4()),
                "execution_id": str(uuid.uuid4()),
                "request_hash": "a" * 64,
                "kind": "JOURNAL",
                "profile": "STANDARD",
                "result": {
                    "outcome": "COMMITTED",
                    "effects": [
                        {"effect_kind": "JOURNAL", "effect_id": str(key)} for key in journals
                    ],
                },
            },
        )
    )
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    control = financial_manifest(facts).control
    identities, _ = await staged(app, tenant=tenant, company=company, source=facts, control=control)
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(
                    ReportSourceCut.company_id == company,
                    ReportSourceCut.generation_id == identities[2],
                )
            )
        await publish(app.state.session_factory, company, cut.id)
    return identities, facts, ids


def request(identity, code="ACCOUNT_LEDGER", **changes):
    return RunRequest.model_validate(
        {
            "generation_id": str(identity),
            "code": code,
            "date_from": "2026-04-02",
            "date_to": "2027-04-30",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "code", ["ACCOUNT_LEDGER", "DAY_BOOK", "PARTY_LEDGER", "CASH_BOOK", "BANK_BOOK"]
)
async def test_native_ledger_matches_reference_through_small_and_comparative_pages(app, code):
    identities, facts, ids = await prepared(app)
    query = request(identities[2], code, comparative_from="2026-04-01", comparative_to="2026-04-03")
    expected, _ = calculate(facts, query, dt.date(2026, 4, 1))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            from reports.runtimes import ledger_v1

            for limit in (1, 7, 200):
                retained, cursor = [], None
                parameters = query.model_dump(
                    mode="json",
                    include=set(ledger_v1.RunRequest.model_fields) - {"code", "generation_id"},
                )
                while True:
                    values, cursor = await ledger_v1.rows(
                        db, COMPANY, identities[2], code, parameters, limit, cursor
                    )
                    retained.extend(values)
                    if cursor is None:
                        break
                assert retained == [
                    {
                        key: value
                        for key, value in row.items()
                        if (key != "kind" or row.get("voucher_id"))
                        and not (
                            row["row_kind"] == "OPENING" and key in {"account_name", "currency"}
                        )
                    }
                    for row in expected
                ]
            for limit in (1, 2, 7, 200):
                actual, cursor = [], None
                while True:
                    values, cursor = await page(db, context, query, limit, cursor)
                    actual.extend(values)
                    if cursor is None:
                        break
                    assert cursor["ordinal"] == len(actual)
                assert actual == expected
            # Sequential exports retain balances and never require a full result array.
            single = query.model_copy(update={"comparative_from": None, "comparative_to": None})
            ledger = LedgerQuery(context, single)
            carry, actual, boundary = {}, [], None
            while True:
                values = await ledger.openings(db, boundary, 2, carry)
                if not values:
                    break
                actual.extend(row for _, row in values)
                boundary = values[-1][0]
            boundary = None
            while True:
                values = await ledger.entries(db, boundary, 2, carry)
                if not values:
                    break
                actual.extend(row for _, row in values)
                boundary = values[-1][0]
            assert [row | {"period": "CURRENT"} for row in actual] == calculate(
                facts, single, context.coverage
            )[0]
            assert len(carry) <= len(context.data.accounts)


async def test_native_query_links_are_derived_immutable_and_tenant_company_scoped(app):
    identities, facts, _ = await prepared(app)
    other_tenant, other_company = uuid.uuid4(), uuid.uuid4()
    foreign, _, _ = await prepared(app, tenant=other_tenant)
    company_foreign, _, _ = await prepared(app, company=other_company)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            values, _ = await page(db, context, request(identities[2]), 200)
            assert values == calculate(facts, request(identities[2]), context.coverage)[0]
            assert len(list(await db.scalars(select(ReportJournalLink)))) == 4
            for key in (foreign[2], company_foreign[2]):
                with pytest.raises(ConflictError):
                    await NativeContext.load(db, COMPANY, key)
        async with app.state.session_factory() as db, db.begin():
            link = await db.scalar(
                select(ReportJournalLink).where(ReportJournalLink.company_id == COMPANY)
            )
            link.journal_id = uuid.uuid4()
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
            await db.rollback()
        async with app.state.session_factory() as db, db.begin():
            version = await db.scalar(
                select(ReportFactVersion).where(
                    ReportFactVersion.company_id == COMPANY,
                    ReportFactVersion.entity == "voucher_execution",
                )
            )
            db.add(
                ReportJournalLink(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    version_id=version.id,
                    epoch_id=identities[0],
                    journal_id=uuid.uuid4(),
                )
            )
            with pytest.raises(ConflictError, match="derived"):
                await db.flush()
            await db.rollback()


async def test_native_ledger_filters_and_cursor_validation(app):
    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for changes in (
                {"account_id": ids["cash"]},
                {"basis": "TRANSACTION", "currency": "INR"},
                {"basis": "TRANSACTION", "currency": "USD"},
            ):
                query = request(identities[2], **changes)
                assert (await page(db, context, query, 200))[0] == calculate(
                    facts, query, context.coverage
                )[0]
            for changes in ({"account_id": uuid.uuid4()}, {"currency": "USD"}):
                with pytest.raises(ValidationFailedError):
                    await page(db, context, request(identities[2]).model_copy(update=changes), 200)
            for cursor in (
                {"period": 2},
                {"period": 1, "phase": "entry", "after": None, "ordinal": 0},
                {"period": 0, "phase": "opening", "after": [], "ordinal": 0},
                {"period": 0, "phase": "entry", "after": ["bad", "bad", 1, "bad"], "ordinal": 0},
            ):
                with pytest.raises(ValidationFailedError):
                    await page(db, context, request(identities[2]), 2, cursor)


async def test_v2_pins_native_ledger_without_materializing_and_rechecks_access(
    app, client, monkeypatch
):
    from conftest import PERMISSIONS, headers
    from sqlalchemy import func
    from test_framework_execution import proof

    from reports.domain.book_summaries import summarize
    from reports.models.framework import ReportJob, ReportResultBatch
    from reports.tasks.framework_worker import process

    identities, facts, ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.reference_fact_limit = 1
    path = f"/v2/companies/{COMPANY}/report-runs"
    query = request(identities[2])
    body = {
        "code": "ACCOUNT_LEDGER",
        "generation_id": str(identities[2]),
        "parameters": {
            "date_from": query.date_from.isoformat(),
            "date_to": query.date_to.isoformat(),
        },
    }
    key = headers()
    accepted = await client.post(path, headers=key, json=body)
    assert accepted.status_code == 202, accepted.text
    assert (await client.post(path, headers=key, json=body)).json()["id"] == accepted.json()["id"]
    identity = uuid.UUID(accepted.json()["id"])

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    target = path + "/" + str(identity)
    result = await client.get(target, headers=headers())
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    assert result.json()["result"]["plan"]["mode"] == "PINNED_QUERY"
    assert result.json()["result"]["row_count"] is None
    assert result.json()["result"]["content_hash"] is None
    expected_rows = calculate(facts, query, dt.date(2026, 4, 1))[0]
    assert result.json()["result"]["evidence"]["book_summary"] == summarize(
        "ACCOUNT_LEDGER", expected_rows
    )
    actual, cursor, first_cursor = [], None, None
    while True:
        response = await client.get(
            target + "/rows",
            headers=headers(),
            params={"limit": 2} | ({"cursor": cursor} if cursor else {}),
        )
        assert response.status_code == 200, response.text
        actual.extend(response.json()["items"])
        cursor = response.json()["page"]["next_cursor"]
        first_cursor = first_cursor or cursor
        if cursor is None:
            break
    assert [row["ordinal"] for row in actual] == list(range(1, len(actual) + 1))
    assert [row["data"] for row in actual] == expected_rows
    revoked = headers(permissions=PERMISSIONS - {"ledger.read"})
    assert (await client.get(target + "/rows", headers=revoked)).status_code == 403
    assert (
        await client.get(target + "/rows", headers=headers(user=uuid.uuid4()))
    ).status_code == 403
    app.state.settings.native_queries_enabled = False
    assert (
        await client.get(target + "/rows", headers=headers(), params={"cursor": first_cursor})
    ).status_code == 200

    def removed_definition(*args, **kwargs):
        raise AssertionError("retained native results must use their packaged runtime")

    with monkeypatch.context() as patch:
        patch.setattr("reports.tasks.native_execution.catalog", removed_definition)
        patch.setattr("reports.queries.native_context.QUERY_VERSION", 999)
        patch.setattr("reports.domain.statements.Facts.selected", removed_definition)
        retained = await client.get(target + "/rows", headers=headers(), params={"limit": 200})
        assert retained.status_code == 200, retained.text
        assert [row["data"] for row in retained.json()["items"]] == [row["data"] for row in actual]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(ReportResultBatch.id))) == 0
            assert (await db.get(ReportJob, identity)).completed_rows == 0


async def test_native_cut_preserves_old_balances_after_a_backdated_append(app):
    from decimal import Decimal

    from reporting_contract.contract import Manifest
    from test_source_versions import apply_change, change_manifest

    identities, facts, _ = await prepared(app)
    original = next(
        row for row in facts if row.entity == "journal" and row.data["kind"] == "MANUAL"
    )
    journal_id = uuid.uuid4()
    added = [
        source(
            "journal",
            journal_id,
            original.data
            | {
                "source_id": str(journal_id),
                "number": "BACKDATED/1",
                "posting_date": "2026-04-15",
                "document_date": "2026-04-15",
                "posted_at": "2026-04-15T00:00:00Z",
            },
        )
    ]
    added.extend(
        source("journal_line", uuid.uuid4(), row.data | {"journal_id": str(journal_id)})
        for row in facts
        if row.entity == "journal_line" and row.data["journal_id"] == str(original.source_id)
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            old_cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
            proof = Manifest.model_validate(old_cut.manifest)
    counts = dict(proof.control.counts)
    counts["journal"] += 1
    counts["journal_line"] += len(added) - 1
    totals = {currency: dict(values) for currency, values in proof.control.base_totals.items()}
    for side in ("DEBIT", "CREDIT"):
        totals["INR"][side] = str(
            Decimal(totals["INR"][side]) + Decimal(original.data["total_" + side.lower()])
        )
    changed = change_manifest(proof, added, proof.sequence + 1).model_copy(
        update={
            "control": proof.control.model_copy(update={"counts": counts, "base_totals": totals}),
        }
    )
    newer = await apply_change(app, identities[0], changed, added)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == newer)
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            for generation, expected_source in ((identities[2], facts), (newer, facts + added)):
                context = await NativeContext.load(db, COMPANY, generation)
                query = request(generation)
                assert (await page(db, context, query, 200))[0] == calculate(
                    expected_source, query, context.coverage
                )[0]


async def test_native_deep_cursor_reads_only_the_requested_index_range(app):
    """A deep page must seek in MySQL, not discard the entire preceding range."""
    identities, _, _ = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            if db.bind.dialect.name != "mysql":
                pytest.skip("native MySQL index access regression")
            context = await NativeContext.load(db, COMPANY, identities[2])
            ledger = LedgerQuery(context, request(identities[2], date_from="2026-04-01"))
            candidates = (await db.execute(ledger.entry_selection(None, 200))).all()
            before = candidates[-2]
            cursor = [
                str(before.posting_date),
                str(before.journal_id),
                before.line_sequence,
                str(before.source_id),
            ]
            connection = await db.connection()

            async def reads():
                result = await connection.exec_driver_sql(
                    "SHOW SESSION STATUS LIKE 'Handler_read_next'"
                )
                return int(result.one()[1])

            started = await reads()
            query = ledger.entry_selection(cursor, 1).with_hint(
                ledger.line, "FORCE INDEX (ix_report_posted_line_date)", dialect_name="mysql"
            )
            selected = (await db.execute(query)).all()
            read_count = await reads() - started
            assert len(selected) == 1
            assert read_count <= 3, f"one deep row scanned {read_count} preceding index records"

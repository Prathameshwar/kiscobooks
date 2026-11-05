"""Query-only capacity probe; synthetic Core cloning in a new disposable local schema.

The initial source template is verified through the real pipeline. Large history cloning
measures no ingest/publication capacity. Reads retain normal guarded sessions and exact
expected balances are checked at each sampled shallow and deep cursor position.
"""

import argparse
import asyncio
import hashlib
import itertools
import json
import os
import statistics
import time
from pathlib import Path

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.process_memory import peak_rss
from reporting_contract.contract import FactPage
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import make_url

from reports.domain.statements import calculate
from reports.metadata import service_metadata
from reports.models.core import ReportGeneration
from reports.models.daily_balances import ReportDailyBalance, grouped
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportFactVersion
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import page
from reports.queries.native_statements import CODES as FINANCIAL_CODES
from reports.queries.native_statements import execute as financial
from reports.schemas.requests import RunRequest
from reports.tasks import source_versions as versions
from reports.tasks.source_publication import publish
from tools.framework_data import BEGIN, END, facts, identity, period_number, posting_date, source
from tools.framework_data import manifest as fixture_manifest
from tools.verify_mysql import database


def columns(row):
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.computed is None
    }


def financial_oracle(transactions):
    """At most one aggregate transaction per day; reference calculations stay bounded."""
    days = (END - BEGIN).days + 1
    cycles, extra = divmod(transactions, days)
    result = []
    for fact in facts(min(days, transactions)):
        if fact.entity == "journal":
            index = int(fact.data["number"].rsplit("/", 1)[-1])
            amount = str(100 * (cycles + int(index < extra)))
            fact = source(
                fact.entity,
                fact.source_id,
                fact.data | {"total_debit": amount, "total_credit": amount},
            )
        elif fact.entity == "journal_line":
            index = fact.source_id.int & ((1 << 40) - 1)
            amount = str(100 * (cycles + int(index // 2 < extra)))
            fact = source(
                fact.entity, fact.source_id, fact.data | {"amount": amount, "base_amount": amount}
            )
        result.append(fact)
    return result


async def measure(server, transactions, export_output=None):
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("disposable loopback server without schema required")
    if not 1 <= transactions <= 5_000_000:
        raise ValueError("fixture exceeds ten million GL lines")
    name = "reports_test_" + uuid7().hex
    await database(server, name, create=True)
    engine = create_engine(parsed.set(database=name).render_as_string(hide_password=False))
    factory = create_session_factory(engine, guarded=True)
    tenant, company, snapshot = identity(20), identity(21), identity(22)
    source_hashes = {
        path.relative_to(Path(__file__).resolve().parents[1]).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (Path(__file__).resolve().parents[1] / "src").rglob("*.py")
    }
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        with tenant_scope(tenant):
            proof = fixture_manifest(1, tenant=tenant, company=company, snapshot=snapshot)
            async with factory() as db, db.begin():
                generation = ReportGeneration(
                    tenant_id=tenant, company_id=company, snapshot_id=snapshot
                )
                db.add(generation)
                await db.flush()
                epoch = await versions.new_epoch(db, generation, proof)
                bundle = await versions.bundle(db, generation, proof)
                await versions.stage(
                    db, epoch, bundle, FactPage(manifest_id=snapshot, items=list(facts(1))), 0
                )
                await versions.finish(db, epoch, bundle)
                await db.flush()
                cut = await versions.pin(db, epoch, generation, proof)
            await publish(factory, company, cut.id)
            async with factory() as db:
                base = list(
                    await db.scalars(
                        select(ReportFactVersion).where(ReportFactVersion.company_id == company)
                    )
                )
                journal = next(row for row in base if row.entity == "journal")
                lines = sorted(
                    (row for row in base if row.entity == "journal_line"),
                    key=lambda row: row.line_sequence,
                )
                projected = sorted(
                    await db.scalars(
                        select(ReportPostedLine).where(ReportPostedLine.company_id == company)
                    ),
                    key=lambda row: row.line_sequence,
                )
                journal_template, line_templates, posted_templates = (
                    columns(journal),
                    list(map(columns, lines)),
                    list(map(columns, projected)),
                )
                daily_template = columns(
                    await db.scalar(
                        select(ReportDailyBalance).where(ReportDailyBalance.company_id == company)
                    )
                )
            started = time.perf_counter()
            ordinal = proof.fact_count
            # Core cloning is limited to this disposable fixture; measured reads stay guarded.
            for start in range(1, transactions, 500):
                source_rows, posted_rows = [], []
                for index in range(start, min(start + 500, transactions)):
                    date = posting_date(index)
                    header_id, journal_source_id = uuid7(), identity(7, index)
                    header = journal_template | {
                        "id": header_id,
                        "source_id": journal_source_id,
                        "posting_date": date,
                        "ordinal": ordinal + 1,
                    }
                    header["data"] = header["data"] | {
                        "source_id": str(journal_source_id),
                        "number": f"BENCH/{index:010}",
                        "document_date": date.isoformat(),
                        "posting_date": date.isoformat(),
                        "posted_at": date.isoformat() + "T00:00:00Z",
                        "fiscal_period_id": str(identity(5, period_number(date))),
                    }
                    header["wire_bytes"] = len(canonical_json(header["data"])) + 256
                    header["content_hash"] = hashlib.sha256(
                        canonical_json(
                            {
                                "entity": "journal",
                                "source_id": str(journal_source_id),
                                "data": header["data"],
                            }
                        )
                    ).hexdigest()
                    source_rows.append(header)
                    for offset, template in enumerate(line_templates):
                        line_id, line_source_id = uuid7(), identity(8, index * 2 + offset)
                        line = template | {
                            "id": line_id,
                            "source_id": line_source_id,
                            "relation_id": journal_source_id,
                            "ordinal": ordinal + 2 + offset,
                        }
                        line["data"] = line["data"] | {"journal_id": str(journal_source_id)}
                        line["wire_bytes"] = len(canonical_json(line["data"])) + 256
                        line["content_hash"] = hashlib.sha256(
                            canonical_json(
                                {
                                    "entity": "journal_line",
                                    "source_id": str(line_source_id),
                                    "data": line["data"],
                                }
                            )
                        ).hexdigest()
                        source_rows.append(line)
                        posted_rows.append(
                            posted_templates[offset]
                            | {
                                "id": uuid7(),
                                "line_id": line_source_id,
                                "journal_id": journal_source_id,
                                "line_version_id": line_id,
                                "journal_version_id": header_id,
                                "posting_date": date,
                                "source_bytes": line["wire_bytes"] + header["wire_bytes"],
                            }
                        )
                    ordinal += 3
                async with engine.begin() as connection:
                    await connection.execute(insert(ReportFactVersion.__table__), source_rows)
                    await connection.execute(insert(ReportPostedLine.__table__), posted_rows)
                if start % 50000 == 1:
                    print(
                        json.dumps(
                            {
                                "seeded_transactions": min(start + 500, transactions),
                                "elapsed_seconds": time.perf_counter() - started,
                            }
                        ),
                        flush=True,
                    )
            seeded_seconds = time.perf_counter() - started
            # Recompute this synthetic fixture's daily data after Core cloning. This
            # bypass is restricted to the tool-created disposable schema, like the
            # source clone above; it is not evidence of production publication.
            async with engine.begin() as connection:
                groups = (
                    (
                        await connection.execute(
                            grouped(company, cut.epoch_id, cut.sequence)
                            .where(ReportPostedLine.tenant_id == tenant)
                            .limit(100001)
                        )
                    )
                    .mappings()
                    .all()
                )
                if len(groups) > 100000:
                    raise ValueError("synthetic daily fixture exceeds its bounded group capacity")
                await connection.execute(
                    delete(ReportDailyBalance.__table__).where(
                        ReportDailyBalance.tenant_id == tenant,
                        ReportDailyBalance.company_id == company,
                        ReportDailyBalance.cut_id == cut.id,
                    )
                )
                for batch in itertools.batched(groups, 200):
                    await connection.execute(
                        insert(ReportDailyBalance.__table__),
                        [daily_template | dict(group) | {"id": uuid7()} for group in batch],
                    )
            async with factory() as db:
                assert (
                    await db.scalar(
                        select(func.count(ReportPostedLine.id)).where(
                            ReportPostedLine.company_id == company
                        )
                    )
                    == 2 * transactions
                )
                context = await NativeContext.load(db, company, generation.id)
                query = RunRequest.model_validate(
                    {
                        "code": "ACCOUNT_LEDGER",
                        "generation_id": str(generation.id),
                        "date_from": BEGIN.isoformat(),
                        "date_to": END.isoformat(),
                    }
                )
                samples = []
                days = (END - BEGIN).days + 1
                cycles, extra = divmod(transactions, days)
                for index in (None, transactions // 2, max(0, transactions - 2)):
                    cursor = None
                    if index is not None:
                        day = index % days
                        rank = cycles * day + min(extra, day) + index // days
                        cursor = {
                            "period": 0,
                            "phase": "entry",
                            "after": [
                                posting_date(index).isoformat(),
                                str(identity(7, index)),
                                1,
                                str(identity(8, index * 2)),
                            ],
                            "ordinal": 2 + rank * 2 + 1,
                        }
                    elapsed = []
                    for _ in range(20):
                        begun = time.perf_counter()
                        rows, _ = await page(db, context, query, 200, cursor)
                        elapsed.append(time.perf_counter() - begun)
                        for row in rows:
                            if row["row_kind"] == "OPENING":
                                assert row["balance"] == "0.0000"
                                continue
                            number = int(row["number"].rsplit("/", 1)[-1])
                            day = number % days
                            rank = cycles * day + min(extra, day) + number // days + 1
                            expected = (
                                rank * 100 * (1 if row["account_id"] == str(identity(1, 0)) else -1)
                            )
                            assert row["balance"] == f"{expected}.0000"
                    samples.append(
                        {
                            "cursor_transaction": index,
                            "count": len(elapsed),
                            "median_seconds": statistics.median(elapsed),
                            "p95_seconds": sorted(elapsed)[18],
                            "max_seconds": max(elapsed),
                        }
                    )
                    print(json.dumps({"query_sample": samples[-1]}), flush=True)
                financial_samples = []
                reference = financial_oracle(transactions)
                for code in sorted(FINANCIAL_CODES):
                    current = query.model_copy(update={"code": code})
                    expected = calculate(reference, current, BEGIN)[0]
                    elapsed = []
                    for _ in range(20):
                        begun = time.perf_counter()
                        rows, _ = await financial(db, context, current, 100000)
                        elapsed.append(time.perf_counter() - begun)
                        assert rows == expected
                    financial_samples.append(
                        {
                            "code": code,
                            "count": len(elapsed),
                            "median_seconds": statistics.median(elapsed),
                            "p95_seconds": sorted(elapsed)[18],
                            "max_seconds": max(elapsed),
                            "rows": len(expected),
                        }
                    )
                    print(json.dumps({"financial_sample": financial_samples[-1]}), flush=True)
                export_result = None
                if export_output is not None:
                    from tools.framework_database_exports import measure_exports

                    export_result = await measure_exports(
                        db, company, generation.id, query, transactions, export_output
                    )
            return {
                "kind": "query_only_cloned_fixture",
                "journal_lines": transactions * 2,
                "seed_seconds": seeded_seconds,
                "peak_rss_bytes": peak_rss(),
                "samples": samples,
                "financial_samples": financial_samples,
                "database_exports": export_result,
                "source_hashes_at_start": source_hashes,
                "limitations": [
                    "synthetic Core cloning; large receipt and claims intentionally not built",
                    "single company; no HTTP/authorization/serialization timing",
                    "two accounts over two fiscal years; "
                    "no high-cardinality dimensions or open bills",
                    "overlaps local development workloads; not production SLO acceptance",
                ],
            }
    finally:
        await engine.dispose()
        await database(server, name, create=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=10000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        measure(
            os.environ.get("REPORTS_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396"),
            args.transactions,
            args.export_output,
        )
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "source_hashes_at_start"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

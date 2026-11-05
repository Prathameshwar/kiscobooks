"""Native bounded version-ingestion/reconciliation benchmark in a disposable schema."""

import argparse
import asyncio
import hashlib
import itertools
import json
import os
import time
import uuid
from pathlib import Path

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.process_memory import peak_rss
from reporting_contract.contract import FactPage
from sqlalchemy import event
from sqlalchemy.engine import make_url

from reports.metadata import service_metadata
from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import ReportSourceCut, ReportSourceEpoch
from reports.tasks import source_versions as versions
from reports.tasks.common import get
from reports.tasks.source_publication import publish
from reports.tasks.source_verification import verify
from tools.framework_data import facts, identity, manifest
from tools.verify_mysql import database


async def measure(
    server: str, transactions: int, *, publication: bool = False, query_pages: bool = False
) -> dict[str, object]:
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("disposable loopback server without schema required")
    if not 1 <= transactions <= 10000000:
        raise ValueError("benchmark bound is 1..10 million synthetic transactions")
    name = "reports_test_" + uuid.uuid4().hex
    await database(server, name, create=True)
    engine = create_engine(parsed.set(database=name).render_as_string(hide_password=False))
    factory = create_session_factory(engine, guarded=True)
    statements = 0
    phase = "setup"
    last_progress = time.perf_counter()
    query_timings = []
    sql_started = 0.0

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def count(_connection, _cursor, _statement, _parameters, _context, _many):
        nonlocal statements, last_progress, sql_started
        sql_started = time.perf_counter()
        statements += 1
        if time.perf_counter() - last_progress >= 60:
            last_progress = time.perf_counter()
            print(
                json.dumps(
                    {"phase": phase, "sql_statements": statements, "peak_rss_bytes": peak_rss()}
                ),
                flush=True,
            )

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def timed(_connection, _cursor, statement, _parameters, _context, _many):
        if phase == "query":
            query_timings.append({"seconds": time.perf_counter() - sql_started, "sql": statement})

    tenant, company, snapshot = identity(20), identity(21), identity(22)
    results = {}
    source_hashes = {
        path.relative_to(Path(__file__).resolve().parents[1]).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for folder in (Path(__file__).resolve().parents[1] / "src", Path(__file__).resolve().parent)
        for path in sorted(folder.rglob("*.py"))
    }
    try:
        async with engine.begin() as db:
            await db.run_sync(service_metadata().create_all)
        started = time.perf_counter()
        proof = manifest(transactions, tenant=tenant, company=company, snapshot=snapshot)
        results["source_fixture_seconds"] = time.perf_counter() - started
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                generation = ReportGeneration(
                    tenant_id=tenant, company_id=company, snapshot_id=snapshot
                )
                db.add(generation)
                await db.flush()
                epoch = await versions.new_epoch(db, generation, proof)
                bundle = await versions.bundle(db, generation, proof)
                generation_id, epoch_id, bundle_id = generation.id, epoch.id, bundle.id
            phase = "stage"
            started, before, after = time.perf_counter(), statements, 0
            for items in itertools.batched(facts(transactions), 200):
                end = after + len(items)
                async with factory() as db, db.begin():
                    epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
                    bundle = await get(db, company, ReportBundle, bundle_id, lock=True)
                    await versions.stage(
                        db,
                        epoch,
                        bundle,
                        FactPage(
                            manifest_id=snapshot,
                            items=list(items),
                            next_after=end if end < proof.fact_count else None,
                        ),
                        after,
                    )
                after = end
                if after % 100000 == 0:
                    print(
                        json.dumps(
                            {
                                "staged_facts": after,
                                "seconds": time.perf_counter() - started,
                                "peak_rss_bytes": peak_rss(),
                            }
                        ),
                        flush=True,
                    )
            results["stage"] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - before,
            }
            started, before = time.perf_counter(), statements
            phase = "receipt"
            async with factory() as db, db.begin():
                epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
                bundle = await get(db, company, ReportBundle, bundle_id, lock=True)
                await versions.finish(db, epoch, bundle)
                await db.flush()
                generation = await get(db, company, ReportGeneration, generation_id)
                cut = await versions.pin(db, epoch, generation, proof)
                cut_id = cut.id
            results["verify_receipt"] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - before,
            }
            started, before = time.perf_counter(), statements
            phase = "publication" if publication else "reconcile"
            if publication:
                await publish(factory, company, cut_id)
            async with factory() as db:
                cut = await get(db, company, ReportSourceCut, cut_id)
                evidence = cut.verification if publication else await verify(db, cut)
                assert evidence is not None and evidence["base_totals"] == proof.control.base_totals
                if publication:
                    assert (
                        await get(db, company, ReportGeneration, generation_id)
                    ).status == "READY"
            results[phase] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - before,
            }
            if query_pages:
                if not publication:
                    raise ValueError("query measurements require full publication")
                from reports.queries.native_context import NativeContext
                from reports.queries.native_ledger import page
                from reports.schemas.requests import RunRequest

                phase = "query"
                query = RunRequest.model_validate(
                    {
                        "generation_id": str(generation_id),
                        "code": "ACCOUNT_LEDGER",
                        "date_from": "2026-04-01",
                        "date_to": "2027-03-31",
                    }
                )
                async with factory() as db:
                    started = time.perf_counter()
                    context = await NativeContext.load(db, company, generation_id)
                    loaded = time.perf_counter() - started
                    cursor, timings, sizes = None, [], []
                    for _ in range(20):
                        started, before = time.perf_counter(), statements
                        rows, cursor = await page(db, context, query, 200, cursor)
                        timings.append(
                            {
                                "seconds": time.perf_counter() - started,
                                "statements": statements - before,
                            }
                        )
                        sizes.append(len(rows))
                        if cursor is None:
                            break
                    results["query_pages"] = {
                        "dimension_seconds": loaded,
                        "pages": timings,
                        "rows": sizes,
                        "sql_timings": query_timings,
                    }
        return {
            "kind": "versioned_native",
            "business_transactions": transactions,
            "journal_lines": 2 * transactions,
            "source_facts": proof.fact_count,
            "published": publication,
            "source_hashes_at_start": source_hashes,
            "peak_rss_bytes": peak_rss(),
            "measurements": results,
            "limitations": [
                "single ingest worker; excludes HTTP/broker and owner posting impact",
                "no export benchmark; query pages measured only when explicitly requested",
            ],
        }
    finally:
        await engine.dispose()
        await database(server, name, create=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query-pages", action="store_true")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="include financial verification, all immutable claims and readiness",
    )
    args = parser.parse_args()
    server = os.environ.get("REPORTS_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    result = asyncio.run(
        measure(server, args.transactions, publication=args.publish, query_pages=args.query_pages)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

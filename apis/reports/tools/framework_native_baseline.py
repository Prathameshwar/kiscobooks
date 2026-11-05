"""Legacy native SQL timings/counts in a newly created disposable loopback schema."""

import argparse
import asyncio
import itertools
import json
import os
import time
import uuid
from pathlib import Path

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from reporting_contract.contract import FactPage
from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from reports.metadata import service_metadata
from reports.models import core as m
from reports.schemas.requests import RunRequest
from reports.tasks import ingest, runs
from reports.tasks.common import company_lock, get
from tools.framework_data import BEGIN, END, facts, identity, manifest
from tools.verify_mysql import database


async def measure(server: str, transactions: int) -> dict[str, object]:
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("benchmark requires loopback server without schema")
    if not 1 <= transactions <= 1000:
        raise ValueError("legacy native probe is bounded to 1000 synthetic transactions")
    name = "reports_test_" + uuid.uuid4().hex
    await database(server, name, create=True)
    engine = create_engine(parsed.set(database=name).render_as_string(hide_password=False))
    factory = create_session_factory(engine, guarded=True)
    tenant, company, snapshot = identity(20), identity(21), identity(22)
    proof = manifest(transactions, tenant=tenant, company=company, snapshot=snapshot)
    statements = 0

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def count(_connection, _cursor, _statement, _parameters, _context, _many):
        nonlocal statements
        statements += 1

    timings = {}
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
            version = await connection.scalar(text("SELECT VERSION()"))
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                generation = m.ReportGeneration(
                    tenant_id=tenant,
                    company_id=company,
                    snapshot_id=snapshot,
                )
                db.add(generation)
                await db.flush()
                generation_id = generation.id
                bundle = await ingest.bundle(db, generation, proof)
                bundle_id = bundle.id
            started, initial = time.perf_counter(), statements
            ordinal = 0
            for batch in itertools.batched(facts(transactions), 200):
                after = ordinal
                ordinal += len(batch)
                async with factory() as db, db.begin():
                    bundle = await get(db, company, m.ReportBundle, bundle_id, lock=True)
                    await ingest.stage(
                        db,
                        bundle,
                        FactPage(
                            manifest_id=snapshot,
                            items=list(batch),
                            next_after=ordinal if ordinal < proof.fact_count else None,
                        ),
                        after,
                    )
            timings["stage"] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - initial,
            }
            started, initial = time.perf_counter(), statements
            async with factory() as db, db.begin():
                generation = await get(db, company, m.ReportGeneration, generation_id, lock=True)
                bundle = await get(db, company, m.ReportBundle, bundle_id, lock=True)
                await ingest.apply(db, generation, bundle)
                await db.flush()
                generation.target_sequence = generation.applied_sequence
                await ingest.activate(db, generation)
            timings["apply_activate"] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - initial,
            }
            request = RunRequest(
                code="TRIAL_BALANCE", generation_id=generation_id, date_from=BEGIN, date_to=END
            )
            async with factory() as db, db.begin():
                definition = await runs.definition(db, tenant, company, request.code)
                run = m.ReportRun(
                    tenant_id=tenant,
                    company_id=company,
                    generation_id=generation_id,
                    definition_id=definition.id,
                    permission_hash="c" * 64,
                    parameters=request.model_dump(mode="json"),
                )
                db.add(run)
                await db.flush()
                run_id = run.id
            started, initial = time.perf_counter(), statements
            async with factory() as db, db.begin():
                await company_lock(db, tenant, company)
                run = await get(db, company, m.ReportRun, run_id, lock=True)
                await runs.complete(db, run)
            timings["run"] = {
                "seconds": time.perf_counter() - started,
                "statements": statements - initial,
            }
        async with engine.connect() as connection:
            plan = await connection.scalar(
                text(
                    "EXPLAIN FORMAT=JSON SELECT id, posting_date, amount FROM report_line "
                    "WHERE tenant_id=UNHEX(:tenant) AND company_id=UNHEX(:company) "
                    "AND generation_id=UNHEX(:generation) "
                    "AND account_id=UNHEX(:account) AND posting_date>=:start "
                    "ORDER BY posting_date, id LIMIT 201"
                ),
                {
                    "tenant": tenant.hex,
                    "company": company.hex,
                    "generation": generation_id.hex,
                    "account": identity(1).hex,
                    "start": BEGIN,
                },
            )
        return {
            "kind": "legacy_native_baseline",
            "mysql_version": version,
            "business_transactions": transactions,
            "journal_lines": 2 * transactions,
            "source_facts": proof.fact_count,
            "timings": timings,
            "account_range_plan": json.loads(plan),
            "limitations": [
                "single worker; no API/queue/owner-write-fence load",
                "disposable tables created from migration-verified metadata",
            ],
        }
    finally:
        await engine.dispose()
        await database(server, name, create=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    server = os.environ.get("REPORTS_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    result = asyncio.run(measure(server, args.transactions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "account_range_plan"}, indent=2
        )
    )


if __name__ == "__main__":
    main()

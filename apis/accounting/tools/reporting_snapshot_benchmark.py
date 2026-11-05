"""Measure native snapshot memory/fence and real posting endpoints in a disposable schema.

Synthetic history is cloned with Core inserts ONLY in the new random test schema. This
excludes historical posting validation from fixture timing; measured writes use the API
and ordinary guarded sessions. Identity's reservation boundary is a test double.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from billing_platform.db import create_engine, tenant_scope
from billing_platform.ids import uuid7
from billing_platform.process_memory import peak_rss
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy.engine import make_url

from accounting.config import Settings
from accounting.main import create_app
from accounting.metadata import service_metadata
from accounting.models.ledger import Journal, JournalLine
from accounting.models.reporting import ReportChange
from accounting.models.reporting_snapshot import ReportSnapshotBuild
from accounting.tasks import reporting_feed as feed
from accounting.tasks import reporting_snapshot as snapshot
from tests.conftest import COMPANY, ENCRYPTION, SECRET, TENANT
from tests.test_ledger_api import create_journal, journal_setup, post_journal
from tools.verify_mysql import schema


class PostingPacer:
    """Two writes per sample stay below the real 120/minute per-user boundary."""

    def __init__(self):
        self.next_start = 0.0

    async def wait(self):
        delay = self.next_start - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.next_start = time.monotonic() + 1.1


def distribution(values):
    ordered = sorted(values)
    return {
        "count": len(values),
        "median_seconds": statistics.median(values),
        "p95_seconds": ordered[math.ceil(len(values) * 0.95) - 1],
        "max_seconds": max(values),
    }


def seeded_control(db):
    """Anchor the synthetic fixture's head; never invoked by production application paths."""
    setup, previous = feed.lock(db, COMPANY), feed.head(db, COMPANY)
    identity = uuid7()
    proof = feed.manifest(
        db, setup, identity, "CHANGE", previous.sequence + 1, 0, hashlib.sha256().hexdigest()
    )
    db.add(
        ReportChange(
            id=identity,
            tenant_id=TENANT,
            company_id=COMPANY,
            sequence=proof.sequence,
            manifest=proof.model_dump(mode="json"),
        )
    )
    feed.evidence_audit(db, setup, identity, "captured")


async def child(tenant, company, identity):
    url = os.environ["RF3_SNAPSHOT_BENCH_DATABASE_URL"]
    parsed = make_url(url)
    if (
        parsed.host not in {"localhost", "127.0.0.1", "::1"}
        or re.fullmatch(r"accounting_test_[0-9a-f]{32}", parsed.database or "") is None
    ):
        raise ValueError("worker requires a disposable loopback benchmark schema")
    settings = Settings(
        database_url=url,
        actor_signing_secret=SecretStr(os.environ["RF3_SNAPSHOT_BENCH_ACTOR_SECRET"]),
        encryption_key=SecretStr(os.environ["RF3_SNAPSHOT_BENCH_ENCRYPTION"]),
        report_snapshot_enabled=True,
        report_snapshot_fact_limit=40_000_000,
        report_snapshot_seconds=3600,
    )
    engine = create_engine(url)
    try:
        await snapshot.build(
            engine, settings, uuid.UUID(tenant), uuid.UUID(company), uuid.UUID(identity)
        )
        print(json.dumps({"peak_rss_bytes": peak_rss()}), flush=True)
    finally:
        await engine.dispose()


async def measure(server, transactions, samples):
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("disposable loopback server without database required")
    if not 1 <= transactions <= 5_000_000 or not 5 <= samples <= 100:
        raise ValueError("unsupported benchmark fixture/sample size")
    name = "accounting_test_" + uuid.uuid4().hex
    await schema(server, name, create=True)
    settings = Settings(
        database_url=parsed.set(database=name).render_as_string(hide_password=False),
        actor_signing_secret=SecretStr(SECRET),
        encryption_key=SecretStr(ENCRYPTION),
        report_snapshot_enabled=True,
        report_snapshot_fact_limit=40_000_000,
        report_snapshot_seconds=3600,
    )
    app = create_app(settings)
    engine, factory = app.state.engine, app.state.session_factory
    root = Path(__file__).resolve().parents[1]
    hashes = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "src").rglob("*.py"))
    }
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://accounting.test"
        ) as client:
            body, _, _ = await journal_setup(client, app)
            draft = await create_journal(client, body)
            posted = await post_journal(client, draft)
            assert posted.status_code == 200, posted.text
            with tenant_scope(TENANT):
                async with factory() as db:
                    journal = await db.get(Journal, uuid.UUID(draft["id"]))
                    lines = list(
                        await db.scalars(
                            select(JournalLine).where(
                                JournalLine.company_id == COMPANY,
                                JournalLine.journal_id == journal.id,
                            )
                        )
                    )
                    header = {
                        c.name: getattr(journal, c.name)
                        for c in Journal.__table__.columns
                        if c.computed is None
                    }
                    details = [
                        {
                            c.name: getattr(line, c.name)
                            for c in JournalLine.__table__.columns
                            if c.computed is None
                        }
                        for line in lines
                    ]
            started = time.perf_counter()
            for start in range(1, transactions, 500):
                headers, entries = [], []
                for index in range(start, min(start + 500, transactions)):
                    identity = uuid7()
                    headers.append(
                        header
                        | {
                            "id": identity,
                            "number": f"RF3/BENCH/{index}",
                            "source_id": str(identity),
                            "reservation_id": uuid7(),
                        }
                    )
                    entries.extend(
                        line | {"id": uuid7(), "journal_id": identity} for line in details
                    )
                async with engine.begin() as connection:
                    await connection.execute(insert(Journal.__table__), headers)
                    await connection.execute(insert(JournalLine.__table__), entries)
                if start % 50000 == 1:
                    print(
                        json.dumps(
                            {
                                "seeded_transactions": min(start + 500, transactions),
                                "seconds": time.perf_counter() - started,
                            }
                        ),
                        flush=True,
                    )
            seeded_seconds = time.perf_counter() - started
            with tenant_scope(TENANT):
                async with factory() as db, db.begin():
                    await db.run_sync(seeded_control)

            pacer = PostingPacer()

            async def posting_sample():
                await pacer.wait()
                started = time.perf_counter()
                row = await create_journal(client, body)
                result = await post_journal(client, row)
                assert result.status_code == 200, (result.status_code, result.text)
                return time.perf_counter() - started

            baseline = [await posting_sample() for _ in range(samples)]
            print(json.dumps({"baseline": distribution(baseline)}), flush=True)
            identity = uuid7()
            with tenant_scope(TENANT):
                async with factory() as db, db.begin():
                    db.add(ReportSnapshotBuild(id=identity, tenant_id=TENANT, company_id=COMPANY))
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "tools.reporting_snapshot_benchmark",
                "--worker",
                "--tenant",
                str(TENANT),
                "--company",
                str(COMPANY),
                "--snapshot",
                str(identity),
                cwd=root,
                env=os.environ
                | {
                    "RF3_SNAPSHOT_BENCH_DATABASE_URL": settings.database_url,
                    "RF3_SNAPSHOT_BENCH_ACTOR_SECRET": SECRET,
                    "RF3_SNAPSHOT_BENCH_ENCRYPTION": ENCRYPTION,
                },
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            task = asyncio.create_task(process.communicate())
            during, barriers = [], []
            try:
                # Wait until the build has actually acquired its owner read view.
                for _ in range(300):
                    with tenant_scope(TENANT):
                        async with factory() as db:
                            row = await db.get(ReportSnapshotBuild, identity)
                            if row.completed_facts or row.status in {"COMPLETE", "FAILED"}:
                                break
                    await asyncio.sleep(0.1)
                for _ in range(samples):
                    if task.done():
                        break
                    during.append(await posting_sample())
                    with tenant_scope(TENANT):
                        async with snapshot.read_view(engine, factory, COMPANY) as (_, _, _, held):
                            barriers.append(held)
                progress = -1
                while not task.done():
                    with tenant_scope(TENANT):
                        async with factory() as db:
                            row = await db.get(ReportSnapshotBuild, identity)
                            bucket = row.completed_facts // 100000
                            if bucket != progress:
                                print(
                                    json.dumps(
                                        {
                                            "snapshot_facts": row.completed_facts,
                                            "status": row.status,
                                        }
                                    ),
                                    flush=True,
                                )
                                progress = bucket
                    await asyncio.sleep(2)
                output, error = await task
                if process.returncode:
                    raise AssertionError(
                        f"snapshot worker exit {process.returncode}: "
                        f"start={error[:2000]!r}; end={error[-2000:]!r}"
                    )
                worker_resources = json.loads(output)
            finally:
                if not task.done():
                    process.terminate()
                    await asyncio.gather(task, return_exceptions=True)
            with tenant_scope(TENANT):
                async with factory() as db:
                    row = await db.get(ReportSnapshotBuild, identity)
                    if row.status != "COMPLETE":
                        raise AssertionError(f"snapshot failed: {row.failure_code}")
                    assert row.manifest["control"]["counts"]["journal_line"] >= 2 * transactions
                    return {
                        "kind": "native_owner_snapshot",
                        "fixture_transactions": transactions,
                        "fixture_lines": 2 * transactions,
                        "fixture_seed_seconds": seeded_seconds,
                        "source_hashes_at_start": hashes,
                        "snapshot": row.evidence,
                        "snapshot_facts": row.completed_facts,
                        "worker_isolation": "SEPARATE_PROCESS",
                        "worker_resources": worker_resources,
                        "baseline_posting": distribution(baseline),
                        "during_snapshot_posting": distribution(during) if during else None,
                        "barriers": distribution(barriers) if barriers else None,
                        "limitations": [
                            "synthetic history; Identity reservation test double",
                            "single company, API create+post; excludes gateway/network latency",
                            "samples paced at least 1.1 seconds apart outside measured latency",
                            "small fixtures may finish before all concurrent samples",
                        ],
                    }
    finally:
        await engine.dispose()
        await schema(server, name, create=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=100)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--tenant")
    parser.add_argument("--company")
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    if args.worker:
        asyncio.run(child(args.tenant, args.company, args.snapshot))
        return
    if args.output is None:
        parser.error("--output is required for the benchmark controller")
    result = asyncio.run(
        measure(
            os.environ.get(
                "ACCOUNTING_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396"
            ),
            args.transactions,
            args.samples,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "source_hashes_at_start"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

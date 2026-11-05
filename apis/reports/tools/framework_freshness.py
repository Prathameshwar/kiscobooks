"""Consumer freshness lower bound against signed synthetic change responses and real SQL.

This excludes owner posting, network and broker latency. A separate producer thread
maintains the offered change rate while the real guarded consumer stages and publishes.
"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import statistics
import time
from pathlib import Path

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential, authorize_snapshot, response_headers
from billing_platform.process_memory import peak_rss
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.transport import Owner
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from reports.config import Settings
from reports.metadata import service_metadata
from reports.models.core import ReportGeneration
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportGenerationRequest, ReportSourceCut
from reports.tasks.source_worker import synchronize
from tools.framework_data import facts, identity, manifest, period_number, posting_date, source
from tools.verify_mysql import database


class Feed:
    def __init__(self, tenant, company):
        self.tenant, self.company = tenant, company
        secret = SecretStr(secrets.token_hex(32))
        scopes = (CompanyServiceScope(tenant_id=tenant, company_id=company),)
        self.owner = Owner(
            origin="http://127.0.0.1", key_id="benchmark.source", secret=secret, scopes=scopes
        )
        self.credential = SnapshotCredential(secret=secret, scopes=scopes)
        self.base = manifest(1, tenant=tenant, company=company, snapshot=uuid7())
        self.initial = list(facts(1))
        self.journal = next(row for row in self.initial if row.entity == "journal")
        self.lines = [row for row in self.initial if row.entity == "journal_line"]
        self.proofs = {1: self.base}
        self.values = {str(self.base.id): self.initial}
        self.emitted = {}
        self.head = 1
        self.producer_seconds = 0.0

    def produce(self, events, rate):
        started = time.monotonic()
        for index in range(1, events + 1):
            delay = started + (index - 1) / rate - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            business_date = posting_date(index)
            journal_id = identity(7, index)
            rows = [
                source(
                    "journal",
                    journal_id,
                    self.journal.data
                    | {
                        "document_date": str(business_date),
                        "posting_date": str(business_date),
                        "posted_at": str(business_date) + "T00:00:00Z",
                        "fiscal_period_id": str(identity(5, period_number(business_date))),
                        "number": f"BENCH/{index:010}",
                        "source_id": str(journal_id),
                    },
                )
            ]
            rows += [
                source(
                    "journal_line",
                    identity(8, index * 2 + offset),
                    line.data
                    | {
                        "journal_id": str(journal_id),
                    },
                )
                for offset, line in enumerate(self.lines)
            ]
            counts = self.base.control.counts | {
                "journal": index + 1,
                "journal_line": 2 * (index + 1),
            }
            amount = f"{100 * (index + 1)}.0000"
            proof = self.base.model_copy(
                update={
                    "id": uuid7(),
                    "kind": "CHANGE",
                    "sequence": index + 1,
                    "fact_count": 3,
                    "facts_hash": hashlib.sha256(
                        b"".join(
                            canonical_json(row.model_dump(mode="json")) + b"\n" for row in rows
                        )
                    ).hexdigest(),
                    "control": self.base.control.model_copy(
                        update={
                            "counts": counts,
                            "base_totals": {"INR": {"DEBIT": amount, "CREDIT": amount}},
                        }
                    ),
                }
            )
            self.values[str(proof.id)] = rows
            self.proofs[proof.sequence] = proof
            self.emitted[proof.sequence] = time.monotonic()
            self.head = proof.sequence  # Publish only the completely built immutable response.
        self.producer_seconds = time.monotonic() - started

    def response(self, incoming):
        credential, framed, key = authorize_snapshot(
            {self.owner.key_id: self.credential},
            owner="accounting",
            requester="reports",
            tenant_id=self.tenant,
            company_id=self.company,
            headers=incoming.headers,
            method=incoming.method,
            path=incoming.url.path,
            query=incoming.url.query.decode(),
            body=incoming.content,
        )
        parts = incoming.url.path.split("/")
        if incoming.method == "POST":
            value = {
                "id": str(self.base.id),
                "status": "COMPLETE",
                "attempt": 1,
                "completed_facts": self.base.fact_count,
                "failure_code": None,
                "manifest": self.base.model_dump(mode="json"),
            }
        elif parts[-1] == "head":
            proof = self.proofs[self.head]
            value = {"sequence": proof.sequence, "manifest": proof.model_dump(mode="json")}
        elif parts[-2] == "changes":
            value = self.proofs[int(parts[-1])].model_dump(mode="json")
        elif parts[-1] == "facts":
            rows = self.values[parts[-2]]
            after = int(incoming.url.params.get("after", "0"))
            value = {
                "manifest_id": parts[-2],
                "items": [row.model_dump(mode="json") for row in rows[after : after + 200]],
                "next_after": after + 200 if after + 200 < len(rows) else None,
            }
        else:
            raise ValueError("unexpected benchmark owner route")
        body = canonical_json(value)
        return httpx.Response(
            200,
            content=body,
            headers=response_headers(
                credential,
                owner="accounting",
                requester="reports",
                key_id=key,
                request_bytes=framed,
                body=body,
            ),
        )


async def measure(server, events, rate):
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("disposable loopback MySQL server required")
    name = "reports_test_" + uuid7().hex
    await database(server, name, create=True)
    url = parsed.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    factory = create_session_factory(engine, guarded=True)
    tenant, company = uuid7(), uuid7()
    feed = Feed(tenant, company)
    settings = Settings(
        database_url=url,
        actor_signing_secret=SecretStr(secrets.token_hex(32)),
        artifact_signing_secret=SecretStr(secrets.token_hex(32)),
        source_fact_limit=100000,
    )
    publications, lags = [], []
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        with tenant_scope(tenant), httpx.MockTransport(feed.response) as transport:
            async with httpx.AsyncClient(transport=transport) as client:
                parent, sequence, producer = None, 1, None
                started = time.monotonic()
                while parent is None or sequence < events + 1:
                    if producer is not None and producer.done():
                        producer.result()  # Propagate producer failure instead of waiting forever.
                    if time.monotonic() - started > 1800:
                        raise TimeoutError("freshness probe exceeded its 30-minute budget")
                    if parent is not None and feed.head == sequence:
                        await asyncio.sleep(0.02)
                        continue
                    async with factory() as db, db.begin():
                        generation = ReportGeneration(
                            tenant_id=tenant,
                            company_id=company,
                            snapshot_id=feed.base.id if parent is None else uuid7(),
                        )
                        db.add(generation)
                        await db.flush()
                        db.add(
                            ReportGenerationRequest(
                                tenant_id=tenant,
                                company_id=company,
                                generation_id=generation.id,
                                strategy="FRESH" if parent is None else "REFRESH",
                                parent_cut_id=parent,
                            )
                        )
                    began = time.monotonic()
                    while True:
                        await synchronize(
                            factory, client, feed.owner, settings, tenant, company, generation.id
                        )
                        async with factory() as db:
                            cut = await db.scalar(
                                select(ReportSourceCut).where(
                                    ReportSourceCut.generation_id == generation.id
                                )
                            )
                            current = await db.get(ReportGeneration, generation.id)
                            if current.status == "READY":
                                break
                    finished = time.monotonic()
                    if parent is not None:
                        lags.extend(
                            finished - feed.emitted[index]
                            for index in range(sequence + 1, cut.sequence + 1)
                        )
                        record = {
                            "changes": cut.sequence - sequence,
                            "seconds": finished - began,
                            "sequence": cut.sequence,
                            "offered_sequence": feed.head,
                        }
                        publications.append(record)
                        print(json.dumps(record), flush=True)
                    parent, sequence = cut.id, cut.sequence
                    if producer is None:
                        started = time.monotonic()
                        producer = asyncio.create_task(
                            asyncio.to_thread(feed.produce, events, rate)
                        )
                    elif sequence < events + 1:
                        await asyncio.sleep(2)  # Production scope polling interval.
                await producer
                async with factory() as db:
                    count = await db.scalar(select(func.count(ReportPostedLine.id)))
                    assert count == 2 * (events + 1)
                elapsed = time.monotonic() - started
        return {
            "boundary": (
                "signed synthetic feed responses to real guarded MySQL READY cuts; "
                "excludes owner posting/network/broker"
            ),
            "offered_changes_per_second": rate,
            "changes": events,
            "producer_seconds": feed.producer_seconds,
            "drain_seconds": elapsed,
            "freshness_seconds": {
                "median": statistics.median(lags),
                "p95": sorted(lags)[max(0, int(len(lags) * 0.95) - 1)],
                "max": max(lags),
            },
            "publications": publications,
            "verified_posted_lines": count,
            "peak_rss_bytes": peak_rss(),
        }
    finally:
        await engine.dispose()
        await database(server, name, create=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=250)
    parser.add_argument("--rate", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.events <= 5000 or not 1 <= args.rate <= 100 or args.events / args.rate > 120:
        parser.error("bounded fixture requires at most 5000 changes over at most 120 seconds")
    server = os.environ.get("REPORTS_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    result = asyncio.run(measure(server, args.events, args.rate))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

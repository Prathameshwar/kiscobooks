import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import SnapshotCredential, authorize_snapshot, response_headers
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr
from reporting_contract.contract import Fact, digest
from reporting_contract.transport import Owner
from sqlalchemy import select
from test_source_versions import change_manifest

from reports.models.core import ReportGeneration
from reports.models.source_versions import ReportSourceCut
from reports.queries.source_versions import SourceView
from reports.tasks.source_worker import synchronize
from tools.framework_data import facts, manifest


class Source:
    def __init__(self):
        secret = SecretStr(secrets.token_hex(32))
        scopes = (CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),)
        self.owner = Owner(
            origin="http://127.0.0.1", key_id="test.source", secret=secret, scopes=scopes
        )
        self.credential = SnapshotCredential(secret=secret, scopes=scopes)
        self.values = list(facts(10))
        self.snapshots = {}
        self.changed = None
        self.waiting = True
        self.bad_head = False
        self.page_size = 17
        self.page_positions = []
        self.failure = None

    def advance(self):
        value = next(row for row in self.values if row.entity == "account").model_dump(mode="json")
        value["data"] = value["data"] | {"name": "Refreshed name"}
        value["content_hash"] = digest(
            {key: data for key, data in value.items() if key != "content_hash"}
        )
        self.changed = Fact.model_validate(value)
        proof = next(iter(self.snapshots.values()))
        self.change = change_manifest(proof, [self.changed], proof.sequence + 1)

    def response(self, incoming):
        credential, framed, key = authorize_snapshot(
            {self.owner.key_id: self.credential},
            owner="accounting",
            requester="reports",
            tenant_id=TENANT,
            company_id=COMPANY,
            headers=incoming.headers,
            method=incoming.method,
            path=incoming.url.path,
            query=incoming.url.query.decode(),
            body=incoming.content,
        )
        parts = incoming.url.path.split("/")
        if incoming.method == "POST":
            identity = uuid.UUID(parts[-1])
            proof = self.snapshots.setdefault(
                identity, manifest(10, tenant=TENANT, company=COMPANY, snapshot=identity)
            )
            value = {
                "id": str(identity),
                "status": "QUEUED" if self.waiting else "COMPLETE",
                "attempt": 1,
                "completed_facts": 0 if self.waiting else len(self.values),
                "manifest": None if self.waiting else proof.model_dump(mode="json"),
                "failure_code": None,
            }
            if self.failure is not None:
                value.update(
                    status="FAILED",
                    attempt=self.failure[0],
                    failure_code=self.failure[1],
                    manifest=None,
                    completed_facts=0,
                )
        elif parts[-1] == "head":
            proof = next(iter(self.snapshots.values()))
            if self.changed:
                proof = self.change
            value = {"sequence": proof.sequence, "manifest": proof.model_dump(mode="json")}
            if self.bad_head:
                value["manifest"]["control"]["base_totals"]["INR"]["DEBIT"] = "999.0000"
        elif parts[-2] == "changes":
            value = self.change.model_dump(mode="json")
        elif parts[-1] == "facts":
            identity = uuid.UUID(parts[-2])
            values = self.values if parts[-3] == "snapshots" else [self.changed]
            after = int(incoming.url.params.get("after", "0"))
            self.page_positions.append(after)
            items = values[after : after + self.page_size]
            value = {
                "manifest_id": str(identity),
                "items": [row.model_dump(mode="json") for row in items],
                "next_after": after + len(items) if after + len(items) < len(values) else None,
            }
        else:
            raise AssertionError("unexpected owner route")
        encoded = canonical_json(value)
        return httpx.Response(
            200,
            content=encoded,
            headers=response_headers(
                credential,
                owner="accounting",
                requester="reports",
                key_id=key,
                request_bytes=framed,
                body=encoded,
            ),
        )


async def submit(app, client, body):
    path = f"/v2/companies/{COMPANY}/report-generations"
    auth = headers()
    first = await client.post(path, headers=auth, json=body)
    assert first.status_code == 202, first.text
    again = await client.post(path, headers=auth, json=body)
    assert again.json()["id"] == first.json()["id"]
    return uuid.UUID(first.json()["id"])


@pytest.mark.parametrize(
    "attempt,code,retryable",
    [
        (1, "SNAPSHOT_INTERRUPTED", True),
        (3, "SNAPSHOT_INTERRUPTED", False),
        (1, "SNAPSHOT_CAPACITY_OR_VERIFICATION", False),
    ],
)
async def test_source_waits_for_retryable_owner_attempts(app, client, attempt, code, retryable):
    source = Source()
    source.failure = attempt, code
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    identity = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:

        async def process():
            await synchronize(
                app.state.session_factory,
                wire,
                source.owner,
                app.state.settings,
                TENANT,
                COMPANY,
                identity,
            )

        if retryable:
            await process()
            source.failure, source.waiting = None, False
            await process()
            with tenant_scope(TENANT):
                async with app.state.session_factory() as db:
                    assert (await db.get(ReportGeneration, identity)).status == "READY"
        else:
            with pytest.raises(ConflictError, match="owner snapshot failed"):
                await process()


async def test_signed_source_pipeline_refresh_and_compaction_keep_old_cutoffs(app, client):
    source = Source()
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    first = await submit(app, client, {})
    ids = [first]
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:

        async def process(identity):
            await synchronize(
                app.state.session_factory,
                wire,
                source.owner,
                app.state.settings,
                TENANT,
                COMPANY,
                identity,
            )

        await process(first)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                assert (await db.get(ReportGeneration, first)).status == "PENDING"
        source.waiting = False
        await process(first)
        await process(first)
        source.advance()
        refreshed = await submit(
            app, client, {"strategy": "REFRESH", "base_generation_id": str(first)}
        )
        await process(refreshed)
        ids.append(refreshed)
        compacted = await submit(
            app, client, {"strategy": "COMPACT", "base_generation_id": str(refreshed)}
        )
        await process(compacted)
        ids.append(compacted)
    account = next(row for row in source.values if row.entity == "account")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            epochs = []
            for index, identity in enumerate(ids):
                generation = await db.get(ReportGeneration, identity)
                assert generation.status == "READY"
                cut = await db.scalar(
                    select(ReportSourceCut).where(ReportSourceCut.generation_id == identity)
                )
                assert cut.verification["differences"] == []
                epochs.append(cut.epoch_id)
                view = SourceView(COMPANY, cut.epoch_id, cut.sequence)
                row = (await view.lookup(db, "account", [account.source_id]))[account.source_id]
                assert row.data["name"] == (
                    account.data["name"] if index == 0 else "Refreshed name"
                )
            assert epochs[0] == epochs[1] and epochs[2] != epochs[1]


async def test_source_generation_routes_enforce_scope_and_strict_inputs(app, client):
    source = Source()
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    identity = await submit(app, client, {})
    path = f"/v2/companies/{COMPANY}/report-generations"
    assert (await client.get(path + "/" + str(identity))).status_code == 401
    assert (
        await client.get(path + "/" + str(identity), headers=headers(permissions=frozenset()))
    ).status_code == 403
    other = uuid.uuid4()
    assert (
        await client.get(
            path.replace(str(COMPANY), str(other)) + "/" + str(identity),
            headers=headers(company=other),
        )
    ).status_code == 403
    for body in (
        {"strategy": "REFRESH"},
        {"unsafe": True},
        {"strategy": "FRESH", "base_generation_id": str(identity)},
    ):
        assert (await client.post(path, headers=headers(), json=body)).status_code == 422
    assert (await client.post(path, headers=headers(), json={})).status_code == 409


async def test_source_barrier_controls_must_match_the_published_cut(app, client):
    source = Source()
    source.waiting, source.bad_head = False, True
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    identity = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:
        with pytest.raises(ConflictError, match="barrier"):
            await synchronize(
                app.state.session_factory,
                wire,
                source.owner,
                app.state.settings,
                TENANT,
                COMPANY,
                identity,
            )


async def test_failed_refresh_queues_one_fresh_rebuild(app, client):
    from reports.models.source_versions import ReportGenerationRequest
    from reports.tasks.source_worker import cycle

    source = Source()
    source.waiting = False
    settings = app.state.settings
    settings.source_versions_enabled = True
    settings.owners = (source.owner,)
    first = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:
        await cycle(settings, app.state.session_factory, wire)
        source.advance()
        source.bad_head = True
        refresh = await submit(
            app, client, {"strategy": "REFRESH", "base_generation_id": str(first)}
        )
        await cycle(settings, app.state.session_factory, wire)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.get(ReportGeneration, refresh)).status == "QUARANTINED"
            requests = list(await db.scalars(select(ReportGenerationRequest)))
            assert [row.strategy for row in requests] == ["FRESH", "REFRESH", "FRESH"]


async def test_source_copy_yields_after_ten_pages_and_resumes_its_ordinal(app, client):
    source = Source()
    source.waiting, source.page_size = False, 1
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    identity = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:
        for turn in range(7):
            await synchronize(
                app.state.session_factory,
                wire,
                source.owner,
                app.state.settings,
                TENANT,
                COMPANY,
                identity,
            )
            with tenant_scope(TENANT):
                async with app.state.session_factory() as db:
                    row = await db.get(ReportGeneration, identity)
                    assert row.status == ("READY" if turn == 6 else "BUILDING")
    assert source.page_positions == list(range(len(source.values)))


async def test_compaction_resumes_when_memory_page_boundaries_change(app, client, monkeypatch):
    from reports.models.source_versions import ReportFactVersion, ReportSourceCut
    from reports.queries import source_versions as queries

    source = Source()
    source.waiting = False
    app.state.settings.source_versions_enabled = True
    app.state.settings.owners = (source.owner,)
    first = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:

        async def process(identity):
            await synchronize(
                app.state.session_factory,
                wire,
                source.owner,
                app.state.settings,
                TENANT,
                COMPANY,
                identity,
            )

        await process(first)
        compacted = await submit(
            app, client, {"strategy": "COMPACT", "base_generation_id": str(first)}
        )
        monkeypatch.setattr(queries, "PAGE_BYTES", 1500)
        await process(compacted)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                assert (await db.get(ReportGeneration, compacted)).status == "BUILDING"
                parent = await db.scalar(
                    select(ReportSourceCut).where(ReportSourceCut.generation_id == first)
                )
                copied = set(
                    (
                        await db.execute(
                            select(ReportFactVersion.entity, ReportFactVersion.source_id).where(
                                ReportFactVersion.epoch_id != parent.epoch_id
                            )
                        )
                    ).tuples()
                )
        original_pages = queries.SourceView.pages

        async def without_revisiting_copied_rows(view, db, entity, **options):
            async for rows in original_pages(view, db, entity, **options):
                if view.epoch == parent.epoch_id:
                    assert (
                        not {(row.entity, row.source_id) for row in rows} & copied
                    ), "compaction revisited already copied records"
                yield rows

        monkeypatch.setattr(queries.SourceView, "pages", without_revisiting_copied_rows)
        monkeypatch.setattr(queries, "PAGE_BYTES", 4000)
        for _ in range(5):
            await process(compacted)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                assert (await db.get(ReportGeneration, compacted)).status == "READY"


async def test_versioned_source_runs_through_bounded_reference_adapter(
    app, client, prefix, monkeypatch
):
    from test_framework_execution import proof

    from reports.tasks.framework_worker import process as process_run

    source = Source()
    source.waiting = False
    app.state.settings.source_versions_enabled = app.state.settings.framework_enabled = True
    app.state.settings.owners = (source.owner,)
    identity = await submit(app, client, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(source.response)) as wire:
        await synchronize(
            app.state.session_factory,
            wire,
            source.owner,
            app.state.settings,
            TENANT,
            COMPANY,
            identity,
        )
        source.advance()
        refreshed = await submit(
            app, client, {"strategy": "REFRESH", "base_generation_id": str(identity)}
        )
        await synchronize(
            app.state.session_factory,
            wire,
            source.owner,
            app.state.settings,
            TENANT,
            COMPANY,
            refreshed,
        )
    path = f"/v2/companies/{COMPANY}/report-runs"
    body = {"code": "SOURCE_RECONCILIATION", "generation_id": str(refreshed)}
    accepted = await client.post(path, headers=headers(), json=body)
    assert accepted.status_code == 202, accepted.text
    run_id = uuid.UUID(accepted.json()["id"])

    async def authority(job):
        return proof(job)

    await process_run(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, run_id, authority
    )
    result = await client.get(path + "/" + str(run_id), headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    assert result.json()["result"]["evidence"]["counts"]["journal_line"] == 20
    # A one-fact change still represents the whole 63-fact source, not a one-fact dataset.
    app.state.settings.reference_fact_limit = 20
    denied = await client.post(path, headers=headers(), json=body)
    assert denied.status_code == 409, denied.text

    from reports.models.core import ReportRun
    from reports.tasks import runs
    from reports.tasks.common import get

    legacy = await client.post(
        prefix + "/report-runs", headers=headers(), json={"generation_id": str(refreshed)}
    )
    assert legacy.status_code == 202, legacy.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await runs.complete(
                db, await get(db, COMPANY, ReportRun, uuid.UUID(legacy.json()["id"]))
            )
    retained = await client.get(prefix + "/report-runs/" + legacy.json()["id"], headers=headers())
    assert retained.json()["status"] == "COMPLETE"
    assert retained.json()["evidence"]["base_totals"]["INR"]["DEBIT"] == "1000.0000"
    monkeypatch.setattr("reports.api.routes.LEGACY_FACT_LIMIT", 20)
    rejected = await client.post(
        prefix + "/report-runs", headers=headers(), json={"generation_id": str(refreshed)}
    )
    assert rejected.status_code == 409

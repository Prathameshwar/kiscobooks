"""Fault-injection tests at transaction, retry and tenant boundaries."""

import base64
import datetime as dt
import json
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.bulk import BulkRecord, resolve_references
from billing_platform.bulk_files import Cell
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.import_contracts import (
    CONTROLS,
    CommitImport,
    DownloadOptions,
    ImportAction,
    ImportBatch,
    ReviseImport,
    SourceFile,
    StageImport,
    TemplateRequest,
)
from billing_platform.import_engine import command, issues, revision, scoped_job
from billing_platform.import_files import (
    cell_value,
    decode_files,
    document,
    exact_json,
    schema_kinds,
    template_document,
)
from billing_platform.import_models import (
    IMPORT_MODELS,
    ImportArtifact,
    ImportChangeSetEffect,
    ImportJobAttempt,
)
from billing_platform.import_reads import download, history, record_history
from tests.models import TenantThing


class ThingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=50)
    parent: str | None = None


class Adapter:
    def __init__(self, tenant: uuid.UUID) -> None:
        self.namespace = "example"
        self.definitions = {"things": "Example domain"}
        self.actor = Actor(tenant_id=tenant, user_id=uuid7(), grants=())
        self.company = uuid7()
        self.failing: set[str] = set()
        self.denied = False
        self.context = "unchanged"

    async def authorize(self, db: AsyncSession, *, write: bool) -> None:
        if self.denied:
            raise PermissionDeniedError("denied")

    async def lock(self, db: AsyncSession) -> None:
        pass

    async def snapshot(
        self, db: AsyncSession, definition: str, parameters: dict[str, str]
    ) -> dict[str, Any]:
        return {"schemas": {"thing:CREATE": ThingInput.model_json_schema()}, "parameters": {}}

    async def fingerprint(self, db: AsyncSession, definition: str) -> str:
        return self.context

    async def readable(self, db: AsyncSession, batch: ImportBatch) -> None:
        await self.authorize(db, write=False)

    async def execute(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
    ) -> dict[str, Any]:
        values = ThingInput.model_validate(resolve_references(record.data, results))
        if record.key in self.failing:
            raise ConflictError("injected native conflict")
        row = TenantThing(id=uuid7(), tenant_id=self.actor.tenant_id, name=values.name)
        db.add(row)
        await db.flush()
        return {"id": str(row.id)}


def file(records: list[dict[str, Any]]) -> SourceFile:
    rows = [
        [
            row["key"],
            row.get("set", row["key"]),
            "thing",
            "CREATE",
            "",
            "",
            "",
            "",
            ",".join(row.get("depends_on", [])),
            "",
            json.dumps(row["data"]),
        ]
        for row in records
    ]
    raw = document("CSV", [("Records", [*CONTROLS, "_payload"], rows)])
    return SourceFile(
        filename="source.csv", format="CSV", content_base64=base64.b64encode(raw).decode()
    )


async def invoke(
    factory: async_sessionmaker[AsyncSession],
    adapter: Adapter,
    action: str,
    body: BaseModel,
    job: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    result = await command(
        factory, adapter, action, body, key or str(uuid7()), uuid.UUID(job) if job else None
    )
    return result.value.model_dump(mode="json")


async def stage(
    factory: async_sessionmaker[AsyncSession],
    adapter: Adapter,
    records: list[dict[str, Any]],
    **options: Any,
) -> dict[str, Any]:
    template = await invoke(factory, adapter, "template", TemplateRequest(definition="things"))
    return await invoke(
        factory,
        adapter,
        "stage",
        StageImport(template_id=template["id"], files=[file(records)], **options),
    )


def row(key: str, **values: Any) -> dict[str, Any]:
    return {"key": key, "data": {"name": key}, **values}


@pytest.mark.parametrize(
    "atomicity,on_error,expected",
    [
        ("ATOMIC", "CONTINUE_INDEPENDENT", 0),
        ("CHANGE_SET", "STOP", 1),
        ("CHANGE_SET", "CONTINUE_INDEPENDENT", 2),
    ],
)
async def test_partial_failure_retry_never_reapplies_success(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    atomicity: str,
    on_error: str,
    expected: int,
) -> None:
    adapter = Adapter(tenant_a)
    job = await stage(
        factory, adapter, [row("a"), row("b"), row("c")], atomicity=atomicity, on_error=on_error
    )
    ready = await invoke(factory, adapter, "validate", ImportAction(expected_version=1), job["id"])
    assert ready["state"] == "READY"
    adapter.failing = {"b"}
    failed = await invoke(
        factory,
        adapter,
        "commit",
        CommitImport(expected_version=ready["row_version"], review_digest=ready["review_digest"]),
        job["id"],
    )
    assert failed["completed_count"] == expected
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == expected
    adapter.failing.clear()
    retried = await invoke(
        factory, adapter, "retry", ImportAction(expected_version=failed["row_version"]), job["id"]
    )
    assert retried["state"] == "READY"
    final = await invoke(
        factory,
        adapter,
        "commit",
        CommitImport(
            expected_version=retried["row_version"], review_digest=retried["review_digest"]
        ),
        job["id"],
    )
    assert final["state"] == "SUCCEEDED" and final["completed_count"] == 3
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == 3
            assert await db.scalar(select(func.count(ImportChangeSetEffect.id))) == 3


async def test_dependencies_aggregate_rollback_revision_and_reports(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    records = [
        row("a", set="parent"),
        row("b", set="parent", data={"name": "b", "parent": {"$ref": "a", "field": "id"}}),
        row("c", depends_on=["a"]),
    ]
    job = await stage(factory, adapter, records)
    adapter.failing = {"b"}
    invalid = await invoke(
        factory, adapter, "validate", ImportAction(expected_version=1), job["id"]
    )
    assert invalid["state"] == "INVALID"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == 0
            for fmt in ("CSV", "TSV", "XLSX"):
                data, _ = await download(
                    db, adapter, uuid.UUID(job["id"]), DownloadOptions(format=fmt)
                )
                assert data
            records_page = await record_history(
                db, adapter, uuid.UUID(job["id"]), b"x" * 32, limit=1
            )
            assert records_page["page"]["has_more"]
            assert (
                len(
                    (
                        await record_history(
                            db,
                            adapter,
                            uuid.UUID(job["id"]),
                            b"x" * 32,
                            cursor=records_page["page"]["next_cursor"],
                            limit=1,
                        )
                    )["items"]
                )
                == 1
            )
    adapter.failing.clear()
    revised = await invoke(
        factory,
        adapter,
        "revise",
        ReviseImport(expected_version=invalid["row_version"], files=[file(records)]),
        job["id"],
    )
    ready = await invoke(
        factory,
        adapter,
        "validate",
        ImportAction(expected_version=revised["row_version"]),
        job["id"],
    )
    applied = await invoke(
        factory,
        adapter,
        "commit",
        CommitImport(expected_version=ready["row_version"], review_digest=ready["review_digest"]),
        job["id"],
    )
    assert applied["state"] == "SUCCEEDED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in IMPORT_MODELS:
                assert await db.scalar(select(func.count(model.id))) > 0, model
            page = await history(db, adapter, b"x" * 32, kind="jobs", limit=1)
            assert page["items"][0]["id"] == job["id"]
    with tenant_scope(uuid7()):
        async with factory() as db:
            for model in IMPORT_MODELS:
                assert await db.scalar(select(func.count(model.id))) == 0, model


async def test_guards_expiry_cancel_replay_and_drift(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    job = await stage(factory, adapter, [row("a")])
    with pytest.raises(ConflictError):
        await invoke(factory, adapter, "validate", ImportAction(expected_version=999), job["id"])
    ready = await invoke(factory, adapter, "validate", ImportAction(expected_version=1), job["id"])
    with pytest.raises(ConflictError):
        await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(expected_version=ready["row_version"], review_digest="0" * 64),
            job["id"],
        )
    adapter.context = "changed"
    with pytest.raises(ConflictError):
        await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(
                expected_version=ready["row_version"], review_digest=ready["review_digest"]
            ),
            job["id"],
        )
    cancelled = await invoke(
        factory, adapter, "cancel", ImportAction(expected_version=ready["row_version"]), job["id"]
    )
    with pytest.raises(ConflictError):
        await invoke(
            factory,
            adapter,
            "retry",
            ImportAction(expected_version=cancelled["row_version"]),
            job["id"],
        )
    adapter.denied = True
    with pytest.raises(PermissionDeniedError):
        await invoke(factory, adapter, "validate", ImportAction(expected_version=1), job["id"])


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":1.23}', '{"a":NaN}'])
def test_exact_json_rejects_ambiguous_or_inexact_numbers(raw: str) -> None:
    with pytest.raises(ValueError):
        exact_json(raw)


def test_file_validation_uses_the_same_schema_and_limits() -> None:
    snapshot = {"schemas": {"thing:CREATE": ThingInput.model_json_schema()}}
    options = {"mode": "CREATE_ONLY", "atomicity": "CHANGE_SET", "on_error": "STOP"}
    source = file([row("a")])
    batch, sources, locations = decode_files([source], snapshot, options)
    assert batch.records[0].data == {"name": "a"} and sources and locations["a"] == "source.csv"
    with pytest.raises(ValueError):
        decode_files([source, source], snapshot, options)
    with pytest.raises(ValueError):
        decode_files([file([row(str(index)) for index in range(201)])], snapshot, options)
    for fmt in ("CSV", "TSV", "XLSX"):
        assert template_document(snapshot, "thing", "CREATE", fmt)
    assert issues(ValueError())[0]["code"] == "invalid_record"
    assert issues(PermissionDeniedError("private"))[0]["code"] == "permission_denied"


async def test_all_history_and_downloads_are_owned_and_round_trip(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    first = await stage(factory, adapter, [row("one", data={"name": ""})])
    await invoke(factory, adapter, "validate", ImportAction(expected_version=1), first["id"])
    second = await stage(factory, adapter, [row("two")])
    secret = b"k" * 32
    with tenant_scope(tenant_a):
        async with factory() as db:
            job = await scoped_job(db, adapter, uuid.UUID(first["id"]))
            for kind in ("jobs", "attempts", "artifacts", "revisions"):
                page = await history(db, adapter, secret, kind=kind, job_id=job.id, limit=1)
                assert page["items"]
                if page["page"]["next_cursor"]:
                    assert (
                        await history(
                            db,
                            adapter,
                            secret,
                            kind=kind,
                            job_id=job.id,
                            limit=1,
                            cursor=page["page"]["next_cursor"],
                        )
                    )["items"]
            attempt = await db.scalar(
                select(ImportJobAttempt).where(
                    ImportJobAttempt.revision_id == (await revision(db, job)).id
                )
            )
            assert attempt is not None
            entries = await record_history(db, adapter, job.id, secret, attempt_id=attempt.id)
            assert entries["items"][0]["field"] == "name"
            with pytest.raises(ValidationFailedError):
                await history(db, adapter, secret, kind="jobs", cursor="bad")
            with pytest.raises(ValidationFailedError):
                await record_history(db, adapter, job.id, secret, cursor="bad")
            with pytest.raises(PermissionDeniedError):
                await record_history(
                    db, adapter, uuid.UUID(second["id"]), secret, attempt_id=attempt.id
                )
            for kind in ("NORMALIZED", "CORRECTION"):
                for fmt in ("CSV", "TSV", "XLSX"):
                    raw, filename = await download(
                        db, adapter, job.id, DownloadOptions(kind=kind, format=fmt)
                    )
                    snapshot = await adapter.snapshot(db, "things", {})
                    batch, _, _ = decode_files(
                        [
                            SourceFile(
                                filename=filename,
                                format=fmt,
                                content_base64=base64.b64encode(raw).decode(),
                            )
                        ],
                        snapshot,
                        {"mode": "CREATE_ONLY", "on_error": "STOP", "atomicity": "CHANGE_SET"},
                    )
                    assert batch.records[0].data["name"] == ""
            artifact = await db.scalar(
                select(ImportArtifact).where(ImportArtifact.revision_id == attempt.revision_id)
            )
            assert artifact is not None
            raw, _ = await download(
                db, adapter, job.id, DownloadOptions(kind="SOURCE", artifact_id=artifact.id)
            )
            assert raw == base64.b64decode(file([row("one", data={"name": ""})]).content_base64)
            with pytest.raises(ValidationFailedError):
                await download(db, adapter, job.id, DownloadOptions(kind="SOURCE"))
            with pytest.raises(PermissionDeniedError):
                await download(
                    db,
                    adapter,
                    uuid.UUID(second["id"]),
                    DownloadOptions(kind="SOURCE", artifact_id=artifact.id),
                )
            with pytest.raises(ValidationFailedError):
                await download(db, adapter, uuid.UUID(second["id"]), DownloadOptions())


async def test_successful_effects_are_immutable_across_revisions(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    records = [row("a"), row("b")]
    job = await stage(factory, adapter, records)
    ready = await invoke(factory, adapter, "validate", ImportAction(expected_version=1), job["id"])
    adapter.failing = {"b"}
    partial = await invoke(
        factory,
        adapter,
        "commit",
        CommitImport(expected_version=ready["row_version"], review_digest=ready["review_digest"]),
        job["id"],
    )
    assert partial["state"] == "PARTIAL"
    for changed in ([row("b")], [row("a", data={"name": "edited"}), row("b")]):
        with pytest.raises(ConflictError):
            await invoke(
                factory,
                adapter,
                "revise",
                ReviseImport(expected_version=partial["row_version"], files=[file(changed)]),
                job["id"],
            )
    revised = await invoke(
        factory,
        adapter,
        "revise",
        ReviseImport(
            expected_version=partial["row_version"],
            files=[file([row("a"), row("b", data={"name": "corrected"})])],
        ),
        job["id"],
    )
    adapter.failing.clear()
    ready = await invoke(
        factory,
        adapter,
        "validate",
        ImportAction(expected_version=revised["row_version"]),
        job["id"],
    )
    final = await invoke(
        factory,
        adapter,
        "commit",
        CommitImport(expected_version=ready["row_version"], review_digest=ready["review_digest"]),
        job["id"],
    )
    assert final["state"] == "SUCCEEDED"
    for action, body in (
        ("validate", ImportAction(expected_version=final["row_version"])),
        ("cancel", ImportAction(expected_version=final["row_version"])),
        ("revise", ReviseImport(expected_version=final["row_version"], files=[file(records)])),
    ):
        with pytest.raises(ConflictError):
            await invoke(factory, adapter, action, body, job["id"])


async def test_expired_payloads_and_cross_actor_templates_fail_closed(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    template = await invoke(factory, adapter, "template", TemplateRequest(definition="things"))
    other = Adapter(tenant_a)
    other.company = adapter.company
    with pytest.raises(PermissionDeniedError):
        await invoke(
            factory,
            other,
            "stage",
            StageImport(template_id=template["id"], files=[file([row("one")])]),
        )
    job = await stage(factory, adapter, [row("one")])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            saved = await scoped_job(db, adapter, uuid.UUID(job["id"]))
            saved.expires_at = utcnow() - dt.timedelta(days=1)
        async with factory() as db:
            with pytest.raises(ConflictError):
                await download(
                    db, adapter, uuid.UUID(job["id"]), DownloadOptions(kind="NORMALIZED")
                )
    with pytest.raises(ConflictError):
        await invoke(factory, adapter, "validate", ImportAction(expected_version=1), job["id"])


def test_native_file_cells_preserve_identifiers_decimals_and_typed_values() -> None:
    assert cell_value(Cell("000123"), {"type": "string"}, {}) == "000123"
    assert cell_value(Cell("123.4500"), {"type": "string"}, {}) == "123.4500"
    assert cell_value(Cell("-3", "n"), {"type": "integer"}, {}) == -3
    for cell, expected in (
        (Cell("1", "b"), True),
        (Cell("0", "b"), False),
        (Cell("true"), True),
        (Cell("false"), False),
    ):
        assert cell_value(cell, {"type": "boolean"}, {}) is expected
    assert cell_value(Cell('["0001"]'), {"type": "array"}, {}) == ["0001"]
    assert cell_value(Cell('{"amount":"1.2345"}'), {"type": "object"}, {}) == {"amount": "1.2345"}
    assert (
        cell_value(Cell('{"$ref":"parent","field":"id"}'), {"type": "string"}, {})["$ref"]
        == "parent"
    )
    with pytest.raises(ValueError):
        cell_value(Cell("123", "n"), {"type": "string"}, {})
    assert schema_kinds(
        {"anyOf": [{"$ref": "#/$defs/Text"}, {"type": "null"}]}, {"Text": {"type": "string"}}
    ) == {"string", "null"}
    assert schema_kinds({}, {}) == set()
    with pytest.raises(ValueError):
        schema_kinds({"$ref": "#/$defs/Loop"}, {"Loop": {"$ref": "#/$defs/Loop"}})
    with pytest.raises(ValueError):
        document("TSV", [("one", [], []), ("two", [], [])])


@pytest.mark.parametrize(
    "extra,payload,value",
    [
        ("unknown", "{}", "x"),
        ("name", '{"name":"one"}', "duplicate"),
        ("_payload", "[]", ""),
        ("name", "{}", "WRONG"),
    ],
)
def test_file_columns_cannot_override_payload_or_template_options(
    extra: str, payload: str, value: str
) -> None:
    snapshot = {
        "schemas": {"thing:CREATE": {"properties": {"name": {"type": "string", "enum": ["one"]}}}}
    }
    if extra == "_payload":
        columns, values = (
            ["_key", "_set", "_resource", "_payload"],
            ["one", "one", "thing", payload],
        )
    else:
        columns, values = (
            ["_key", "_set", "_resource", "_payload", extra],
            ["one", "one", "thing", payload, value],
        )
    raw = document("CSV", [("Records", columns, [values])])
    source = SourceFile(
        filename="invalid.csv", format="CSV", content_base64=base64.b64encode(raw).decode()
    )
    with pytest.raises(ValueError):
        decode_files(
            [source],
            snapshot,
            {"mode": "CREATE_ONLY", "on_error": "STOP", "atomicity": "CHANGE_SET"},
        )


def test_combined_file_budget_is_enforced_before_decoding_the_next_file() -> None:
    huge = SourceFile(
        filename="oversize.tsv",
        format="TSV",
        content_base64=base64.b64encode(b"x" * (8 * 1024 * 1024)).decode(),
    )
    with pytest.raises(ValueError, match="combined source files"):
        decode_files(
            [file([row("one")]), huge],
            {"schemas": {"thing:CREATE": ThingInput.model_json_schema()}},
            {"mode": "CREATE_ONLY", "on_error": "STOP", "atomicity": "CHANGE_SET"},
        )

"""Current-authority import history and short-lived private downloads."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.bulk import MAX_BYTES
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.import_contracts import CONTROLS, DownloadOptions, ImportBatch
from billing_platform.import_engine import (
    ImportAdapter,
    action_hash,
    effects,
    evidence,
    groups,
    revision,
    scoped_job,
)
from billing_platform.import_files import document
from billing_platform.import_models import (
    ImportArtifact,
    ImportChangeSet,
    ImportJob,
    ImportJobAttempt,
    ImportJobRecord,
    ImportJobRevision,
    ImportRecordIssue,
    ImportRecordResult,
    ImportTemplateSnapshot,
)
from billing_platform.pagination import CursorCodec


def codec(secret: bytes, adapter: ImportAdapter, context: str) -> CursorCodec:
    return CursorCodec(
        secret,
        context=f"imports:{adapter.namespace}:{adapter.actor.tenant_id}:{adapter.company}:{adapter.actor.user_id}:{context}",
        ttl_seconds=300,
    )


async def history(
    db: AsyncSession,
    adapter: ImportAdapter,
    secret: bytes,
    *,
    kind: str,
    job_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    await adapter.authorize(db, write=False)
    if kind == "jobs":
        model: Any = ImportJob
        columns: tuple[str, ...] = (
            "id",
            "definition",
            "state",
            "revision",
            "row_version",
            "record_count",
            "completed_count",
            "created_at",
            "expires_at",
        )
        statement = select(*(getattr(model, key) for key in columns)).where(
            model.company_id == adapter.company, model.actor_user_id == adapter.actor.user_id
        )
    else:
        assert job_id is not None
        job = await scoped_job(db, adapter, job_id)
        revs = select(ImportJobRevision.id).where(
            ImportJobRevision.company_id == adapter.company, ImportJobRevision.job_id == job.id
        )
        if kind == "attempts":
            model = ImportJobAttempt
            columns = ("id", "revision_id", "phase", "outcome", "created_at", "finished_at")
            statement = select(*(getattr(model, key) for key in columns)).where(
                model.company_id == adapter.company, model.revision_id.in_(revs)
            )
        elif kind == "artifacts":
            model = ImportArtifact
            columns = (
                "id",
                "revision_id",
                "filename",
                "format",
                "byte_count",
                "content_sha256",
                "expires_at",
            )
            statement = select(*(getattr(model, key) for key in columns)).where(
                model.company_id == adapter.company, model.revision_id.in_(revs)
            )
        elif kind == "revisions":
            model = ImportJobRevision
            columns = ("id", "revision", "input_hash", "created_at")
            statement = select(*(getattr(model, key) for key in columns)).where(
                model.company_id == adapter.company, model.job_id == job.id
            )
        else:
            raise ValueError("unknown history kind")
    signed = codec(secret, adapter, f"history:{kind}:{job_id}:{limit}")
    if cursor:
        try:
            statement = statement.where(model.id > uuid.UUID(signed.decode(cursor)["id"]))
        except (ValueError, KeyError) as exc:
            raise ValidationFailedError("invalid history cursor") from exc
    values = list((await db.execute(statement.order_by(model.id).limit(limit + 1))).mappings())
    result = [
        {
            key: value.isoformat()
            if hasattr(value, "isoformat")
            else str(value)
            if isinstance(value, uuid.UUID)
            else value
            for key, value in row.items()
        }
        for row in values[:limit]
    ]
    return {
        "items": result,
        "page": {
            "limit": limit,
            "has_more": len(values) > limit,
            "next_cursor": signed.encode({"id": str(values[limit - 1]["id"])})
            if len(values) > limit
            else None,
        },
    }


async def download(
    db: AsyncSession, adapter: ImportAdapter, job_id: uuid.UUID, options: DownloadOptions
) -> tuple[bytes, str]:
    job = await scoped_job(db, adapter, job_id)
    attempt = None
    if options.kind == "RESULT" and options.attempt_id is not None:
        attempt = await company_object(
            db, ImportJobAttempt, options.attempt_id, company_id=adapter.company
        )
        rev = await company_object(
            db, ImportJobRevision, attempt.revision_id, company_id=adapter.company
        )
        if rev.job_id != job.id:
            raise PermissionDeniedError("attempt belongs to another import")
        if options.revision is not None and options.revision != rev.revision:
            raise ValidationFailedError("attempt belongs to a different file revision")
    else:
        rev = await revision(db, job, options.revision)
    if rev.batch is None or job.expires_at <= utcnow():
        raise ConflictError("import payload expired; history remains available")
    batch = ImportBatch.model_validate(rev.batch)
    await adapter.readable(db, batch)
    template = await company_object(
        db, ImportTemplateSnapshot, job.template_id, company_id=adapter.company
    )
    snapshot = template.snapshot or {}
    tabular = snapshot.get("tabular")
    if options.kind == "SOURCE":
        if options.artifact_id is None:
            raise ValidationFailedError("source download requires artifact_id")
        artifact = await company_object(
            db, ImportArtifact, options.artifact_id, company_id=adapter.company
        )
        if artifact.revision_id != rev.id:
            raise PermissionDeniedError("artifact belongs to another revision")
        await db.refresh(artifact, attribute_names=["content"])
        if artifact.expires_at <= utcnow() or artifact.content is None:
            raise ConflictError("source artifact expired")
        result, filename = artifact.content, artifact.filename
    elif options.kind in {"NORMALIZED", "CORRECTION"}:
        completed: set[str] = set()
        if options.kind == "CORRECTION":
            # Keep successful parents: retry/revision uses immutable effects to skip
            # them and resolves child references from the original successful IDs.
            # Removing parents would make a standalone correction file unusable.
            completed = set()
        rows = []
        for row in batch.records:
            if row.key in completed:
                continue
            controls = [
                row.key,
                row.change_set,
                row.resource,
                row.action,
                str(row.target.id or ""),
                row.target.code or "",
                row.target.record or "",
                row.target.field if row.target.record else "",
                ",".join(row.depends_on),
                ",".join(row.clear_fields),
            ]
            rows.append(
                [*controls, json.dumps(row.data, ensure_ascii=False, separators=(",", ":"))]
            )
        headers = [*CONTROLS, "_payload"]
        if tabular:
            schema = snapshot["schemas"][tabular["resource"] + ":" + tabular["action"]]
            headers = ["_key", *schema["properties"]]
            rows = [
                [
                    row.key,
                    *[
                        json.dumps(row.data[key], ensure_ascii=False, separators=(",", ":"))
                        if isinstance(row.data.get(key), dict | list)
                        else ""
                        if row.data.get(key) is None
                        else str(row.data[key])
                        for key in headers[1:]
                    ],
                ]
                for row in batch.records
            ]
        result = await asyncio.to_thread(document, options.format, [("Records", headers, rows)])
        filename = options.kind.lower() + "." + options.format.lower()
    else:
        if attempt is None:
            attempt = await db.scalar(
                select(ImportJobAttempt)
                .where(
                    ImportJobAttempt.company_id == adapter.company,
                    ImportJobAttempt.revision_id == rev.id,
                )
                .order_by(ImportJobAttempt.id.desc())
                .limit(1)
            )
        if attempt is None:
            raise ValidationFailedError("validation/import attempt is unavailable")
        stmt = (
            select(ImportJobRecord, ImportRecordResult, ImportRecordIssue)
            .join(ImportRecordResult, ImportRecordResult.record_id == ImportJobRecord.id)
            .outerjoin(ImportRecordIssue, ImportRecordIssue.result_id == ImportRecordResult.id)
            .where(
                ImportJobRecord.company_id == adapter.company,
                ImportRecordResult.attempt_id == attempt.id,
            )
            .order_by(ImportJobRecord.ordinal, ImportRecordIssue.id)
            .limit(20001)
        )
        rows = []
        result_fields = snapshot.get("result_fields", [])
        completion_fields = set(snapshot.get("completion_result_fields", []))
        result_values = {record.key: dict(record.data) for record in batch.records}
        if result_fields and attempt.phase == "IMPORT":
            original_groups = groups(batch)
            for group_key, effect in (await effects(db, job)).items():
                original = original_groups.get(group_key)
                # Failed input can be corrected under the same row key. Only
                # enrich a historical report from effects for its exact input.
                if original is not None and action_hash(original) == effect.action_hash:
                    for record_key, value in effect.results.items():
                        result_values.setdefault(record_key, {}).update(value)
        for source, outcome, issue in (await db.execute(stmt)).all():
            rows.append(
                [
                    source.source_file,
                    source.source_sheet,
                    str(source.source_row),
                    source.logical_key,
                    attempt.phase,
                    str(attempt.id),
                    outcome.status,
                    str(outcome.business_id or ""),
                    issue.field if issue else "",
                    issue.code if issue else "",
                    issue.message if issue else "",
                    *[
                        ""
                        if key in completion_fields and outcome.status != "APPLIED"
                        else str(result_values.get(source.logical_key, {}).get(key, ""))
                        for key in result_fields
                    ],
                ]
            )
        result = await asyncio.to_thread(
            document,
            options.format,
            [
                (
                    "Results",
                    [
                        "file",
                        "sheet",
                        "row",
                        "key",
                        "phase",
                        "attempt_id",
                        "status",
                        "business_id",
                        "field",
                        "code",
                        "message",
                        *[
                            snapshot.get("result_headers", {}).get(key, key)
                            for key in result_fields
                        ],
                    ],
                    rows,
                )
            ],
        )
        filename = "import-results." + options.format.lower()
    if len(result) > MAX_BYTES:
        raise ValidationFailedError("download exceeds 8 MiB")
    evidence(db, adapter, job, "export")
    return result, filename


async def record_history(
    db: AsyncSession,
    adapter: ImportAdapter,
    job_id: uuid.UUID,
    secret: bytes,
    *,
    attempt_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    job = await scoped_job(db, adapter, job_id)
    rev = await revision(db, job)
    if rev.batch is None:
        raise ConflictError("import data expired")
    await adapter.readable(db, ImportBatch.model_validate(rev.batch))
    if attempt_id:
        attempt = await company_object(db, ImportJobAttempt, attempt_id, company_id=adapter.company)
        parent = await company_object(
            db, ImportJobRevision, attempt.revision_id, company_id=adapter.company
        )
        if parent.job_id != job.id:
            raise PermissionDeniedError("attempt belongs to another import")
        # Historical issues require read permission for their historical schema too.
        if parent.batch is None:
            raise ConflictError("historical input expired")
        await adapter.readable(db, ImportBatch.model_validate(parent.batch))
        model: Any = ImportRecordIssue
        stmt = (
            select(model.id, ImportRecordResult.record_id, model.field, model.code, model.message)
            .join(ImportRecordResult, model.result_id == ImportRecordResult.id)
            .where(model.company_id == adapter.company, ImportRecordResult.attempt_id == attempt.id)
        )
    else:
        latest = (
            select(ImportJobAttempt.id)
            .where(
                ImportJobAttempt.company_id == adapter.company,
                ImportJobAttempt.revision_id == rev.id,
            )
            .order_by(ImportJobAttempt.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        model = ImportJobRecord
        stmt = (
            select(
                model.id,
                model.logical_key,
                model.resource,
                model.source_file,
                model.source_sheet,
                model.source_row,
                ImportRecordResult.status,
                ImportRecordResult.business_id,
            )
            .join(ImportChangeSet, model.change_set_id == ImportChangeSet.id)
            .outerjoin(
                ImportRecordResult,
                and_(
                    ImportRecordResult.record_id == model.id,
                    ImportRecordResult.attempt_id == latest,
                ),
            )
            .where(model.company_id == adapter.company, ImportChangeSet.revision_id == rev.id)
        )
    signed = codec(secret, adapter, f"records:{job_id}:{job.row_version}:{attempt_id}:{limit}")
    if cursor:
        try:
            stmt = stmt.where(model.id > uuid.UUID(signed.decode(cursor)["id"]))
        except (ValueError, KeyError) as exc:
            raise ValidationFailedError("invalid record cursor") from exc
    rows = list((await db.execute(stmt.order_by(model.id).limit(limit + 1))).mappings())
    return {
        "items": [
            {
                key: str(value) if isinstance(value, uuid.UUID) else value
                for key, value in row.items()
            }
            for row in rows[:limit]
        ],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": signed.encode({"id": str(rows[limit - 1]["id"])})
            if len(rows) > limit
            else None,
        },
    }

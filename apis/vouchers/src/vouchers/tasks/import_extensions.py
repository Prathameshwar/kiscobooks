"""Snapshot, correction and download adapters for the canonical voucher import job."""

import asyncio
import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

from billing_platform.bulk import selection_digest
from billing_platform.bulk_files import csv_document, xlsx_workbook
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandReceipt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.api.auth import Access
from vouchers.domain import import_kinds as kinds
from vouchers.domain import imports as rules
from vouchers.models import core as core
from vouchers.models import imports as m
from vouchers.schemas.imports import ImportDownload, ImportRevisionInput, TemplateSnapshotInput
from vouchers.tasks import import_history as journal
from vouchers.tasks import imports as run
from vouchers.tasks.common import audit, get, values
from vouchers.tasks.configuration import effective


async def snapshot(
    db: AsyncSession, current: Access, body: TemplateSnapshotInput
) -> dict[str, Any]:
    run.require(current, "import.manage", "create")
    if run.masked(current):
        raise PermissionDeniedError("template contains fields that are no longer readable")
    kind, revision = await run.import_type(db, current, body.voucher_type_id)
    shape, _ = await run.shape_for(
        db,
        current,
        revision,
        kind.kind,
        document_date=body.document_date,
        posting_date=body.posting_date,
        class_id=body.class_id,
    )
    policy, evidence = await effective(
        db,
        current,
        revision.id,
        date=body.document_date,
        posting_date=body.posting_date,
        class_id=body.class_id,
    )
    classes = list(
        await db.scalars(
            select(core.VoucherClass)
            .where(
                core.VoucherClass.company_id == current.context.company_id,
                core.VoucherClass.type_revision_id == revision.id,
            )
            .order_by(core.VoucherClass.code, core.VoucherClass.id)
            .limit(201)
        )
    )
    options = {
        "classes": {
            "items": [{"id": str(row.id), "code": row.code} for row in classes[:200]],
            "truncated": len(classes) > 200,
        },
        "master_lookup": {
            "matching": "exact active company code",
            "owner": "accounting",
            "fields": ["party_code", "account_code"],
            "validation_resolves_current_versions": True,
        },
    }
    fields = list(
        await db.scalars(
            select(core.VoucherDefinitionProjection)
            .where(
                core.VoucherDefinitionProjection.company_id == current.context.company_id,
                core.VoucherDefinitionProjection.entity_type == "vouchers.voucher",
            )
            .order_by(
                core.VoucherDefinitionProjection.field_key, core.VoucherDefinitionProjection.id
            )
            .limit(129)
        )
    )
    allowed = set(shape.names("header"))
    definitions = [row.definition for row in fields if "cf." + row.field_key in allowed]
    return {
        "parameters": body.model_dump(mode="json"),
        "kind": kind.kind,
        "type_revision_id": str(revision.id),
        "header": [asdict(c) for c in shape.header],
        "lines": [asdict(c) for c in shape.line],
        "instructions": rules.instructions(shape),
        "custom_fields": definitions,
        "options": options,
        "policy": policy.model_dump(mode="json"),
        "policy_digest": evidence["digest"],
        "review_context": await run.definition_digest(db, current),
    }


async def checked_template(
    db: AsyncSession, current: Access, template_id: uuid.UUID, type_id: uuid.UUID | None = None
) -> m.ImportTemplateSnapshot:
    run.require(current, "import.manage", "create")
    row = await get(db, current, m.ImportTemplateSnapshot, template_id)
    if row.actor_user_id != current.actor.user_id:
        raise PermissionDeniedError("template belongs to another actor")
    if row.snapshot is None or row.expires_at <= utcnow():
        raise ConflictError("import template expired")
    body = TemplateSnapshotInput.model_validate(row.snapshot["parameters"])
    if type_id is not None and type_id != body.voucher_type_id:
        raise ValidationFailedError("template belongs to another voucher type")
    if selection_digest(await snapshot(db, current, body)) != row.fingerprint:
        raise ConflictError("template configuration or authority changed; download a new template")
    return row


def template_view(row: m.ImportTemplateSnapshot) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "fingerprint": row.fingerprint,
        "expires_at": row.expires_at.isoformat(),
        "snapshot": row.snapshot,
    }


async def create_template(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    key: str,
    body: TemplateSnapshotInput,
) -> Any:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        value = await snapshot(db, current, body)
        row = m.ImportTemplateSnapshot(
            **values(current),
            actor_user_id=current.actor.user_id,
            definition="vouchers",
            fingerprint=selection_digest(value),
            snapshot=value,
            expires_at=utcnow() + run.JOB_TTL,
        )
        db.add(row)
        await db.flush()
        audit(db, current, "import_job", row.id, "template")
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return template_view(await checked_template(db, current, uuid.UUID(refs["id"])))

    return await run.job_command(
        factory,
        current,
        ("import.manage", "create"),
        "template",
        key,
        body.model_dump(mode="json"),
        mutate,
        render,
    )


def canonical_source(source: dict[str, Any]) -> dict[str, Any]:
    def cells(values: dict[str, str]) -> dict[str, str]:
        return {k: v for k, v in values.items() if v and k not in {"_row", "_sheet", "import_key"}}

    return {"header": cells(source["header"]), "lines": [cells(line) for line in source["lines"]]}


async def revise(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    key: str,
    job_id: uuid.UUID,
    body: ImportRevisionInput,
) -> Any:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        job = await run.scoped_job(db, current, job_id, lock=True)
        run.actionable(job)
        if job.revision >= journal.MAX_REVISIONS:
            raise ConflictError(
                "import revision limit reached; upload remaining vouchers as a new job"
            )
        if job.row_version != body.expected_version or job.state in {
            "VALIDATING",
            "COMMITTING",
            "CANCELLED",
        }:
            raise ConflictError("job changed or has an active attempt")
        if body.voucher_type_id != job.type_id or body.duplicate_rule != job.duplicate_rule:
            raise ValidationFailedError("correction must retain voucher type and duplicate rule")
        kind, native_revision = await run.import_type(db, current, job.type_id)
        parameters: dict[str, Any] = {}
        if body.template_id is not None:
            template = await checked_template(db, current, body.template_id, job.type_id)
            assert template.snapshot is not None
            parameters = TemplateSnapshotInput.model_validate(
                template.snapshot["parameters"]
            ).model_dump(exclude={"voucher_type_id"})
        shape, _ = await run.shape_for(db, current, native_revision, kind.kind, **parameters)
        raw, staged = await asyncio.to_thread(
            run.decode, body.format, body.content_base64, body.document, shape
        )
        existing = {
            row.import_key.casefold(): row
            for row in await run.job_rows(db, current, job.id, lock=True)
        }
        incoming = {row.import_key.casefold(): row for row in staged}
        for name, old in existing.items():
            if old.state == "CREATED" and (
                name not in incoming
                or canonical_source(old.source_input)
                != canonical_source(
                    {"header": incoming[name].header, "lines": incoming[name].lines}
                )
            ):
                raise ConflictError(
                    "successful vouchers must be retained unchanged in a correction"
                )
        await journal.revision(db, current, job)
        for name, old in existing.items():
            if name not in incoming:
                await db.delete(old)
        # New ordinals are display order; effect identity always stays the logical key.
        for item in staged:
            _, issues = kinds.parse(kind.kind, item, shape)
            row = existing.get(item.import_key.casefold())
            if row is None:
                row = run.new(
                    m.VoucherImportRow,
                    current,
                    job_id=job.id,
                    import_key=item.import_key,
                    ordinal=item.ordinal,
                    state="STAGED",
                    source_input={},
                    source_rows=[],
                    errors=[],
                )
                db.add(row)
            row.ordinal = item.ordinal
            if row.state == "CREATED":
                continue
            row.source_input = {"header": item.header, "lines": item.lines}
            row.source_rows = [list(position) for position in item.rows]
            row.errors = [issue.as_dict() for issue in issues[: rules.MAX_ERRORS]]
            row.state = "INVALID" if issues else "STAGED"
            row.prepared_input = None
            row.configuration_hash = None
            row.currency = None
            row.declared_total = row.computed_payable = row.computed_tax_total = (
                row.supplier_difference
            ) = None
            row.error_count = len(row.errors)
            row.row_version += 1
        job.revision += 1
        job.row_version += 1
        job.type_revision_id = native_revision.id
        job.source_format, job.input_sha256 = body.format, hashlib.sha256(raw).hexdigest()
        job.state, job.selection_digest = "STAGED", None
        job.voucher_count = len(staged)
        artifact = await db.scalar(
            select(m.VoucherImportArtifact).where(
                m.VoucherImportArtifact.company_id == job.company_id,
                m.VoucherImportArtifact.job_id == job.id,
            )
        )
        assert artifact is not None
        artifact.content, artifact.byte_count = raw, len(raw)
        artifact.media_type, artifact.content_sha256 = run.FILE_MEDIA[body.format], job.input_sha256
        artifact.row_version += 1
        await db.flush()
        run.count(job, await run.job_rows(db, current, job.id))
        await journal.capture_revision(db, current, job, raw, body.template_id)
        run.job_audit(db, current, job, "revise")
        return CommandReceipt(200, {"id": str(job.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await run.job_detail(db, current, uuid.UUID(refs["id"]))

    request = body.model_dump(mode="json", exclude={"content_base64", "document"})
    request["job_id"] = str(job_id)
    request["source_digest"] = hashlib.sha256(
        (body.content_base64 or json.dumps(body.document, sort_keys=True)).encode()
    ).hexdigest()
    return await run.job_command(
        factory, current, ("import.manage", "create"), "revise", key, request, mutate, render
    )


async def history(
    db: AsyncSession,
    current: Access,
    secret: bytes,
    job_id: uuid.UUID,
    kind: str,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    job = await run.readable_job(db, current, job_id)
    model: Any = m.VoucherImportRevision if kind == "revisions" else m.VoucherImportAttempt
    columns = (
        ("id", "revision", "source_format", "source_sha256", "created_at", "expires_at")
        if kind == "revisions"
        else ("id", "revision_id", "phase", "outcome", "created_at", "finished_at")
    )
    codec = run.cursor_codec(secret, current, f"{kind}:{job.id}")
    statement = select(*(getattr(model, col) for col in columns)).where(
        model.company_id == job.company_id, model.job_id == job.id
    )
    if (after := run.after(codec, cursor)) is not None:
        statement = statement.where(model.id < uuid.UUID(str(after)))
    records = list(
        (await db.execute(statement.order_by(model.id.desc()).limit(limit + 1))).mappings()
    )
    return {
        "items": [dict(row) for row in records[:limit]],
        "next_cursor": codec.encode({"after": str(records[limit - 1]["id"])})
        if len(records) > limit
        else None,
    }


async def attempt_results(
    db: AsyncSession,
    current: Access,
    secret: bytes,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    job = await run.readable_job(db, current, job_id)
    attempt = await get(db, current, m.VoucherImportAttempt, attempt_id)
    if attempt.job_id != job.id:
        raise PermissionDeniedError("attempt belongs to another job")
    codec = run.cursor_codec(secret, current, f"attempt:{attempt_id}")
    statement = select(m.VoucherImportResult).where(
        m.VoucherImportResult.company_id == job.company_id,
        m.VoucherImportResult.attempt_id == attempt.id,
    )
    if (after := run.after(codec, cursor)) is not None:
        statement = statement.where(m.VoucherImportResult.ordinal > int(after))
    rows = list(
        await db.scalars(statement.order_by(m.VoucherImportResult.ordinal).limit(limit + 1))
    )
    items = [dict(row.result) for row in rows[:limit]]
    if run.masked(current):
        for item in items:
            for field in (
                "currency",
                "declared_total",
                "computed_payable",
                "computed_tax_total",
                "supplier_difference",
            ):
                item[field] = None
    return {
        "items": items,
        "next_cursor": codec.encode({"after": rows[limit - 1].ordinal})
        if len(rows) > limit
        else None,
    }


def render_data(
    sources: list[dict[str, Any]], fmt: str, results: dict[str, dict[str, Any]] | None = None
) -> bytes:
    vouchers: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for source in sources:
        head = {"import_key": source["key"]} | canonical_source(source["source"])["header"]
        children = canonical_source(source["source"])["lines"]
        vouchers.append(head)
        lines.extend({"import_key": source["key"]} | line for line in children)
    if fmt == "JSON":
        return json.dumps(
            {
                "schema_version": 1,
                "vouchers": [
                    head
                    | {
                        "lines": [
                            {k: v for k, v in line.items() if k != "import_key"}
                            for line in lines
                            if line["import_key"] == head["import_key"]
                        ]
                    }
                    for head in vouchers
                ],
                **({"results": results} if results is not None else {}),
            },
            ensure_ascii=False,
        ).encode()
    header_names = list(dict.fromkeys(key for row in vouchers for key in row))
    line_names = list(dict.fromkeys(key for row in lines for key in row))

    def table(rows: list[dict[str, str]], names: list[str]) -> list[list[str]]:
        return [[row.get(key, "") for key in names] for row in rows]

    if fmt == "XLSX" and results is None:
        return xlsx_workbook(
            [
                ("vouchers", header_names, table(vouchers, header_names)),
                ("lines", line_names, table(lines, line_names)),
            ],
            marker=rules.MARKER,
        )
    flat = [
        head | line
        for head in vouchers
        for line in ([row for row in lines if row["import_key"] == head["import_key"]] or [{}])
    ]
    names = list(dict.fromkeys(header_names + line_names))
    if results is not None:
        names += ["_status", "_messages", "_draft_id", "_source_sheet", "_source_row"]
        positions = {r["key"]: r["positions"] for r in sources}
        line_counts = {r["key"]: len(r["source"]["lines"]) for r in sources}
        offsets: dict[str, int] = {}
        for row in flat:
            result = results.get(row["import_key"], {})
            errors = result.get("errors", [])
            key = row["import_key"]
            offset = offsets.get(key, 0)
            locations = positions[key]
            # Two-sheet workbooks store the voucher header before their line positions.
            start = 1 if len(locations) == line_counts[key] + 1 else 0
            location = locations[min(start + offset, len(locations) - 1)]
            offsets[key] = offset + 1
            row.update(
                {
                    "_status": result.get("state", ""),
                    "_draft_id": str(result.get("voucher_id") or ""),
                    "_messages": json.dumps(errors, ensure_ascii=False),
                    "_source_sheet": location[0],
                    "_source_row": str(location[1]),
                }
            )
    if fmt == "XLSX":
        return xlsx_workbook([("results", names, table(flat, names))], marker=rules.MARKER)
    return csv_document(
        names,
        table(flat, names),
        template=True,
        marker=rules.MARKER,
        delimiter="\t" if fmt == "TSV" else ",",
    )


async def download(
    db: AsyncSession, current: Access, job_id: uuid.UUID, options: ImportDownload
) -> tuple[bytes, str]:
    run.require(current, "import.read")
    job = await run.scoped_job(db, current, job_id)
    if run.masked(current):
        raise PermissionDeniedError("download contains fields that are no longer readable")
    number = options.revision or job.revision
    attempt = None
    source: m.VoucherImportRevision | None
    if options.attempt_id is not None:
        attempt = await get(db, current, m.VoucherImportAttempt, options.attempt_id)
        if attempt.job_id != job.id:
            raise PermissionDeniedError("attempt belongs to another job")
        source = await get(db, current, m.VoucherImportRevision, attempt.revision_id)
        if options.revision is not None and source.revision != options.revision:
            raise ValidationFailedError("attempt and revision differ")
    else:
        source = await db.scalar(
            select(m.VoucherImportRevision).where(
                m.VoucherImportRevision.company_id == job.company_id,
                m.VoucherImportRevision.job_id == job.id,
                m.VoucherImportRevision.revision == number,
            )
        )
    if source is None:
        raise ConflictError("import revision is unavailable")
    available = source.snapshot is not None and source.expires_at > utcnow()
    if not available and options.kind != "RESULT":
        raise ConflictError("import source data expired or is unavailable")
    if options.kind == "SOURCE":
        await db.refresh(source, ["content"])
        if source.content is None:
            raise ConflictError("source expired")
        content, fmt = source.content, source.source_format
    else:
        results = None
        if options.kind == "RESULT":
            if attempt is None:
                attempt = await db.scalar(
                    select(m.VoucherImportAttempt)
                    .where(
                        m.VoucherImportAttempt.company_id == job.company_id,
                        m.VoucherImportAttempt.job_id == job.id,
                        m.VoucherImportAttempt.revision_id == source.id,
                    )
                    .order_by(m.VoucherImportAttempt.id.desc())
                    .limit(1)
                )
            if attempt is None or attempt.outcome == "RUNNING":
                raise ConflictError("choose a completed validation or import attempt")
            results = {
                row.record_key: row.result
                for row in await db.scalars(
                    select(m.VoucherImportResult).where(
                        m.VoucherImportResult.company_id == job.company_id,
                        m.VoucherImportResult.attempt_id == attempt.id,
                    )
                )
            }
        if available:
            assert source.snapshot is not None
            sources = source.snapshot["rows"]
        else:
            assert results is not None
            # Retained attempt evidence remains downloadable after source cells expire.
            sources = [
                {
                    "key": key,
                    "source": {
                        "header": {
                            field: str(result.get(field) or "")
                            for field in (
                                "currency",
                                "declared_total",
                                "computed_payable",
                                "computed_tax_total",
                                "supplier_difference",
                            )
                        },
                        "lines": [],
                    },
                    "positions": result.get("source_rows") or [["results", result["ordinal"]]],
                }
                for key, result in results.items()
            ]
        content = await asyncio.to_thread(render_data, sources, options.format, results)
        fmt = options.format
    audit(db, current, "import_job", job.id, "report_access")
    return (
        content,
        f"voucher-import-{job.id}-r{source.revision}-{options.kind.lower()}.{fmt.lower()}",
    )

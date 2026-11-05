"""Bounded reusable import lifecycle. Adapters own authority and native commands."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import re
import uuid
from collections import defaultdict
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.bulk import BulkRecord, ordered_records, references, selection_digest
from billing_platform.command_transaction import command_transaction
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.import_contracts import (
    ImportBatch,
    ImportDetail,
    StageImport,
    TemplateDetail,
    TemplateRequest,
)
from billing_platform.import_files import decode_files
from billing_platform.import_models import (
    ImportArtifact,
    ImportChangeSet,
    ImportChangeSetEffect,
    ImportJob,
    ImportJobAttempt,
    ImportJobDependency,
    ImportJobRecord,
    ImportJobRevision,
    ImportRecordIssue,
    ImportRecordResult,
    ImportRow,
    ImportTemplateSnapshot,
)
from billing_platform.outbox import audit_payload, emit

ARTIFACT_DAYS = 30


class ImportAdapter(Protocol):
    actor: Actor
    company: uuid.UUID
    namespace: str
    definitions: dict[str, str]

    async def authorize(self, db: AsyncSession, *, write: bool) -> None: ...
    async def lock(self, db: AsyncSession) -> None: ...
    async def snapshot(
        self, db: AsyncSession, definition: str, parameters: dict[str, str]
    ) -> dict[str, Any]: ...
    async def fingerprint(self, db: AsyncSession, definition: str) -> str: ...
    async def readable(self, db: AsyncSession, batch: ImportBatch) -> None: ...
    async def execute(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
    ) -> dict[str, Any]: ...


@runtime_checkable
class PreparedImportAdapter(Protocol):
    """Opt-in owner preparation; external work is resumed outside this transaction."""

    async def prepare_import(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
        *,
        validate: bool,
    ) -> dict[str, Any]: ...


@runtime_checkable
class ImportPreflight(Protocol):
    async def before_import_command(
        self, action: str, body: BaseModel, job_id: uuid.UUID | None
    ) -> None: ...


def pending_effects(applied: dict[str, ImportChangeSetEffect]) -> bool:
    return any(
        value.get("pending") is True for row in applied.values() for value in row.results.values()
    )


def new(model: type[Any], adapter: ImportAdapter, **values: Any) -> Any:
    return model(
        id=uuid7(),
        tenant_id=adapter.actor.tenant_id,
        company_id=adapter.company,
        created_by=adapter.actor.user_id,
        updated_by=adapter.actor.user_id,
        **values,
    )


def evidence(db: AsyncSession, adapter: ImportAdapter, row: ImportRow, action: str) -> None:
    entity = adapter.namespace + ".import_job"
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=row.id,
        event_type=entity + "." + action,
        tenant_id=adapter.actor.tenant_id,
        payload=audit_payload(
            action=entity + "." + action,
            entity_type=entity,
            entity_id=row.id,
            actor_user_id=adapter.actor.user_id,
            company_id=adapter.company,
        ),
    )


def detail(job: ImportJob) -> ImportDetail:
    return ImportDetail.model_validate(
        {key: getattr(job, key) for key in ImportDetail.model_fields}
    )


async def scoped_job(
    db: AsyncSession, adapter: ImportAdapter, identifier: uuid.UUID, *, lock: bool = False
) -> ImportJob:
    await adapter.authorize(db, write=False)
    job = await company_object(db, ImportJob, identifier, company_id=adapter.company, lock=lock)
    if job.actor_user_id != adapter.actor.user_id:
        raise PermissionDeniedError("import belongs to another actor")
    return job


async def revision(
    db: AsyncSession, job: ImportJob, number: int | None = None
) -> ImportJobRevision:
    value = await db.scalar(
        select(ImportJobRevision).where(
            ImportJobRevision.company_id == job.company_id,
            ImportJobRevision.job_id == job.id,
            ImportJobRevision.revision == (number or job.revision),
        )
    )
    if value is None:
        raise ValidationFailedError("import revision is unavailable")
    return value


def groups(batch: ImportBatch) -> dict[str, list[BulkRecord]]:
    result: dict[str, list[BulkRecord]] = defaultdict(list)
    for record in ordered_records(batch.records):
        result[record.change_set].append(record)
    return dict(result)


def action_hash(records: list[BulkRecord]) -> str:
    return selection_digest(
        [row.model_dump(mode="json", exclude={"source_sheet", "source_row"}) for row in records]
    )


async def effects(db: AsyncSession, job: ImportJob) -> dict[str, ImportChangeSetEffect]:
    return {
        row.logical_key: row
        for row in await db.scalars(
            select(ImportChangeSetEffect)
            .where(
                ImportChangeSetEffect.company_id == job.company_id,
                ImportChangeSetEffect.job_id == job.id,
            )
            .limit(201)
        )
    }


async def stage_revision(
    db: AsyncSession, adapter: ImportAdapter, job: ImportJob, body: StageImport
) -> None:
    template = await company_object(
        db, ImportTemplateSnapshot, body.template_id, company_id=adapter.company
    )
    if template.actor_user_id != adapter.actor.user_id:
        raise PermissionDeniedError("template belongs to another actor")
    if template.snapshot is None or template.expires_at <= utcnow():
        raise ConflictError("template expired; generate a fresh template")
    await authorize_snapshot(db, adapter, template)
    options = body.model_dump(include={"mode", "atomicity", "on_error"})
    try:
        batch, sources, locations = await asyncio.to_thread(
            decode_files, body.files, template.snapshot, options
        )
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ValidationFailedError(
            "invalid import file; use the configured versioned template"
        ) from exc
    await adapter.readable(db, batch)
    previous = await effects(db, job)
    grouped = groups(batch)
    for key, effect in previous.items():
        if key not in grouped or action_hash(grouped[key]) != effect.action_hash:
            raise ConflictError("successful aggregates cannot be removed or changed")
    if previous:
        old = await revision(db, job, job.revision - 1)
        assert old.batch is not None
        if any(old.batch[key] != options[key] for key in options):
            raise ConflictError("successful import execution options are immutable")
    stored = new(
        ImportJobRevision,
        adapter,
        job_id=job.id,
        revision=job.revision,
        input_hash=selection_digest(batch.model_dump(mode="json")),
        batch=batch.model_dump(mode="json"),
    )
    db.add(stored)
    await db.flush()
    by_key = {}
    ordinal = 0
    for position, (key, records) in enumerate(grouped.items(), 1):
        aggregate = new(
            ImportChangeSet, adapter, revision_id=stored.id, logical_key=key, ordinal=position
        )
        db.add(aggregate)
        await db.flush()
        for record in records:
            ordinal += 1
            row = new(
                ImportJobRecord,
                adapter,
                change_set_id=aggregate.id,
                logical_key=record.key,
                ordinal=ordinal,
                source_file=locations[record.key],
                source_sheet=record.source_sheet,
                source_row=record.source_row,
                resource=record.resource,
            )
            db.add(row)
            by_key[record.key] = row
    await db.flush()
    for record in batch.records:
        parents = (
            set(record.depends_on)
            | references(record.data)
            | ({record.target.record} if record.target.record else set())
        )
        for parent in parents:
            db.add(
                new(
                    ImportJobDependency,
                    adapter,
                    parent_id=by_key[parent].id,
                    child_id=by_key[record.key].id,
                )
            )
    for file, raw in sources:
        db.add(
            new(
                ImportArtifact,
                adapter,
                revision_id=stored.id,
                filename=file.filename,
                format=file.format,
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
                content=raw,
                expires_at=job.expires_at,
            )
        )
    job.record_count = len(batch.records)
    job.state, job.review_digest, job.context_digest = "STAGED", None, None


async def authorize_snapshot(
    db: AsyncSession, adapter: ImportAdapter, template: ImportTemplateSnapshot
) -> None:
    """A retained snapshot and an idempotency receipt never grant read authority."""
    if template.snapshot is None:
        raise ConflictError("template payload expired")
    old = template.snapshot
    current = await adapter.snapshot(db, template.definition, old.get("parameters", {}))
    if not old["schemas"].keys() <= current["schemas"].keys():
        raise PermissionDeniedError("saved template includes unavailable resources")
    if not old.get("options", {}).keys() <= current.get("options", {}).keys():
        raise PermissionDeniedError("saved template includes unavailable options")
    for key, schema in old["schemas"].items():
        if (
            not schema.get("properties", {}).keys()
            <= current["schemas"][key].get("properties", {}).keys()
        ):
            raise PermissionDeniedError("saved template includes unavailable native fields")
        for scope in ("x-custom-fields", "x-shared-custom-fields"):
            previous = {field["key"] for field in schema.get(scope, [])}
            allowed = {field["key"] for field in current["schemas"][key].get(scope, [])}
            if not previous <= allowed:
                raise PermissionDeniedError("saved template includes unavailable custom fields")


def issues(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, PlatformError) and (exc.status_code >= 500 or exc.status_code == 429):
        return [
            {
                "field": "",
                "code": "owner_unavailable",
                "message": (
                    "A service could not complete this step. "
                    "Resume the import to retry the same command."
                ),
            }
        ]
    if isinstance(exc, ValidationError):
        return [
            {
                "field": ".".join(str(value) for value in error["loc"])[:128],
                "code": error["type"][:64],
                "message": "Required field is missing."
                if error["type"] == "missing"
                else "Field does not match its configured type or constraints.",
            }
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        ][:100]
    if isinstance(exc, PermissionDeniedError) or (
        isinstance(exc, PlatformError) and exc.status_code in {401, 403}
    ):
        return [
            {
                "field": "",
                "code": "permission_denied",
                "message": "Current permission does not allow this operation.",
            }
        ]
    if (
        isinstance(exc, PlatformError)
        and exc.status_code == 422
        and isinstance(exc.extra.get("fields"), dict)
    ):
        safe_messages = {
            "Unknown or ambiguous code": (
                "Choose an active, unambiguous code from this company's template options."
            ),
            "Duplicate code": (
                "This code is repeated in the import file. Give each new record a unique code."
            ),
            "Choose the template type": "Use the type selected when downloading this template.",
            "Required": "This field is required.",
            "Required by product configuration": "This field is required by Product Configuration.",
            "Disabled by product configuration": "This field is disabled by Product Configuration.",
        }
        fields = [
            field
            for field in exc.extra["fields"]
            if isinstance(field, str) and re.fullmatch(r"[A-Za-z0-9_.]{1,128}", field)
        ]
        if fields:
            return [
                {
                    "field": field,
                    "code": "validation_failed",
                    "message": safe_messages.get(
                        str(exc.extra["fields"][field]),
                        "Field does not match the current configuration or business rules.",
                    ),
                }
                for field in fields[:100]
            ]
    if isinstance(exc, ConflictError | IntegrityError) or (
        isinstance(exc, PlatformError) and exc.status_code == 409
    ):
        return [
            {
                "field": "",
                "code": "conflict",
                "message": (
                    "Identity, version, configuration or effective interval "
                    "conflicts with existing data."
                ),
            }
        ]
    return [
        {
            "field": "",
            "code": "invalid_record",
            "message": (
                "Native business validation rejected this record; "
                "check required fields and referenced active options."
            ),
        }
    ]


async def run_attempt(
    db: AsyncSession, adapter: ImportAdapter, job: ImportJob, *, validate: bool
) -> None:
    stored = await revision(db, job)
    if stored.batch is None:
        raise ConflictError("import data expired")
    batch = ImportBatch.model_validate(stored.batch)
    await adapter.readable(db, batch)
    context = await adapter.fingerprint(db, job.definition)
    if not validate and (
        job.state not in {"READY", "IMPORTING"}
        or (job.state == "READY" and job.context_digest != context)
    ):
        raise ConflictError("import changed since validation; validate again")
    applied = await effects(db, job)
    outputs: dict[str, dict[str, Any]] = {
        key: value for effect in applied.values() for key, value in effect.results.items()
    }
    outcomes: dict[str, tuple[str, list[dict[str, str]], dict[str, Any]]] = {}
    group_limit = getattr(adapter, "command_group_limit", None)
    # The first commit accepts the reviewed immutable input. Continuations still
    # execute current native policy, just as the retained owner commands do.
    continuing = job.state == ("VALIDATING" if validate else "IMPORTING") and (
        not validate or job.context_digest == context
    )
    if group_limit and continuing:
        previous = await db.scalar(
            select(ImportJobAttempt.id)
            .where(
                ImportJobAttempt.company_id == adapter.company,
                ImportJobAttempt.revision_id == stored.id,
            )
            .order_by(ImportJobAttempt.id.desc())
            .limit(1)
        )
        previous_rows = (
            await db.execute(
                select(ImportJobRecord.logical_key, ImportRecordResult)
                .join(ImportRecordResult, ImportRecordResult.record_id == ImportJobRecord.id)
                .where(
                    ImportJobRecord.company_id == adapter.company,
                    ImportRecordResult.attempt_id == previous,
                )
                .limit(200)
            )
        ).all()
        retained_messages: dict[uuid.UUID, list[dict[str, str]]] = {}
        if previous_rows:
            for issue in await db.scalars(
                select(ImportRecordIssue)
                .where(
                    ImportRecordIssue.company_id == adapter.company,
                    ImportRecordIssue.result_id.in_([result.id for _, result in previous_rows]),
                )
                .limit(20000)
            ):
                retained_messages.setdefault(issue.result_id, []).append(
                    {"field": issue.field, "code": issue.code, "message": issue.message}
                )
        for logical_key, result in previous_rows:
            if result.status == "QUEUED":
                continue
            messages = retained_messages.get(result.id, [])[:100]
            outcomes[logical_key] = (result.status, messages, outputs.get(logical_key, {}))
    processed = 0
    savepoint = await db.begin_nested()
    failed = any(status in {"INVALID", "FAILED", "BLOCKED"} for status, _, _ in outcomes.values())
    try:
        for aggregate_key, records in groups(batch).items():
            if aggregate_key in applied:
                for record in records:
                    outcomes[record.key] = (
                        "PENDING" if outputs[record.key].get("pending") else "APPLIED",
                        [],
                        outputs[record.key],
                    )
                continue
            if all(record.key in outcomes for record in records):
                continue
            if group_limit and processed >= group_limit:
                for record in records:
                    outcomes[record.key] = ("QUEUED", [], {})
                continue
            processed += 1
            if failed and (batch.on_error == "STOP" or batch.atomicity == "ATOMIC"):
                for record in records:
                    outcomes[record.key] = (
                        "SKIPPED",
                        [
                            {
                                "field": "",
                                "code": "stopped",
                                "message": "Processing stopped after an earlier aggregate failed.",
                            }
                        ],
                        {},
                    )
                continue
            group_outputs = dict(outputs)
            current = records[0]
            try:
                async with db.begin_nested():
                    for current in records:
                        parents = (
                            set(current.depends_on)
                            | references(current.data)
                            | ({current.target.record} if current.target.record else set())
                        )
                        if not parents <= group_outputs.keys():
                            raise ValidationFailedError("dependency failed")
                        command_key = f"import:{job.id}:{aggregate_key}:{current.key}"
                        if isinstance(adapter, PreparedImportAdapter):
                            group_outputs[current.key] = await adapter.prepare_import(
                                db,
                                current,
                                batch.mode,
                                group_outputs,
                                command_key,
                                validate=validate,
                            )
                        else:
                            group_outputs[current.key] = await adapter.execute(
                                db, current, batch.mode, group_outputs, command_key
                            )
                    if not validate:
                        db.add(
                            new(
                                ImportChangeSetEffect,
                                adapter,
                                job_id=job.id,
                                logical_key=aggregate_key,
                                action_hash=action_hash(records),
                                results={row.key: group_outputs[row.key] for row in records},
                            )
                        )
                    await db.flush()
            except (PlatformError, ValidationError, ValueError, IntegrityError, KeyError) as exc:
                failed = True
                for record in records:
                    outcomes[record.key] = (
                        "INVALID" if validate else "FAILED",
                        issues(exc)
                        if record.key == current.key
                        else [
                            {
                                "field": "",
                                "code": "aggregate_rollback",
                                "message": (
                                    "Another record in this aggregate failed; "
                                    "no aggregate changes were retained."
                                ),
                            }
                        ],
                        {},
                    )
            else:
                outputs = group_outputs
                for record in records:
                    outcomes[record.key] = (
                        "VALID"
                        if validate
                        else "PENDING"
                        if group_outputs[record.key].get("pending") is True
                        else "APPLIED",
                        [],
                        group_outputs[record.key],
                    )
        if validate or (failed and batch.atomicity == "ATOMIC"):
            await savepoint.rollback()
            if not validate:
                for key, (status, _, _) in list(outcomes.items()):
                    if status == "APPLIED" and key not in {
                        item for effect in applied.values() for item in effect.results
                    }:
                        outcomes[key] = (
                            "FAILED",
                            [
                                {
                                    "field": "",
                                    "code": "atomic_rollback",
                                    "message": (
                                        "The atomic import failed; " "all changes were rolled back."
                                    ),
                                }
                            ],
                            {},
                        )
        else:
            await savepoint.commit()
    except BaseException:
        if savepoint.is_active:
            await savepoint.rollback()
        raise
    # Rolled-back ORM objects must not be consulted here. Only detached scalar values
    # captured above survive; preview-generated business IDs are deliberately discarded.
    unfinished = any(status == "QUEUED" for status, _, _ in outcomes.values())
    attempt = new(
        ImportJobAttempt,
        adapter,
        revision_id=stored.id,
        phase="VALIDATE" if validate else "IMPORT",
        outcome="PENDING"
        if unfinished
        else "FAILED"
        if failed
        else "PENDING"
        if any(status == "PENDING" for status, _, _ in outcomes.values())
        else "SUCCEEDED",
        finished_at=utcnow(),
    )
    db.add(attempt)
    await db.flush()
    record_rows = list(
        await db.scalars(
            select(ImportJobRecord)
            .join(ImportChangeSet, ImportJobRecord.change_set_id == ImportChangeSet.id)
            .where(
                ImportJobRecord.company_id == adapter.company,
                ImportChangeSet.revision_id == stored.id,
            )
            .limit(201)
        )
    )
    for row in record_rows:
        status, messages, output = outcomes[row.logical_key]
        result = new(
            ImportRecordResult,
            adapter,
            attempt_id=attempt.id,
            record_id=row.id,
            status=status,
            business_id=uuid.UUID(output["id"])
            if status == "APPLIED" and output.get("id")
            else None,
        )
        db.add(result)
        await db.flush()
        for message in messages:
            db.add(new(ImportRecordIssue, adapter, result_id=result.id, **message))
    job.row_version += 1
    job.updated_by = adapter.actor.user_id
    if validate:
        job.context_digest = context
        job.review_digest = (
            None
            if failed or unfinished
            else selection_digest(
                {"input": stored.input_hash, "context": context, "revision": job.revision}
            )
        )
        job.state = "VALIDATING" if unfinished else "INVALID" if failed else "READY"
    else:
        job.completed_count = sum(status == "APPLIED" for status, _, _ in outcomes.values())
        job.state = (
            "IMPORTING"
            if unfinished
            else "SUCCEEDED"
            if job.completed_count == job.record_count
            else "PARTIAL"
            if job.completed_count or any(status == "PENDING" for status, _, _ in outcomes.values())
            else "FAILED"
        )
        if not unfinished:
            job.review_digest = None
    evidence(db, adapter, job, "update")


async def command(
    factory: async_sessionmaker[AsyncSession],
    adapter: ImportAdapter,
    action: str,
    body: BaseModel,
    key: str,
    job_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    values = body.model_dump(mode="json")
    request_digest = hashlib.sha256(
        await asyncio.to_thread(canonical_json, values, maximum_bytes=13 * 1024 * 1024)
    ).hexdigest()

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await adapter.authorize(db, write=True)
        if job_id is not None:
            await scoped_job(db, adapter, job_id)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await adapter.lock(db)
        if action == "template":
            request = TemplateRequest.model_validate(body.model_dump())
            snapshot = await adapter.snapshot(db, request.definition, request.parameters)
            row = new(
                ImportTemplateSnapshot,
                adapter,
                actor_user_id=adapter.actor.user_id,
                definition=request.definition,
                fingerprint=selection_digest(snapshot),
                snapshot=snapshot,
                expires_at=utcnow() + dt.timedelta(days=ARTIFACT_DAYS),
            )
            db.add(row)
            await db.flush()
            evidence(db, adapter, row, "create")
            return CommandReceipt(201, {"template_id": str(row.id)})
        if action == "stage":
            request_stage = StageImport.model_validate(body.model_dump())
            template = await company_object(
                db, ImportTemplateSnapshot, request_stage.template_id, company_id=adapter.company
            )
            job = new(
                ImportJob,
                adapter,
                actor_user_id=adapter.actor.user_id,
                template_id=template.id,
                definition=template.definition,
                record_count=1,
                expires_at=min(template.expires_at, utcnow() + dt.timedelta(days=ARTIFACT_DAYS)),
            )
            db.add(job)
            await db.flush()
            await stage_revision(db, adapter, job, request_stage)
            evidence(db, adapter, job, "create")
        else:
            assert job_id is not None
            job = await scoped_job(db, adapter, job_id, lock=True)
            if values["expected_version"] != job.row_version:
                raise ConflictError("import version changed")
            if (job.expires_at <= utcnow() and job.state != "IMPORTING") or job.state in {
                "CANCELLED",
                "EXPIRED",
            }:
                raise ConflictError("import is no longer actionable")
            if (job.state == "IMPORTING" or pending_effects(await effects(db, job))) and not (
                action == "commit" and job.state == "IMPORTING"
            ):
                raise ConflictError(
                    "Import has pending owner commands; resume them before changing this job"
                )
            if action in {"validate", "retry"}:
                if job.state == "SUCCEEDED":
                    raise ConflictError("import already succeeded")
                await run_attempt(db, adapter, job, validate=True)
            elif action == "commit":
                if values["review_digest"] != job.review_digest:
                    raise ConflictError("validation review differs")
                await run_attempt(db, adapter, job, validate=False)
            elif action == "revise":
                if job.state == "SUCCEEDED":
                    raise ConflictError("successful import cannot be revised")
                old = await revision(db, job)
                assert old.batch is not None
                job.revision += 1
                job.row_version += 1
                await stage_revision(
                    db,
                    adapter,
                    job,
                    StageImport(
                        template_id=job.template_id,
                        files=values["files"],
                        **{name: old.batch[name] for name in ("mode", "atomicity", "on_error")},
                    ),
                )
                evidence(db, adapter, job, "update")
            elif action == "cancel":
                if job.state == "SUCCEEDED":
                    raise ConflictError("successful import cannot be cancelled")
                job.state, job.review_digest = "CANCELLED", None
                job.row_version += 1
                evidence(db, adapter, job, "update")
            else:
                raise ValueError("unknown import command")
        await db.flush()
        return CommandReceipt(200 if action != "stage" else 201, {"job_id": str(job.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        if "template_id" in receipt:
            row = await company_object(
                db,
                ImportTemplateSnapshot,
                uuid.UUID(receipt["template_id"]),
                company_id=adapter.company,
            )
            if (
                row.actor_user_id != adapter.actor.user_id
                or row.snapshot is None
                or row.expires_at <= utcnow()
            ):
                raise ConflictError("template is no longer available")
            await authorize_snapshot(db, adapter, row)
            return TemplateDetail(
                id=row.id,
                definition=row.definition,
                fingerprint=row.fingerprint,
                snapshot=row.snapshot,
                expires_at=row.expires_at,
            )
        return detail(await scoped_job(db, adapter, uuid.UUID(receipt["job_id"])))

    async with (
        asyncio.timeout(60 if getattr(adapter, "command_group_limit", None) else 30),
        command_transaction(
            factory,
            tenant_id=adapter.actor.tenant_id,
            company_id=adapter.company,
            actor_id=adapter.actor.user_id,
        ),
    ):
        return await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=adapter.actor.tenant_id,
                company_id=adapter.company,
                actor_id=adapter.actor.user_id,
                operation=adapter.namespace + ".import." + action,
                key=key,
                request={
                    "job_id": str(job_id) if job_id else None,
                    "body_digest": request_digest,
                },
            ),
            authorize=authorize,
            mutate=mutate,
            render=render,
            timeout_seconds=60 if getattr(adapter, "command_group_limit", None) else 30,
        )

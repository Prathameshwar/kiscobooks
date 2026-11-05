"""Durable bulk administration: immutable input revisions and reviewed selection."""

import datetime as dt
import hashlib
import uuid
from collections import defaultdict
from typing import Any

from billing_platform.bulk import (
    BulkBatch,
    BulkRecord,
    ordered_records,
    references,
    selection_digest,
)
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import (
    BulkChangeSet,
    BulkImportArtifact,
    BulkJob,
    BulkJobDependency,
    BulkJobRecord,
)
from catalog.schemas.bulk import (
    BulkQuery,
    CommitJob,
    FileStage,
    FilterStage,
    JobAction,
    JobDetail,
    JobListItem,
    JsonStage,
    RecordListItem,
    RecordPreview,
    ReviseJob,
    ValidateJob,
)
from catalog.tasks.bulk_access import readable_evidence, require_bulk, resource_entity, scoped_job
from catalog.tasks.bulk_inputs import decode_stage
from catalog.tasks.bulk_registry import OPERATIONS, operation
from catalog.tasks.bulk_selection import materialize
from catalog.tasks.classification import audit_change
from catalog.tasks.field_context import FieldContext, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state


def audit(db: AsyncSession, actor: Actor, job: BulkJob, action: str = "update") -> None:
    audit_change(
        db,
        actor,
        job.company_id,
        "catalog.bulk_job",
        job.id,
        action,
        frozenset(
            {
                "state",
                "revision",
                "record_count",
                "completed_count",
                "invalid_count",
                "selection_digest",
            }
        ),
    )


def touch(row: Any, actor: Actor) -> None:
    if row.row_version >= 2**31 - 1:
        raise ConflictError("bulk object version exhausted")
    row.row_version += 1
    row.updated_at, row.updated_by = utcnow(), actor.user_id


def new(model: type[Any], actor: Actor, company: uuid.UUID, **values: Any) -> Any:
    return model(
        id=uuid7(),
        tenant_id=actor.tenant_id,
        company_id=company,
        row_version=1,
        created_by=actor.user_id,
        updated_by=actor.user_id,
        **values,
    )


async def records(db: AsyncSession, job: BulkJob) -> list[BulkJobRecord]:
    return list(
        await db.scalars(
            select(BulkJobRecord)
            .where(BulkJobRecord.company_id == job.company_id, BulkJobRecord.job_id == job.id)
            .order_by(BulkJobRecord.ordinal)
            .limit(2001)
        )
    )


async def change_sets(db: AsyncSession, job: BulkJob) -> list[BulkChangeSet]:
    return list(
        await db.scalars(
            select(BulkChangeSet)
            .where(BulkChangeSet.company_id == job.company_id, BulkChangeSet.job_id == job.id)
            .order_by(BulkChangeSet.ordinal)
            .limit(2001)
        )
    )


async def stage_rows(
    db: AsyncSession,
    actor: Actor,
    job: BulkJob,
    batch: BulkBatch,
    *,
    sealed: dict[str, BulkChangeSet] | None = None,
) -> None:
    retained = sealed or {}
    grouped: dict[str, list[BulkRecord]] = defaultdict(list)
    for record in ordered_records(batch.records):
        if record.action != "AUTO":
            operation(record.resource, record.action)
        elif not any(
            resource == record.resource and action in {"CREATE", "UPDATE"}
            for resource, action in OPERATIONS
        ):
            raise ValidationFailedError("resource cannot be imported")
        grouped[record.change_set].append(record)
    if not retained.keys() <= grouped.keys():
        raise ConflictError("completed change sets must remain in a revision")
    by_key: dict[str, BulkJobRecord] = {row.logical_key: row for row in await records(db, job)}
    ordinal = 0
    for set_ordinal, (key, members) in enumerate(grouped.items(), 1):
        commands = sum(
            operation(row.resource, row.action).command_count if row.action != "AUTO" else 1
            for row in members
        )
        if commands > 100:
            raise ValidationFailedError("one change set may execute at most 100 native commands")
        digest = selection_digest([row.model_dump(mode="json") for row in members])
        if key in retained:
            if retained[key].action_hash != digest:
                raise ConflictError("completed effects are sealed; corrections require a new job")
            ordinal += len(members)
            continue
        group = new(
            BulkChangeSet,
            actor,
            job.company_id,
            job_id=job.id,
            logical_key=key,
            ordinal=set_ordinal,
            record_count=len(members),
            action_hash=digest,
            state="STAGED",
        )
        db.add(group)
        await db.flush([group])
        for record in members:
            ordinal += 1
            row = new(
                BulkJobRecord,
                actor,
                job.company_id,
                job_id=job.id,
                change_set_id=group.id,
                logical_key=record.key,
                ordinal=ordinal,
                resource=record.resource,
                action=record.action,
                source_sheet=record.source_sheet,
                source_row=record.source_row,
                normalized_input=record.model_dump(mode="json"),
                state="STAGED",
            )
            db.add(row)
            by_key[record.key] = row
    await db.flush()
    if (
        batch.atomicity == "ATOMIC"
        and sum(
            operation(row.resource, row.action).command_count if row.action != "AUTO" else 1
            for row in batch.records
        )
        > 1000
    ):
        raise ValidationFailedError("atomic jobs may execute at most 1000 native commands")
    for record in batch.records:
        for parent in (
            set(record.depends_on)
            | references(record.data)
            | ({record.target.record} if record.target.record else set())
        ):
            db.add(
                new(
                    BulkJobDependency,
                    actor,
                    job.company_id,
                    job_id=job.id,
                    parent_record_id=by_key[parent].id,
                    child_record_id=by_key[record.key].id,
                )
            )


async def detail(
    db: AsyncSession, actor: Actor, company: uuid.UUID, job_id: uuid.UUID
) -> JobDetail:
    job = await scoped_job(db, actor, company, job_id)
    context = await require_bulk(db, actor, company)
    required = set(JobDetail.model_fields) - {"id", "company_id", "created_at", "actor_user_id"}
    values = {key: getattr(job, key) for key in context.native.fields}
    if not required <= context.readable(values):
        raise PermissionDeniedError("bulk job fields are protected")
    return JobDetail.model_validate(job, from_attributes=True)


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: JsonStage | FileStage | FilterStage | JobAction,
    key: str,
    *,
    action: str = "stage",
    job_id: uuid.UUID | None = None,
) -> CommandResult[JobDetail]:
    body_hash = hashlib.sha256(
        canonical_json(body.model_dump(mode="json"), maximum_bytes=13 * 1024 * 1024)
    ).hexdigest()
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.bulk_job." + action,
        key,
        {"id": str(job_id) if job_id else None, "body_sha256": body_hash},
    )
    permission = "catalog.bulk.commit" if action == "commit" else "catalog.bulk.manage"

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await require_bulk(db, actor, company, permission)
        if job_id is not None:
            await scoped_job(db, actor, company, job_id)
        if receipt is not None:
            await scoped_job(db, actor, company, uuid.UUID(receipt["id"]))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await policy_state(db, actor, company, lock=True)
        if isinstance(body, JsonStage | FileStage | FilterStage):
            if isinstance(body, FilterStage):
                batch = await materialize(db, actor, company, body)
                raw, content_type = (
                    canonical_json(batch.model_dump(mode="json"), maximum_bytes=8 * 1024 * 1024),
                    "application/json",
                )
            else:
                batch, raw, content_type = decode_stage(body)
            job = new(
                BulkJob,
                actor,
                company,
                actor_user_id=actor.user_id,
                kind="UPDATE" if isinstance(body, FilterStage) else "IMPORT",
                mode=batch.mode,
                atomicity=batch.atomicity,
                on_error=batch.on_error,
                state="STAGED",
                revision=1,
                schema_version=1,
                input_hash=selection_digest(batch.model_dump(mode="json")),
                record_count=len(batch.records),
                completed_count=0,
                invalid_count=0,
                expires_at=utcnow() + dt.timedelta(days=7),
            )
            db.add(job)
            await db.flush([job])
            await stage_rows(db, actor, job, batch)
            db.add(
                new(
                    BulkImportArtifact,
                    actor,
                    company,
                    job_id=job.id,
                    content_type=content_type,
                    content_sha256=hashlib.sha256(raw).hexdigest(),
                    byte_count=len(raw),
                    expires_at=job.expires_at,
                    content=raw,
                )
            )
            audit(db, actor, job, "create")
        else:
            assert job_id is not None
            job = await scoped_job(db, actor, company, job_id, lock=True, live=action != "cancel")
            if job.row_version != body.expected_version:
                raise ConflictError("bulk job changed; reload its current version")
            rows, groups = await records(db, job), await change_sets(db, job)
            if action == "cancel":
                if job.state == "SUCCEEDED":
                    raise ConflictError("completed effects cannot be cancelled")
                job.state = "CANCELLED"
            elif isinstance(body, ValidateJob):
                if job.state in {"VALIDATING", "QUEUED", "RUNNING", "SUCCEEDED"}:
                    raise ConflictError("bulk job cannot be reviewed in its current state")
                selected = set(
                    body.selected_keys
                    or [group.logical_key for group in groups if group.state != "APPLIED"]
                )
                if (
                    len(selected) != len(body.selected_keys or selected)
                    or not selected
                    or not selected
                    <= {group.logical_key for group in groups if group.state != "APPLIED"}
                ):
                    raise ValidationFailedError(
                        "selection requires unique unfinished change-set keys"
                    )
                selected_rows = {
                    row.logical_key
                    for row in rows
                    if any(
                        group.id == row.change_set_id and group.logical_key in selected
                        for group in groups
                    )
                    or row.state == "APPLIED"
                }
                for row in rows:
                    record = BulkRecord.model_validate(row.normalized_input)
                    deps = (
                        set(record.depends_on)
                        | references(record.data)
                        | ({record.target.record} if record.target.record else set())
                    )
                    if row.logical_key in selected_rows and not deps <= selected_rows:
                        raise ValidationFailedError(
                            "selected work requires its unfinished dependencies"
                        )
                for group in groups:
                    if group.state != "APPLIED":
                        group.state, group.error_code = (
                            ("STAGED" if group.logical_key in selected else "EXCLUDED"),
                            None,
                        )
                for row in rows:
                    if row.state != "APPLIED":
                        row.state = "STAGED" if row.logical_key in selected_rows else "EXCLUDED"
                        row.prepared_input, row.preview, row.source_pins, row.error_code = (
                            None,
                            None,
                            None,
                            None,
                        )
                        row.target_id, row.target_key, row.expected_version = None, None, None
                state = await policy_state(db, actor, company)
                context = await require_bulk(db, actor, company)
                from catalog.tasks.bulk_identity import identity_digest

                job.identity_digest = await identity_digest(db, company)
                job.policy_generation, job.source_version = (
                    state.generation if state else 1,
                    context.source_version,
                )
                job.selected_keys, job.selection_digest, job.invalid_count, job.state = (
                    sorted(selected),
                    None,
                    0,
                    "VALIDATING",
                )
            elif isinstance(body, CommitJob):
                if job.state != "READY" or job.selection_digest != body.selection_digest:
                    raise ConflictError("commit requires the current reviewed selection digest")
                job.state = "QUEUED"
            elif isinstance(body, ReviseJob):
                if job.state in {"VALIDATING", "QUEUED", "RUNNING", "SUCCEEDED"}:
                    raise ConflictError("stop pending work before revising")
                if (body.batch.mode, body.batch.atomicity, body.batch.on_error) != (
                    job.mode,
                    job.atomicity,
                    job.on_error,
                ):
                    raise ConflictError("job modes remain fixed across revisions")
                sealed = {group.logical_key: group for group in groups if group.state == "APPLIED"}
                dependencies = await db.scalars(
                    select(BulkJobDependency)
                    .where(
                        BulkJobDependency.company_id == company, BulkJobDependency.job_id == job.id
                    )
                    .limit(20000)
                )
                for dependency in dependencies:
                    await db.delete(dependency)
                await db.flush()
                for row in rows:
                    if row.state != "APPLIED":
                        await db.delete(row)
                await db.flush()
                for group in groups:
                    if group.state != "APPLIED":
                        await db.delete(group)
                await db.flush()
                await stage_rows(db, actor, job, body.batch, sealed=sealed)
                job.revision += 1
                job.input_hash, job.record_count = (
                    selection_digest(body.batch.model_dump(mode="json")),
                    len(body.batch.records),
                )
                job.state, job.selection_digest, job.selected_keys, job.invalid_count = (
                    "STAGED",
                    None,
                    None,
                    0,
                )
            else:
                raise ValidationFailedError("unsupported bulk job transition")
            touch(job, actor)
            audit(db, actor, job)
        await db.flush()
        return CommandReceipt(202, {"id": str(job.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> JobDetail:
        return await detail(db, actor, company, uuid.UUID(receipt["id"]))

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render, timeout_seconds=60
    )


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: BulkQuery,
    secret: bytes,
    *,
    job_id: uuid.UUID | None = None,
) -> Page[Any]:
    context = await require_bulk(db, actor, company)
    model: Any = BulkJob if job_id is None else BulkJobRecord
    schema: type[BaseModel] = JobListItem if job_id is None else RecordListItem
    if job_id is not None:
        await scoped_job(db, actor, company, job_id)
        context = await load_field_context(db, actor, company, "catalog.bulk_job_record")
    if not (set(schema.model_fields) - {"id", "company_id", "created_at"}) <= context.readable():
        raise PermissionDeniedError("bulk list fields are protected")
    stmt = select(*(getattr(model, key) for key in schema.model_fields)).where(
        model.company_id == company
    )
    stmt = (
        stmt.where(model.actor_user_id == actor.user_id)
        if job_id is None
        else stmt.where(model.job_id == job_id)
    )
    if query.state:
        stmt = stmt.where(model.state == query.state)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=cursor_codec(secret, actor, company, "catalog.bulk." + str(job_id), context, query),
        project=schema.model_validate,
    )


async def preview(
    db: AsyncSession, actor: Actor, company: uuid.UUID, job_id: uuid.UUID, record_id: uuid.UUID
) -> RecordPreview:
    job = await scoped_job(db, actor, company, job_id, live=True)
    row = await db.scalar(
        select(BulkJobRecord).where(
            BulkJobRecord.company_id == company,
            BulkJobRecord.job_id == job.id,
            BulkJobRecord.id == record_id,
        )
    )
    if row is None:
        raise PermissionDeniedError("record is outside this bulk job")
    return await render_preview(db, actor, company, row)


async def render_preview(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    row: BulkJobRecord,
    *,
    contexts: dict[str, FieldContext] | None = None,
) -> RecordPreview:
    contexts = {} if contexts is None else contexts
    metadata = RecordListItem.model_validate(row, from_attributes=True).model_dump()
    await readable_evidence(
        db,
        actor,
        company,
        [
            {
                "resource": "bulk_job_record",
                "values": {k: v for k, v in metadata.items() if k != "id"},
            }
        ],
        contexts=contexts,
    )
    saved = row.preview or {}
    if row.resource not in contexts:
        contexts[row.resource] = await load_field_context(
            db,
            actor,
            company,
            resource_entity(row.resource),
        )
    evidence = [*(row.source_pins or [])]
    for name in ("before", "after"):
        if saved.get(name) is not None:
            evidence.append({"resource": row.resource, "values": saved[name]})
    for change in saved.get("changes", []):
        for name in ("before", "after"):
            if change.get(name) is not None:
                evidence.append({"resource": change["resource"], "values": change[name]})
    await readable_evidence(db, actor, company, evidence, contexts=contexts)
    return RecordPreview(
        **metadata,
        before=saved.get("before"),
        after=saved.get("after"),
        result=saved.get("result") if row.state == "APPLIED" else None,
        changes=saved.get("changes", []),
        error_fields=saved.get("error_fields", []),
    )

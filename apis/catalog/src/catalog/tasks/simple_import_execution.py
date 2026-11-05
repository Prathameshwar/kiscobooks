"""Resume retained row commands outside the import transaction and checkpoint results."""

import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.import_contracts import ImportBatch
from billing_platform.import_engine import (
    detail,
    effects,
    evidence,
    issues,
    new,
    revision,
    scoped_job,
)
from billing_platform.import_journal import StepBudget
from billing_platform.import_models import (
    ImportChangeSet,
    ImportChangeSetEffect,
    ImportJob,
    ImportJobAttempt,
    ImportJobRecord,
    ImportRecordIssue,
    ImportRecordResult,
)
from billing_platform.import_reads import codec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.schemas.simple_product_import import SimpleImportProgress, SimpleImportRowResult
from catalog.tasks import simple_import_definition as definition
from catalog.tasks import simple_product_creation as creation
from catalog.tasks.simple_import_adapter import SimpleCatalogImportAdapter


async def load(
    db: AsyncSession,
    adapter: SimpleCatalogImportAdapter,
    identity: uuid.UUID,
    *,
    lock: bool = False,
) -> tuple[
    ImportJob,
    list[ImportJobRecord],
    dict[str, ImportChangeSetEffect],
    dict[str, SimpleProductCreation],
]:
    job = await scoped_job(db, adapter, identity, lock=lock)
    if job.definition != definition.DEFINITION:
        raise ValidationFailedError("This is not a Simple product creation import")
    stored = await revision(db, job)
    applied = await effects(db, job)
    identifiers = [
        uuid.UUID(value["receipt_id"])
        for effect in applied.values()
        for value in effect.results.values()
    ]
    receipts = {
        str(row.id): row
        for row in await db.scalars(
            select(SimpleProductCreation)
            .where(
                SimpleProductCreation.company_id == adapter.company,
                SimpleProductCreation.id.in_(identifiers),
            )
            .limit(200)
        )
    }
    if len(receipts) != len(identifiers) or any(
        row.created_by != adapter.actor.user_id for row in receipts.values()
    ):
        raise PermissionDeniedError("Import creation ownership differs")
    if stored.batch is not None:
        await adapter.readable(db, ImportBatch.model_validate(stored.batch))
    else:
        # Source retention does not erase or authorize pending native effects.
        fields = {"name", "code"}
        for receipt in receipts.values():
            fields |= {key for key, value in receipt.request.items() if value is not None}
            if receipt.request.get("tax"):
                fields |= {"hsn_sac", "gst_rule"}
        await definition.require_readable(db, adapter.actor, adapter.company, fields)
        if any(
            row.request.get("opening_quantity") not in {None, "0", "0.0000"}
            for row in receipts.values()
        ):
            quantity = next(
                (field for field in adapter.opening_fields if field["key"] == "quantity"), {}
            )
            if not quantity.get("readable"):
                raise PermissionDeniedError("Opening stock import fields are protected")
    records = list(
        await db.scalars(
            select(ImportJobRecord)
            .join(ImportChangeSet, ImportJobRecord.change_set_id == ImportChangeSet.id)
            .where(
                ImportJobRecord.company_id == adapter.company,
                ImportChangeSet.revision_id == stored.id,
            )
            .order_by(ImportJobRecord.id)
            .limit(200)
        )
    )
    return job, records, applied, receipts


def outputs(applied: dict[str, ImportChangeSetEffect]) -> dict[str, dict[str, Any]]:
    return {key: value for effect in applied.values() for key, value in effect.results.items()}


def progress(job: ImportJob, applied: dict[str, ImportChangeSetEffect]) -> SimpleImportProgress:
    values = outputs(applied).values()
    pending = sum(value.get("pending") is True for value in values)
    if job.state in {"IMPORTING", "VALIDATING"}:
        pending = job.record_count - job.completed_count
    failures = sum(bool(value.get("last_error")) for value in outputs(applied).values())
    return SimpleImportProgress(
        job=detail(job),
        pending_count=pending,
        failed_count=failures,
        can_resume=pending > 0 and not (job.state == "VALIDATING" and job.expires_at <= utcnow()),
    )


async def read(adapter: SimpleCatalogImportAdapter, identity: uuid.UUID) -> SimpleImportProgress:
    with tenant_scope(adapter.actor.tenant_id):
        async with adapter.factory() as db:
            job, _, applied, _ = await load(db, adapter, identity)
            return progress(job, applied)


async def rows(
    adapter: SimpleCatalogImportAdapter, identity: uuid.UUID, limit: int, cursor: str | None
) -> dict[str, Any]:
    with tenant_scope(adapter.actor.tenant_id):
        async with adapter.factory() as db:
            job, records, applied, receipts = await load(db, adapter, identity)
            signed = codec(
                adapter.secret, adapter, f"simple-rows:{job.id}:{job.row_version}:{limit}"
            )
            if cursor:
                try:
                    after = uuid.UUID(signed.decode(cursor)["id"])
                except (ValueError, KeyError) as error:
                    raise ValidationFailedError("Invalid result cursor") from error
                records = [row for row in records if row.id > after]
            selected = records[:limit]
            values = outputs(applied)
            stored = await revision(db, job)
            inputs = {row["key"]: row["data"] for row in (stored.batch or {}).get("records", [])}
            attempt = await db.scalar(
                select(ImportJobAttempt)
                .where(
                    ImportJobAttempt.company_id == adapter.company,
                    ImportJobAttempt.revision_id == stored.id,
                )
                .order_by(ImportJobAttempt.id.desc())
                .limit(1)
            )
            results = (
                {}
                if attempt is None
                else {
                    row.record_id: row
                    for row in await db.scalars(
                        select(ImportRecordResult).where(
                            ImportRecordResult.company_id == adapter.company,
                            ImportRecordResult.attempt_id == attempt.id,
                            ImportRecordResult.record_id.in_([row.id for row in selected]),
                        )
                    )
                }
            )
            messages: dict[uuid.UUID, list[dict[str, str]]] = {}
            if results:
                for result_id, field, code, message in await db.execute(
                    select(
                        ImportRecordIssue.result_id,
                        ImportRecordIssue.field,
                        ImportRecordIssue.code,
                        ImportRecordIssue.message,
                    )
                    .where(
                        ImportRecordIssue.company_id == adapter.company,
                        ImportRecordIssue.result_id.in_([row.id for row in results.values()]),
                    )
                    .order_by(ImportRecordIssue.id)
                    .limit(20001)
                ):
                    messages.setdefault(result_id, []).append(
                        {"field": field, "code": code, "message": message}
                    )
            items = []
            for row in selected:
                output = values.get(row.logical_key, {})
                native = receipts.get(output.get("receipt_id", ""))
                result = results.get(row.id)
                state = result.status if result else "STAGED"
                if output:
                    state = (
                        "FAILED"
                        if output.get("last_error")
                        else "PENDING"
                        if output.get("pending")
                        else "APPLIED"
                    )
                data = inputs.get(row.logical_key, {})
                items.append(
                    SimpleImportRowResult(
                        id=row.id,
                        key=row.logical_key,
                        source_file=row.source_file,
                        source_sheet=row.source_sheet,
                        source_row=row.source_row,
                        code=native.code if native else data.get("code"),
                        name=native.request.get("name") if native else data.get("name"),
                        state=state,
                        step=native.step if native else None,
                        item_id=native.item_id if native and native.status == "COMPLETE" else None,
                        opening_posted=bool(output.get("opening_posted")),
                        messages=output.get("last_error") or messages.get(result.id, [])[:100]
                        if result
                        else output.get("last_error", []),
                    ).model_dump(mode="json")
                )
            return {
                "items": items,
                "page": {
                    "limit": limit,
                    "has_more": len(records) > limit,
                    "next_cursor": signed.encode({"id": str(selected[-1].id)})
                    if len(records) > limit
                    else None,
                },
            }


async def advance(adapter: SimpleCatalogImportAdapter, identity: uuid.UUID) -> SimpleImportProgress:
    context = adapter.financial_context()
    with tenant_scope(adapter.actor.tenant_id):
        async with adapter.factory() as db:
            await adapter.authorize(db, write=True)
            job, _, applied, _ = await load(db, adapter, identity)
            if job.state == "IMPORTING":
                raise ConflictError("Continue reviewed import admission before processing products")
            pending = [
                value["receipt_id"]
                for value in sorted(
                    outputs(applied).values(), key=lambda value: bool(value.get("last_error"))
                )
                if value.get("pending")
            ]
        budget = StepBudget(40, seconds=8)
        failures: dict[str, list[dict[str, str]]] = {}
        visited: set[str] = set()
        for receipt_id in pending:
            while budget.take():
                visited.add(receipt_id)
                try:
                    previous = await creation.read(
                        adapter.factory, adapter.actor, adapter.company, uuid.UUID(receipt_id)
                    )
                    current = await creation.advance(
                        adapter.factory,
                        adapter.actor,
                        context,
                        uuid.UUID(receipt_id),
                        adapter.owners,
                    )
                except PlatformError as error:
                    failures[receipt_id] = issues(error)
                    break
                if (
                    current.status == "COMPLETE"
                    or current.step == "FINALIZE"
                    or current.row_version == previous.row_version
                ):
                    break
            if not budget.alive() or budget.used >= budget.maximum:
                break
        async with adapter.factory() as db, db.begin():
            await adapter.authorize(db, write=True)
            job, records, applied, receipts = await load(db, adapter, identity, lock=True)
            changed = False
            for effect in applied.values():
                updated = {}
                for key, output in effect.results.items():
                    value = dict(output)
                    native = receipts[value["receipt_id"]]
                    if native.status == "COMPLETE":
                        value.update(
                            pending=False,
                            id=str(native.item_id),
                            opening_posted=bool(native.progress.get("opening_posted")),
                        )
                        value.pop("last_error", None)
                    elif value["receipt_id"] in visited:
                        value.pop("last_error", None)
                        if value["receipt_id"] in failures:
                            value["last_error"] = failures[value["receipt_id"]]
                    changed |= value != output
                    updated[key] = value
                effect.results = updated
            if changed:
                stored = await revision(db, job)
                values = outputs(applied)
                previous_attempt = await db.scalar(
                    select(ImportJobAttempt.id)
                    .where(
                        ImportJobAttempt.company_id == adapter.company,
                        ImportJobAttempt.revision_id == stored.id,
                    )
                    .order_by(ImportJobAttempt.id.desc())
                    .limit(1)
                )
                previous_results = {
                    row.record_id: row
                    for row in await db.scalars(
                        select(ImportRecordResult)
                        .where(
                            ImportRecordResult.company_id == adapter.company,
                            ImportRecordResult.attempt_id == previous_attempt,
                        )
                        .limit(200)
                    )
                }
                previous_messages: dict[uuid.UUID, list[dict[str, str]]] = {}
                if previous_results:
                    for issue in await db.scalars(
                        select(ImportRecordIssue)
                        .where(
                            ImportRecordIssue.company_id == adapter.company,
                            ImportRecordIssue.result_id.in_(
                                [row.id for row in previous_results.values()]
                            ),
                        )
                        .limit(20000)
                    ):
                        previous_messages.setdefault(issue.result_id, []).append(
                            {"field": issue.field, "code": issue.code, "message": issue.message}
                        )
                job.completed_count = sum(not value.get("pending") for value in values.values())
                job.state = "SUCCEEDED" if job.completed_count == job.record_count else "PARTIAL"
                job.row_version += 1
                job.updated_by = adapter.actor.user_id
                attempt = new(
                    ImportJobAttempt,
                    adapter,
                    revision_id=stored.id,
                    phase="IMPORT",
                    outcome=job.state,
                    finished_at=utcnow(),
                )
                db.add(attempt)
                await db.flush()
                for record in records:
                    value = values.get(record.logical_key, {})
                    previous_result = previous_results.get(record.id)
                    state = (
                        "APPLIED"
                        if value and not value.get("pending")
                        else "FAILED"
                        if value.get("last_error")
                        else "PENDING"
                        if value
                        else previous_result.status
                        if previous_result
                        else "SKIPPED"
                    )
                    result = new(
                        ImportRecordResult,
                        adapter,
                        attempt_id=attempt.id,
                        record_id=record.id,
                        status=state,
                        business_id=uuid.UUID(value["id"]) if state == "APPLIED" else None,
                    )
                    db.add(result)
                    await db.flush()
                    for message in (
                        value.get("last_error", [])
                        if value
                        else previous_messages.get(previous_result.id, [])
                        if previous_result
                        else []
                    ):
                        db.add(new(ImportRecordIssue, adapter, result_id=result.id, **message))
                evidence(db, adapter, job, "update")
            return progress(job, applied)

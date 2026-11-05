"""Bounded worker transactions reuse native commands; previews always roll back."""

import re
import uuid
from typing import Any

from billing_platform.actor_authorization import ActorAuthorizationProof
from billing_platform.authz import Grant, ScopePath
from billing_platform.bulk import selection_digest
from billing_platform.command_transaction import command_transaction
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import (
    BulkChangeSet,
    BulkChangeSetEffect,
    BulkJob,
    BulkJobDependency,
    BulkJobRecord,
)
from catalog.tasks.actor_authorization import require_job_actor, validate_proof
from catalog.tasks.bulk_access import (
    Evidence,
    native,
    readable_evidence,
    scoped_job,
    verify_pins,
    wire,
)
from catalog.tasks.bulk_identity import identity_digest
from catalog.tasks.bulk_jobs import audit, new, touch
from catalog.tasks.bulk_matching import prepare
from catalog.tasks.bulk_registry import Runtime
from catalog.tasks.field_context import load_field_context
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.policy_state import company_policy_state, policy_state

PERMISSION_CHUNKS = tuple(
    frozenset(sorted(CATALOG_PERMISSIONS)[start : start + 32])
    for start in range(0, len(CATALOG_PERMISSIONS), 32)
)
#: A reviewer's report carries column names and nothing else — no reason, no value, no policy.
#: Anything that is not a plausible field path is dropped rather than escaped (CLAUDE.md §5.8).
FIELD_PATH = re.compile(r"[a-z][a-z0-9_.]{0,127}")


class RowFailureError(Exception):
    def __init__(self, record_id: uuid.UUID, cause: Exception) -> None:
        self.record_id, self.cause = record_id, cause
        super().__init__("bulk record failed native validation")

    def fields(self) -> list[str]:
        """Which columns this row's reviewer has to change: schema refusals and domain ones.

        A domain refusal names its fields too (``ValidationFailedError(..., fields=...)``), and
        the report is the only place a bulk caller can read them. Without this, a reviewer
        holding a five-thousand-row file sees ``invalid_record`` and no column, which is the one
        outcome the field-naming refusals exist to avoid.
        """
        paths: tuple[str, ...]
        if isinstance(self.cause, PlatformError):
            paths = tuple(self.cause.extra.get("fields") or ())
        elif isinstance(self.cause, ValidationError):
            paths = tuple(
                ".".join(str(value) for value in error["loc"])
                for error in self.cause.errors(
                    include_input=False, include_context=False, include_url=False
                )
            )
        else:
            return []
        return sorted({path for path in paths if FIELD_PATH.fullmatch(path)})[:100]


class DependencyFailedError(ConflictError):
    """A selected record cannot run because its prerequisite did not commit."""


def terminal_state(job: BulkJob) -> str:
    if job.completed_count == job.record_count:
        return "SUCCEEDED"
    return "PARTIAL" if job.completed_count else "FAILED"


async def current_actor(
    db: AsyncSession,
    proofs: tuple[ActorAuthorizationProof, ...],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
) -> Actor:
    if len(proofs) != len(PERMISSION_CHUNKS):
        raise PermissionDeniedError(
            "bulk worker requires the complete current authorization proof set"
        )
    grants: list[Grant] = []
    for proof, requested in zip(proofs, PERMISSION_CHUNKS, strict=True):
        validate_proof(
            proof, tenant_id=tenant, company_id=company, user_id=user, permissions=requested
        )
        actor = await require_job_actor(
            db, proof, company_id=company, user_id=user, permissions=proof.permissions
        )
        grants.extend(actor.grants)
    return Actor(tenant_id=tenant, user_id=user, grants=tuple(grants))


async def group_records(
    db: AsyncSession, job: BulkJob, group_ids: set[uuid.UUID]
) -> list[BulkJobRecord]:
    return list(
        await db.scalars(
            select(BulkJobRecord)
            .where(
                BulkJobRecord.company_id == job.company_id,
                BulkJobRecord.job_id == job.id,
                BulkJobRecord.change_set_id.in_(group_ids),
            )
            .order_by(BulkJobRecord.ordinal)
            .limit(1001)
        )
    )


async def ancestors(db: AsyncSession, job: BulkJob, group: BulkChangeSet) -> list[BulkChangeSet]:
    found, pending = {group.id}, {group.id}
    for _ in range(32):
        children = select(BulkJobRecord.id).where(
            BulkJobRecord.company_id == job.company_id,
            BulkJobRecord.job_id == job.id,
            BulkJobRecord.change_set_id.in_(pending),
        )
        parent_rows = select(BulkJobDependency.parent_record_id).where(
            BulkJobDependency.company_id == job.company_id,
            BulkJobDependency.job_id == job.id,
            BulkJobDependency.child_record_id.in_(children),
        )
        ids = set(
            await db.scalars(
                select(BulkJobRecord.change_set_id).where(
                    BulkJobRecord.company_id == job.company_id,
                    BulkJobRecord.job_id == job.id,
                    BulkJobRecord.id.in_(parent_rows),
                )
            )
        )
        pending = ids - found
        if not pending:
            break
        found |= pending
    groups = list(
        await db.scalars(
            select(BulkChangeSet)
            .where(
                BulkChangeSet.company_id == job.company_id,
                BulkChangeSet.job_id == job.id,
                BulkChangeSet.id.in_(found),
            )
            .order_by(BulkChangeSet.ordinal)
        )
    )
    if sum(value.record_count for value in groups) > 1000:
        raise ValidationFailedError(
            "dependent preview exceeds 1000 commands; split the staged work"
        )
    return groups


async def frozen(runtime: Runtime, job: BulkJob) -> None:
    state = await policy_state(runtime.db, runtime.actor, runtime.company, lock=True)
    context = await load_field_context(
        runtime.db, runtime.actor, runtime.company, "catalog.bulk_job"
    )
    if state is None or state.generation != job.policy_generation:
        raise ConflictError("Catalog or Identity changed outside this job; review again")
    if context.source_version != job.source_version:
        if job.identity_digest != await identity_digest(runtime.db, runtime.company):
            raise ConflictError("Identity facts changed outside this job; review again")
        job.source_version = context.source_version


async def apply_records(
    runtime: Runtime,
    job: BulkJob,
    group: BulkChangeSet,
    rows: list[BulkJobRecord],
    results: dict[str, dict[str, Any]],
    *,
    reviewed: bool,
) -> list[dict[str, Any]]:
    captured = []
    byte_count = 0
    target_keys: set[str] = set()
    for stored in rows:
        if reviewed:
            await verify_pins(runtime.db, runtime.actor, runtime.company, stored.source_pins or [])
        with Evidence(runtime.db) as evidence:
            try:
                op, body, target, before = await prepare(
                    runtime, stored, job.mode, results, reviewed=reviewed
                )
            except IdentitySourceUnavailableError:
                raise
            except (PlatformError, ValidationError, ValueError, KeyError, TypeError) as exc:
                raise RowFailureError(stored.id, exc) from exc
            if stored.target_key is not None and not reviewed:
                if stored.target_key in target_keys:
                    raise ConflictError("duplicate target commands cannot be resolved by row order")
                target_keys.add(stored.target_key)
                duplicate = await runtime.db.scalar(
                    select(BulkJobRecord.id)
                    .where(
                        BulkJobRecord.company_id == job.company_id,
                        BulkJobRecord.job_id == job.id,
                        BulkJobRecord.id != stored.id,
                        BulkJobRecord.target_key == stored.target_key,
                        BulkJobRecord.state.in_(("VALID", "APPLIED")),
                    )
                    .limit(1)
                )
                if duplicate is not None:
                    raise ConflictError(
                        "duplicate target command requires an explicit combined change set"
                    )
            try:
                output = await op.call(
                    runtime, body, target, f"bulk:{job.id}:{group.logical_key}:{stored.logical_key}"
                )
            except IdentitySourceUnavailableError:
                raise
            except (PlatformError, ValidationError, ValueError) as exc:
                raise RowFailureError(stored.id, exc) from exc
            output["created"] = evidence.named_created()
            planned_ids = {
                key for result in results.values() for key in result.get("_created_ids", [])
            }
            output["_created_ids"] = sorted(str(key) for _, key in evidence.created)
            after = None
            if target is not None:
                current = await runtime.db.get(
                    op.model, uuid.UUID(output["id"]) if op.action == "ADJUST" else target
                )
                if current is not None:
                    after = native(current)
            else:
                created = [
                    row
                    for (table, _), row in evidence.rows.items()
                    if table == op.model.__tablename__ and (table, row.id) in evidence.created
                ]
                if len(created) == 1:
                    after = native(created[0])
                    output.setdefault("id", str(created[0].id))
            pins = [pin for pin in evidence.pins() if pin["id"] not in planned_ids]
            # Preview output is useful only when the entire dependency evidence is
            # readable. Native handlers still enforce all changed-field writes.
            await readable_evidence(runtime.db, runtime.actor, runtime.company, pins)
            results[stored.logical_key] = output
            captured.append(
                {
                    "id": stored.id,
                    "prepared": stored.prepared_input,
                    "target_id": stored.target_id,
                    "target_key": stored.target_key,
                    "expected_version": stored.expected_version,
                    "preview": {"before": before, "after": after, "changes": evidence.changes()},
                    "pins": pins,
                }
            )
            byte_count += len(
                canonical_json(
                    wire({"review": captured[-1], "result": output}), maximum_bytes=256 * 1024
                )
            )
            if byte_count > 8 * 1024 * 1024:
                raise ValidationFailedError("change-set evidence exceeds the 8 MiB review bound")
    return captured


async def finish_validation(db: AsyncSession, actor: Actor, job: BulkJob) -> None:
    pending = await db.scalar(
        select(BulkChangeSet.id)
        .where(
            BulkChangeSet.company_id == job.company_id,
            BulkChangeSet.job_id == job.id,
            BulkChangeSet.state == "STAGED",
        )
        .limit(1)
    )
    if pending is not None:
        return
    invalid = await db.scalar(
        select(func.count(BulkJobRecord.id)).where(
            BulkJobRecord.company_id == job.company_id,
            BulkJobRecord.job_id == job.id,
            BulkJobRecord.state.in_(("INVALID", "BLOCKED")),
        )
    )
    job.invalid_count = invalid or 0
    job.state = "FAILED" if invalid else "READY"
    if not invalid:
        prepared = list(
            (
                await db.execute(
                    select(
                        BulkJobRecord.logical_key,
                        BulkJobRecord.prepared_input,
                        BulkJobRecord.target_id,
                        BulkJobRecord.expected_version,
                    )
                    .where(
                        BulkJobRecord.company_id == job.company_id,
                        BulkJobRecord.job_id == job.id,
                        BulkJobRecord.state == "VALID",
                    )
                    .order_by(BulkJobRecord.ordinal)
                )
            ).all()
        )
        job.selection_digest = selection_digest(
            {
                "revision": job.revision,
                "input": job.input_hash,
                "selection": job.selected_keys,
                "generation": job.policy_generation,
                "source": job.source_version,
                "identity": job.identity_digest,
                "records": [
                    [key, value, str(target) if target else None, version]
                    for key, value, target, version in prepared
                ],
            }
        )


def error_code(exc: Exception) -> str:
    if isinstance(exc, PermissionDeniedError):
        return "permission_denied"
    if isinstance(exc, ConflictError):
        return "review_conflict"
    if isinstance(exc, NotFoundError):
        return "target_not_found"
    return "invalid_record"


async def step(
    factory: async_sessionmaker[AsyncSession],
    proofs: tuple[ActorAuthorizationProof, ...],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    job_id: uuid.UUID,
    secret: bytes,
) -> bool:
    async with command_transaction(
        factory, tenant_id=tenant, company_id=company, actor_id=user
    ) as db:
        await company_policy_state(db, tenant, company, lock=True)
        actor = await current_actor(db, proofs, tenant, company, user)
        job = await scoped_job(db, actor, company, job_id, lock=True, live=True)
        validating = job.state == "VALIDATING"
        if job.state not in {"VALIDATING", "QUEUED", "RUNNING"}:
            return False
        actor.require_scope(
            "catalog.bulk.manage" if validating else "catalog.bulk.commit",
            target=ScopePath(company_id=company),
        )
        runtime = Runtime(db, factory, actor, company, secret)
        await frozen(runtime, job)
        group = await db.scalar(
            select(BulkChangeSet)
            .where(
                BulkChangeSet.company_id == company,
                BulkChangeSet.job_id == job.id,
                BulkChangeSet.state == ("STAGED" if validating else "VALID"),
            )
            .order_by(BulkChangeSet.ordinal)
            .limit(1)
        )
        if group is None:
            if validating:
                await finish_validation(db, actor, job)
            else:
                job.state = terminal_state(job)
            touch(job, actor)
            audit(db, actor, job)
            return True
        if not validating and job.atomicity == "ATOMIC":
            groups = list(
                await db.scalars(
                    select(BulkChangeSet)
                    .where(
                        BulkChangeSet.company_id == company,
                        BulkChangeSet.job_id == job.id,
                        BulkChangeSet.state.in_(("VALID", "APPLIED")),
                    )
                    .order_by(BulkChangeSet.ordinal)
                )
            )
        else:
            groups = await ancestors(db, job, group)
        rows = await group_records(db, job, {value.id for value in groups})
        if len(rows) > 1000:
            raise ValidationFailedError("worker chunk exceeds command bounds")
        results: dict[str, dict[str, Any]] = {}
        effects = list(
            await db.scalars(
                select(BulkChangeSetEffect).where(
                    BulkChangeSetEffect.company_id == company,
                    BulkChangeSetEffect.job_id == job.id,
                    BulkChangeSetEffect.change_set_id.in_({value.id for value in groups}),
                )
            )
        )
        for effect in effects:
            results.update(effect.results)
        captured: list[dict[str, Any]] = []
        failed: Exception | None = None
        transaction = await db.begin_nested()
        try:
            for current in groups:
                if current.state == "APPLIED":
                    if not any(
                        effect.change_set_id == current.id
                        and effect.action_hash == current.action_hash
                        for effect in effects
                    ):
                        raise ConflictError("completed change-set evidence is unavailable")
                    continue
                if current.state not in {"STAGED", "VALID"} or (
                    not validating and current.id != group.id and job.atomicity != "ATOMIC"
                ):
                    raise DependencyFailedError("a required change set did not complete")
                current_rows = [row for row in rows if row.change_set_id == current.id]
                reviewed = not validating or current.id != group.id
                produced = await apply_records(
                    runtime, job, current, current_rows, results, reviewed=reviewed
                )
                if validating:
                    if current.id == group.id:
                        captured = produced
                else:
                    db.add(
                        new(
                            BulkChangeSetEffect,
                            actor,
                            company,
                            job_id=job.id,
                            change_set_id=current.id,
                            logical_key=current.logical_key,
                            accepted_revision=job.revision,
                            action_hash=current.action_hash,
                            results={
                                row.logical_key: results[row.logical_key] for row in current_rows
                            },
                            source_pins=[pin for item in produced for pin in item["pins"]],
                        )
                    )
                    current.state = "APPLIED"
                    applied = {entry["id"]: entry for entry in produced}
                    for row in current_rows:
                        row.state, row.error_code = "APPLIED", None
                        result = results[row.logical_key]
                        identities = {
                            key: result[key]
                            for key in ("id", "family_id", "item_id", "created")
                            if key in result
                        }
                        row.preview = {**applied[row.id]["preview"], "result": identities}
                        row.source_pins = applied[row.id]["pins"]
                    job.completed_count += len(current_rows)
            await current_actor(db, proofs, tenant, company, user)
            if validating:
                await transaction.rollback()
            else:
                await db.flush()
                await transaction.commit()
        except IdentitySourceUnavailableError:
            await transaction.rollback()
            raise
        except (
            RowFailureError,
            PlatformError,
            ValidationError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            failed = exc
            await transaction.rollback()
        # SAVEPOINT rollback expires modified ORM objects; reload before touching
        # durable review state. Domain rows, receipts and outbox writes are gone.
        await db.refresh(job)
        await db.refresh(group)
        current_rows = await group_records(db, job, {group.id})
        if failed is not None:
            failure_code = error_code(
                failed.cause if isinstance(failed, RowFailureError) else failed
            )
            affected = [group]
            if not validating and job.atomicity == "ATOMIC":
                affected = list(
                    await db.scalars(
                        select(BulkChangeSet).where(
                            BulkChangeSet.company_id == company,
                            BulkChangeSet.job_id == job.id,
                            BulkChangeSet.state == "VALID",
                            BulkChangeSet.logical_key.in_(job.selected_keys or []),
                        )
                    )
                )
                current_rows = await group_records(db, job, {value.id for value in affected})
            failed_group = next(
                (
                    row.change_set_id
                    for row in current_rows
                    if isinstance(failed, RowFailureError) and row.id == failed.record_id
                ),
                group.id,
            )
            for value in affected:
                value.state = (
                    ("INVALID" if validating else "FAILED")
                    if value.id == failed_group
                    else "BLOCKED"
                )
                value.error_code = (
                    failure_code if value.id == failed_group else "atomic_rolled_back"
                )
            for row in current_rows:
                row.state, row.error_code = ("INVALID" if validating else "FAILED"), failure_code
                if isinstance(failed, RowFailureError) and row.id == failed.record_id:
                    row.preview = {"error_fields": failed.fields()}
                elif isinstance(failed, RowFailureError):
                    row.state, row.error_code = "BLOCKED", "aggregate_rolled_back"
            if isinstance(failed, DependencyFailedError):
                group.state, group.error_code = "BLOCKED", "dependency_failed"
                for row in current_rows:
                    row.state, row.error_code = "BLOCKED", "dependency_failed"
            if not validating:
                job.invalid_count += len(current_rows)
                job.state = "PARTIAL" if job.completed_count else "FAILED"
                if job.on_error == "CONTINUE_INDEPENDENT" and job.atomicity != "ATOMIC":
                    job.state = "RUNNING"
        elif validating:
            group.state, group.error_code = "VALID", None
            snapshots = {entry["id"]: entry for entry in captured}
            for row in current_rows:
                entry = snapshots[row.id]
                row.prepared_input, row.preview, row.source_pins = (
                    entry["prepared"],
                    entry["preview"],
                    entry["pins"],
                )
                row.target_id, row.target_key, row.expected_version = (
                    entry["target_id"],
                    entry["target_key"],
                    entry["expected_version"],
                )
                row.state, row.error_code = "VALID", None
        else:
            state = await policy_state(db, actor, company)
            assert state is not None
            job.policy_generation, job.state = state.generation, "RUNNING"
        await db.flush()
        if validating:
            await finish_validation(db, actor, job)
        elif job.state == "RUNNING":
            remaining = await db.scalar(
                select(BulkChangeSet.id)
                .where(
                    BulkChangeSet.company_id == company,
                    BulkChangeSet.job_id == job.id,
                    BulkChangeSet.state == "VALID",
                )
                .limit(1)
            )
            if remaining is None:
                job.state = terminal_state(job)
        touch(job, actor)
        audit(db, actor, job)
        await current_actor(db, proofs, tenant, company, user)
        return True

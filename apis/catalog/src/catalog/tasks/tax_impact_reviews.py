"""Chunked background tax impact reviews; a release publishes against a COMPLETE report.

The synchronous preview evaluates at most 256 products. A company-wide or large-group release
is reviewed instead by ``python -m catalog.tasks.tax_review_worker``: each chunk replays the
stored release input inside a rolled-back savepoint, evaluates the next bounded page of affected
products and stores their non-complete results. The report is bound to the company policy
generation, Identity source version and business date it started at; any Catalog product or tax
change advances the generation, so a report that still matches describes exactly what is being
published, and a report that does not is marked STALE.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.models.classification import CatalogPolicyState
from catalog.models.tax import TaxRule
from catalog.models.tax_governance import TaxImpactFinding, TaxImpactReview, TaxRelease
from catalog.schemas import tax_governance as s
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import business_date

ENTITY = "catalog.tax_impact_review"
#: 16 products x 2 directions x 64 date boundaries stays inside the 2048-check bound.
MAX_CHUNK = 16
FAILURES = frozenset({"actor_denied", "invalid_release", "review_capacity"})


def audit(db: AsyncSession, review: TaxImpactReview, action: str, actor_id: uuid.UUID) -> None:
    event = audit_event(ENTITY, action)
    emit(
        db,
        tenant_id=review.tenant_id,
        aggregate_type=ENTITY,
        aggregate_id=review.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            entity_type=ENTITY,
            entity_id=review.id,
            actor_user_id=actor_id,
            company_id=review.company_id,
            category=category(ENTITY, action),
            changes={"status": {"changed": True}, "progress": {"changed": True}},
        ),
    )


def authorize(actor: Actor, company: uuid.UUID) -> None:
    for permission in ("tax_rule.publish", "tax_rule.manage"):
        actor.require_scope(permission, target=ScopePath(company_id=company))


async def checkpoint(access: ConfigurationAccess) -> tuple[int, Any]:
    context = await access.context(TaxRule)
    return context.source_version, business_date(context.company.timezone)


async def dry_run(
    access: ConfigurationAccess, state: CatalogPolicyState, body: s.ReleaseInput
) -> tuple[set[uuid.UUID], Any]:
    """Apply the release in a savepoint, validate schedules, and always roll back."""
    from catalog.tasks.tax_commands import TaxWork
    from catalog.tasks.tax_governance import apply_changes
    from catalog.tasks.tax_integrity import change_scopes

    work = TaxWork(access, state)
    savepoint = await access.db.begin_nested()
    try:
        await apply_changes(work, body)
        return await change_scopes(work)
    finally:
        await savepoint.rollback()
        access.tax_rows.clear()


async def start(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: s.ReleaseInput,
    key: str,
) -> CommandResult[s.ImpactReviewDetail]:
    from catalog.tasks.tax_governance import digest

    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        ENTITY + ".start",
        key,
        {"body": body.model_dump(mode="json")},
    )
    access: ConfigurationAccess | None = None
    state: CatalogPolicyState | None = None

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal access, state
        authorize(actor, company)
        access = ConfigurationAccess(db, actor, company)
        await access.context(TaxRelease, "tax_rule.manage")
        state = await policy_state(db, actor, company, lock=receipt is None)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert access is not None and state is not None
        generation = state.generation
        source_version, today = await checkpoint(access)
        # Fail fast on an invalid or stale release before any background work is queued.
        await dry_run(access, state, body)
        review = TaxImpactReview(
            id=uuid7(),
            tenant_id=actor.tenant_id,
            company_id=company,
            actor_user_id=actor.user_id,
            change_reason=body.change_reason,
            input_digest=digest(body),
            request=body.model_dump(mode="json"),
            change_count=len(body.changes),
            policy_generation=generation,
            source_version=source_version,
            business_date=today,
            status="PENDING",
            item_count=0,
            checked_count=0,
            finding_count=0,
            blocking_count=0,
            row_version=1,
            created_by=actor.user_id,
            updated_by=actor.user_id,
        )
        db.add(review)
        await db.flush()
        audit(db, review, "start", actor.user_id)
        return CommandReceipt(201, {"id": str(review.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> s.ImpactReviewDetail:
        return await read(db, actor, company, uuid.UUID(receipt["id"]))

    return await execute_idempotent(
        factory, identity, authorize=check, mutate=mutate, render=render
    )


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, review_id: uuid.UUID
) -> s.ImpactReviewDetail:
    actor.require_scope("tax_rule.read", target=ScopePath(company_id=company))
    review = await company_object(db, TaxImpactReview, review_id, company_id=company)
    return s.ImpactReviewDetail.model_validate(review)


async def findings(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    review_id: uuid.UUID,
    query: s.ImpactFindingQuery,
    secret: bytes,
) -> Page[s.ImpactFindingListItem]:
    for permission in ("tax_rule.read", "item.read"):
        actor.require_scope(permission, target=ScopePath(company_id=company))
    if query.q is not None:
        raise ValidationFailedError("impact findings support the blocking filter, not search")
    await company_object(db, TaxImpactReview, review_id, company_id=company)
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(TaxRelease)
    stmt = select(
        *(getattr(TaxImpactFinding, name) for name in s.ImpactFindingListItem.model_fields)
    ).where(TaxImpactFinding.company_id == company, TaxImpactFinding.review_id == review_id)
    if query.blocking is not None:
        stmt = stmt.where(TaxImpactFinding.blocking == query.blocking)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(TaxImpactFinding.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret, actor, company, ENTITY + ":" + str(review_id) + ":findings", context, query
        ),
        project=s.ImpactFindingListItem.model_validate,
    )


def finish(review: TaxImpactReview, status: str, reason: str | None = None) -> None:
    review.status, review.reason_code = status, reason
    review.completed_at = utcnow()


async def chunk(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    review_id: uuid.UUID,
    *,
    limit: int = MAX_CHUNK,
) -> TaxImpactReview:
    """Evaluate the next page of affected products; one bounded worker transaction.

    The caller supplies an actor resolved from fresh Identity proofs; nothing about the
    original requester's authority is stored on the review.
    """
    from catalog.tasks.tax_commands import TaxWork
    from catalog.tasks.tax_governance import apply_changes, digest
    from catalog.tasks.tax_integrity import affected_items, blocking, change_scopes, evaluate

    if type(limit) is not int or not 1 <= limit <= MAX_CHUNK:
        raise ValidationFailedError("impact review chunk size must be 1-16")
    state = await policy_state(db, actor, company, lock=True)
    assert state is not None
    review = await company_object(db, TaxImpactReview, review_id, company_id=company, lock=True)
    if review.actor_user_id != actor.user_id:
        raise PermissionDeniedError("impact review must run as its requester")
    if review.status != "PENDING":
        raise ConflictError("impact review is no longer pending")
    authorize(actor, company)
    access = ConfigurationAccess(db, actor, company)
    await access.context(TaxRelease, "tax_rule.manage")
    source_version, today = await checkpoint(access)
    review.row_version += 1
    review.updated_at, review.updated_by = utcnow(), actor.user_id
    if (state.generation, source_version, today) != (
        review.policy_generation,
        review.source_version,
        review.business_date,
    ):
        finish(review, "STALE", "policy_changed")
        audit(db, review, "stale", actor.user_id)
        await db.flush()
        return review
    body = s.ReleaseInput.model_validate(review.request)
    if digest(body) != review.input_digest:
        raise ConflictError("stored impact review input is inconsistent")
    work = TaxWork(access, state)
    results: list[tuple[uuid.UUID, str, s.ImpactItem]] = []
    failure: str | None = None
    page: list[tuple[uuid.UUID, str]] = []
    savepoint = await db.begin_nested()
    try:
        await apply_changes(work, body)
        scopes, start_date = await change_scopes(work)
        items = await affected_items(
            access, scopes, start_date, after=review.checkpoint_id, chunk=limit
        )
        page = [(item.id, item.status) for item in items]
        statuses = dict(page)
        impact = await evaluate(access, items, start_date, enforce=False)
        results = [(entry.item_id, statuses[entry.item_id], entry) for entry in impact.impact]
    except PermissionDeniedError:
        failure = "actor_denied"
    except (ConflictError, ValidationFailedError) as exc:
        failure = "review_capacity" if "exceeds" in str(exc) else "invalid_release"
    finally:
        await savepoint.rollback()
        access.tax_rows.clear()
    await db.refresh(review)
    if failure is not None:
        assert failure in FAILURES
        finish(review, "FAILED", failure)
        audit(db, review, "failed", actor.user_id)
        await db.flush()
        return review
    for item_id, item_status, entry in results:
        review.checked_count += 1
        if entry.status == "COMPLETE":
            continue
        stop = blocking(item_status, entry)
        db.add(
            TaxImpactFinding(
                id=uuid7(),
                tenant_id=review.tenant_id,
                company_id=company,
                review_id=review.id,
                item_id=item_id,
                direction=entry.direction,
                as_of=entry.as_of,
                status=entry.status,
                missing=list(entry.missing),
                blocking=stop,
                row_version=1,
                created_by=actor.user_id,
                updated_by=actor.user_id,
            )
        )
        review.finding_count += 1
        review.blocking_count += int(stop)
    review.item_count += len(page)
    if page:
        review.checkpoint_id = page[-1][0]
    if len(page) < limit:
        finish(review, "COMPLETE")
    audit(db, review, "chunk", actor.user_id)
    await db.flush()
    return review


async def fail(
    db: AsyncSession, company: uuid.UUID, review_id: uuid.UUID, version: int, reason: str
) -> None:
    """Stop a review whose requester's proof was refused; no actor authority is needed."""
    if reason not in FAILURES:
        raise ValueError("invalid private failure code")
    review = await company_object(db, TaxImpactReview, review_id, company_id=company, lock=True)
    if review.status != "PENDING" or review.row_version != version:
        return
    finish(review, "FAILED", reason)
    review.row_version += 1
    review.updated_at, review.updated_by = utcnow(), None
    audit(db, review, "failed", review.actor_user_id)
    await db.flush()


async def verify(work: Any, body: s.ReleaseCommit) -> TaxImpactReview:
    """The referenced report must be COMPLETE, unblocked and describe exactly this state."""
    from catalog.tasks.tax_governance import digest

    assert body.impact_review_id is not None
    access: ConfigurationAccess = work.access
    review = await company_object(
        access.db, TaxImpactReview, body.impact_review_id, company_id=access.company, lock=True
    )
    if review.status != "COMPLETE":
        raise ConflictError("impact review is not complete")
    if review.blocking_count:
        raise ConflictError("impact review found products the release would leave incomplete")
    source_version, today = await checkpoint(access)
    if (
        review.input_digest != digest(body)
        or review.policy_generation != work.state.generation
        or review.source_version != source_version
        or review.business_date != today
    ):
        raise ConflictError("tax release input, policy or business date changed; review again")
    return review

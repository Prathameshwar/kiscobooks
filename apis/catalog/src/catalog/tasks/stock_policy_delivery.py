"""Explicit Accounting-to-legacy-billing adapter; never infer an acknowledgement."""

import datetime as dt
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from voucher_execution.stock_policy import PolicyInspection, PolicyInspectionResult, PolicyManifest
from voucher_execution.stock_policy_transport import PolicyUnavailableError
from voucher_execution.stock_retirement import ActorProof

from catalog.domain.policy_release import (
    OPERATION_POLICY_AGGREGATE,
    RELEASE_AGGREGATE,
    ManifestEntry,
)
from catalog.models.releases import CatalogPolicyRelease
from catalog.schemas.acknowledgements import AcknowledgementEvent
from catalog.tasks.acknowledgements import ingest
from catalog.tasks.pricing_commands import PricingWork


class PolicyOwner(Protocol):
    async def inspect(self, request: PolicyInspection) -> PolicyInspectionResult: ...


@dataclass(frozen=True)
class Context:
    proof: ActorProof
    owner: PolicyOwner | None


_context: ContextVar[Context | None] = ContextVar("catalog_stock_policy_delivery", default=None)


@contextmanager
def request_scope(proof: ActorProof, owner: PolicyOwner | None) -> Iterator[None]:
    token = _context.set(Context(proof, owner))
    try:
        yield
    finally:
        _context.reset(token)


async def acknowledge(
    work: PricingWork,
    release: CatalogPolicyRelease,
    entries: Sequence[ManifestEntry],
    defaults: Mapping[str, uuid.UUID | None],
    *,
    today: dt.date,
) -> None:
    context = _context.get()
    if context is None or context.owner is None or release.effective_date > today:
        return
    manifest = PolicyManifest.model_validate(
        {
            "locations": [
                {"warehouse_id": row.warehouse_id, "revision": row.revision, "flags": row.flags}
                for row in entries
            ],
            "defaults": dict(defaults),
        }
    )
    if manifest.digest() != release.manifest_digest:
        raise ConflictError("native policy inspection must name the exact published manifest")
    request = PolicyInspection(
        check_id=uuid7(),
        tenant_id=work.actor.tenant_id,
        company_id=work.company,
        actor_user_id=work.actor.user_id,
        release_id=release.id,
        release_revision=release.revision,
        effective_date=release.effective_date,
        manifest=manifest,
        authority=context.proof,
    )
    try:
        result = await context.owner.inspect(request)
    except PolicyUnavailableError:
        return  # An unavailable owner supplies no acknowledgement: delivery remains pending.
    if (
        result.check_id != request.check_id
        or result.request_hash != request.digest()
        or result.issued_at > utcnow() + dt.timedelta(seconds=5)
        or result.expires_at <= utcnow() + dt.timedelta(seconds=5)
    ):
        raise ConflictError("native policy inspection differs from the current release")
    if result.result == "PENDING":
        return
    # Only this adapter maps verified native Accounting implementation evidence to
    # the existing wire consumer. The caller and payload cannot choose a consumer.
    for aggregate, identity, revision in (
        (RELEASE_AGGREGATE, release.id, release.revision),
        *((OPERATION_POLICY_AGGREGATE, row.warehouse_id, row.revision) for row in entries),
    ):
        await ingest(
            work.db,
            message_id=request.check_id,
            consumer="billing",
            companies={request.tenant_id: frozenset({request.company_id})},
            event=AcknowledgementEvent(
                tenant_id=request.tenant_id,
                company_id=request.company_id,
                release_id=release.id,
                release_revision=release.revision,
                aggregate=aggregate,
                aggregate_id=identity,
                enforced_revision=revision,
                result=result.result,
                reason_code=result.reason,
                acknowledged_at=result.issued_at,
            ),
        )

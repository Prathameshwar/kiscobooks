"""Native Accounting adapter for current, coordinated location retirement."""

import datetime as dt
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PlatformError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.retirement_transport import RetirementUnavailableError
from voucher_execution.stock_retirement import (
    ActorProof,
    RetirementEvidence,
    RetirementRelease,
    RetirementRequest,
)

from catalog.domain.sources import SourceUnavailableError
from catalog.models.stock_source import (
    RETIREMENT_CHECKS,
    RETIREMENT_COMMAND,
    RetirementClearance,
    StockSourceFence,
)
from catalog.models.warehouses import Warehouse, WarehouseBin
from catalog.tasks.policy_state import company_policy_state

COMMAND_HASH = RETIREMENT_COMMAND
logger = logging.getLogger(__name__)


class RetirementOwner(Protocol):
    async def check(self, request: RetirementRequest) -> RetirementEvidence: ...
    async def release(self, request: RetirementRelease) -> None: ...


@dataclass
class Context:
    actor: Actor
    proof: ActorProof
    accounting: RetirementOwner | None
    vouchers: RetirementOwner | None
    releases: list[RetirementRelease] = field(default_factory=list)


_context: ContextVar[Context | None] = ContextVar("catalog_stock_retirement", default=None)


@asynccontextmanager
async def request_scope(
    actor: Actor,
    proof: ActorProof,
    accounting: RetirementOwner | None,
    vouchers: RetirementOwner | None,
) -> AsyncIterator[None]:
    context = Context(actor, proof, accounting, vouchers)
    token = _context.set(context)
    try:
        yield
    finally:
        _context.reset(token)
        if context.vouchers is not None:
            for lease in context.releases:
                try:
                    await context.vouchers.release(lease)
                except PlatformError:
                    # Never replace a committed command result with cleanup failure.
                    # The retained owner lease expires after at most thirty seconds.
                    logger.warning("Stock retirement write-fence release will expire safely")


def require_evidence(evidence: RetirementEvidence, request: RetirementRequest, owner: str) -> None:
    now = utcnow()
    if (
        evidence.owner != owner
        or evidence.check_id != request.check_id
        or evidence.request_hash != request.digest()
        or evidence.issued_at > now + dt.timedelta(seconds=5)
        or evidence.expires_at <= now + dt.timedelta(seconds=5)
    ):
        raise SourceUnavailableError("current stock retirement evidence could not be verified")
    if evidence.result == "UNAVAILABLE":
        raise SourceUnavailableError("the stock owner is not ready to check this location")
    if evidence.result == "BLOCKED":
        messages = {
            "STOCK_ON_HAND": "this location still has physical stock or carrying value",
            "OPEN_TRANSFER": "complete or reverse the location's incoming and outgoing transfers",
            "PENDING_DOCUMENT": (
                "complete, cancel or reassign pending stock documents "
                "before retiring this location"
            ),
        }
        raise ConflictError(
            messages.get(evidence.reason or "", "this location is not clear to retire")
        )


async def owner_check(owner: RetirementOwner, request: RetirementRequest) -> RetirementEvidence:
    try:
        return await owner.check(request)
    except RetirementUnavailableError as exc:
        raise SourceUnavailableError(
            "current stock retirement checks are unavailable; retry after the owners recover"
        ) from exc


async def check(
    db: AsyncSession, actor: Actor, row: Warehouse | WarehouseBin
) -> RetirementClearance:
    context = _context.get()
    if (
        context is None
        or context.accounting is None
        or context.vouchers is None
        or (context.actor.tenant_id, context.actor.user_id) != (actor.tenant_id, actor.user_id)
    ):
        raise SourceUnavailableError("configure the native stock owners before retiring a location")
    existing = db.info.get(RETIREMENT_CHECKS, {}).get((row.__tablename__, row.id))
    if isinstance(existing, RetirementClearance) and existing.expires_at > utcnow():
        return existing
    digest = db.info.get(COMMAND_HASH)
    if not isinstance(digest, str):
        raise SourceUnavailableError("stock retirement needs its reviewed command identity")
    await company_policy_state(db, actor.tenant_id, row.company_id, lock=True)
    live = await db.scalar(
        select(StockSourceFence.id)
        .where(
            StockSourceFence.company_id == row.company_id,
            StockSourceFence.closed_at.is_(None),
            StockSourceFence.expires_at > utcnow(),
            or_(
                StockSourceFence.facts["purpose"].as_string().is_(None),
                StockSourceFence.facts["purpose"].as_string() != "REPORT",
            ),
        )
        .limit(1)
    )
    if live is not None:
        raise ConflictError("stock posting is using these definitions; retry after it completes")
    body = RetirementRequest(
        check_id=uuid7(),
        tenant_id=actor.tenant_id,
        company_id=row.company_id,
        actor_user_id=actor.user_id,
        warehouse_id=row.id if isinstance(row, Warehouse) else row.warehouse_id,
        bin_id=row.id if isinstance(row, WarehouseBin) else None,
        expected_version=row.row_version,
        command_hash=digest,
        authority=context.proof,
    )
    documents = await owner_check(context.vouchers, body)
    require_evidence(documents, body, "vouchers")
    assert documents.fence_id is not None
    context.releases.append(
        RetirementRelease(
            tenant_id=body.tenant_id,
            company_id=body.company_id,
            check_id=body.check_id,
            fence_id=documents.fence_id,
        )
    )
    stock = await owner_check(context.accounting, body)
    require_evidence(stock, body, "accounting")
    clearance = RetirementClearance(
        tenant_id=actor.tenant_id,
        company_id=row.company_id,
        table_name="warehouse" if isinstance(row, Warehouse) else "warehouse_bin",
        object_id=row.id,
        expected_version=row.row_version,
        check_id=body.check_id,
        checked_at=stock.issued_at,
        expires_at=min(documents.expires_at, stock.expires_at) - dt.timedelta(seconds=5),
    )
    db.info.setdefault(RETIREMENT_CHECKS, {})[(row.__tablename__, row.id)] = clearance
    return clearance

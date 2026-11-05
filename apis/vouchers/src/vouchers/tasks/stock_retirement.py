"""NoPendingDocument checks and bounded write leases under the common company lock."""

import datetime as dt

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.retirement_transport import RetirementUnavailableError
from voucher_execution.stock_retirement import (
    RetirementEvidence,
    RetirementRelease,
    RetirementRequest,
)

from vouchers.models import core as m
from vouchers.models.stock import VoucherStockDetail
from vouchers.models.stock_retirement import StockRetirementFence


async def lock(db: AsyncSession, request: RetirementRequest | RetirementRelease) -> None:
    row = await db.scalar(
        select(m.VoucherCompanyGuard)
        .where(
            m.VoucherCompanyGuard.company_id == request.company_id,
        )
        .with_for_update()
    )
    if row is None:
        raise RetirementUnavailableError(
            "initialize Vouchers sources before checking stock retirement"
        )


def audit(db: AsyncSession, row: StockRetirementFence, action: str) -> None:
    event = "vouchers.stock_retirement_fence." + action
    emit(
        db,
        tenant_id=row.tenant_id,
        aggregate_type="vouchers.stock_retirement_fence",
        aggregate_id=row.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="system",
            entity_type="vouchers.stock_retirement_fence",
            entity_id=row.id,
            actor_user_id=row.actor_user_id,
            company_id=row.company_id,
        ),
    )


async def pending(db: AsyncSession, request: RetirementRequest) -> bool:
    endpoint = [VoucherStockDetail.warehouse_id == request.warehouse_id]
    destination = [VoucherStockDetail.destination_warehouse_id == request.warehouse_id]
    if request.bin_id is not None:
        endpoint.append(VoucherStockDetail.bin_id == request.bin_id)
        destination.append(VoucherStockDetail.destination_bin_id == request.bin_id)
    location = or_(and_(*endpoint), and_(*destination))
    document = (
        select(m.Voucher.id)
        .join(
            m.VoucherRevision,
            and_(
                m.VoucherRevision.company_id == m.Voucher.company_id,
                m.VoucherRevision.voucher_id == m.Voucher.id,
                m.VoucherRevision.revision_number == m.Voucher.current_revision,
            ),
        )
        .join(
            VoucherStockDetail,
            and_(
                VoucherStockDetail.company_id == m.VoucherRevision.company_id,
                VoucherStockDetail.revision_id == m.VoucherRevision.id,
            ),
        )
        .where(
            m.Voucher.company_id == request.company_id,
            location,
            m.Voucher.status.not_in(("POSTED", "REVERSED", "CANCELLED", "DECLINED", "EXPIRED")),
        )
        .limit(1)
    )
    if await db.scalar(document) is not None:
        return True
    operation = (
        select(m.VoucherOperation.id)
        .join(
            VoucherStockDetail,
            and_(
                VoucherStockDetail.company_id == m.VoucherOperation.company_id,
                VoucherStockDetail.revision_id == m.VoucherOperation.revision_id,
            ),
        )
        .where(
            m.VoucherOperation.company_id == request.company_id,
            location,
            m.VoucherOperation.status == "PENDING",
            m.VoucherOperation.purpose.in_(("POST", "REVERSE")),
        )
        .limit(1)
    )
    return await db.scalar(operation) is not None


def evidence(row: StockRetirementFence) -> RetirementEvidence:
    return RetirementEvidence(
        owner="vouchers",
        check_id=row.check_id,
        request_hash=row.request_hash,
        issued_at=row.created_at,
        expires_at=row.expires_at,
        fence_id=row.id,
        result="CLEARED",
    )


async def acquire(db: AsyncSession, body: RetirementRequest, actor: Actor) -> RetirementEvidence:
    if (actor.tenant_id, actor.user_id) != (
        body.tenant_id,
        body.actor_user_id,
    ) or actor.impersonation_id:
        raise PermissionDeniedError("retirement requires its original scoped administrator")
    actor.require_scope(
        "warehouse_bin.manage" if body.bin_id else "warehouse.deactivate",
        target=ScopePath(company_id=body.company_id),
    )
    await lock(db, body)
    previous = await db.scalar(
        select(StockRetirementFence)
        .where(
            StockRetirementFence.company_id == body.company_id,
            StockRetirementFence.check_id == body.check_id,
        )
        .with_for_update()
    )
    if previous is not None:
        if (
            previous.request_hash != body.digest()
            or previous.closed_at is not None
            or previous.expires_at <= utcnow()
        ):
            raise ConflictError("retirement check has changed, expired or already completed")
        return evidence(previous)
    now = utcnow()
    if await pending(db, body):
        return RetirementEvidence(
            owner="vouchers",
            check_id=body.check_id,
            request_hash=body.digest(),
            issued_at=now,
            expires_at=now + dt.timedelta(seconds=5),
            result="BLOCKED",
            reason="PENDING_DOCUMENT",
        )
    row = StockRetirementFence(
        id=uuid7(),
        tenant_id=body.tenant_id,
        company_id=body.company_id,
        created_at=now,
        updated_at=now,
        created_by=actor.user_id,
        updated_by=actor.user_id,
        row_version=1,
        check_id=body.check_id,
        actor_user_id=actor.user_id,
        warehouse_id=body.warehouse_id,
        bin_id=body.bin_id,
        request_hash=body.digest(),
        expires_at=now + dt.timedelta(seconds=30),
        closed_at=None,
    )
    db.add(row)
    await db.flush()
    audit(db, row, "acquire")
    return evidence(row)


async def release(db: AsyncSession, body: RetirementRelease) -> None:
    await lock(db, body)
    row = await db.scalar(
        select(StockRetirementFence)
        .where(
            StockRetirementFence.company_id == body.company_id,
            StockRetirementFence.check_id == body.check_id,
            StockRetirementFence.id == body.fence_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ConflictError("retirement release does not match its retained fence")
    if row.closed_at is None:
        row.closed_at = utcnow()
        row.row_version += 1
        audit(db, row, "release")

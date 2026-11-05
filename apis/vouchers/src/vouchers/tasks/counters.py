"""Counter lifecycle with server-derived cashier and posted-tender totals."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.models.counter import (
    CheckoutCounter,
    CounterCashEvent,
    CounterOperator,
    CounterOutlet,
    CounterSession,
    VoucherCounterContext,
)
from vouchers.schemas.counters import (
    CashMovement,
    CounterCreate,
    MasterStatusUpdate,
    OperatorCreate,
    OperatorStatusUpdate,
    OutletCreate,
    SessionClose,
    SessionOpen,
)
from vouchers.tasks.access import authorize
from vouchers.tasks.common import audit, expected, get, values


async def outlet_create(db: AsyncSession, current: Access, body: OutletCreate) -> CounterOutlet:
    duplicate = await db.scalar(
        select(CounterOutlet.id).where(
            CounterOutlet.company_id == current.context.company_id, CounterOutlet.code == body.code
        )
    )
    if duplicate is not None:
        raise ConflictError("outlet code is already in use")
    row = CounterOutlet(**values(current), code=body.code, name=body.name, status="ACTIVE")
    db.add(row)
    audit(db, current, "counter_outlet", row.id, "create")
    await db.flush()
    return row


async def counter_create(db: AsyncSession, current: Access, body: CounterCreate) -> CheckoutCounter:
    outlet = await get(db, current, CounterOutlet, body.outlet_id)
    if outlet.status != "ACTIVE":
        raise ConflictError("outlet is inactive")
    duplicate = await db.scalar(
        select(CheckoutCounter.id).where(
            CheckoutCounter.company_id == current.context.company_id,
            CheckoutCounter.outlet_id == body.outlet_id,
            CheckoutCounter.code == body.code,
        )
    )
    if duplicate is not None:
        raise ConflictError("counter code is already in use at this outlet")
    row = CheckoutCounter(
        **values(current), outlet_id=body.outlet_id, code=body.code, name=body.name, status="ACTIVE"
    )
    db.add(row)
    audit(db, current, "checkout_counter", row.id, "create")
    await db.flush()
    return row


async def operator_create(
    db: AsyncSession, current: Access, counter_id: uuid.UUID, body: OperatorCreate
) -> CounterOperator:
    await get(db, current, CheckoutCounter, counter_id)
    existing = await db.scalar(
        select(CounterOperator.id).where(
            CounterOperator.company_id == current.context.company_id,
            CounterOperator.counter_id == counter_id,
            CounterOperator.user_id == body.user_id,
        )
    )
    if existing is not None:
        raise ConflictError("counter operator is already assigned")
    row = CounterOperator(
        **values(current), counter_id=counter_id, user_id=body.user_id, status="ACTIVE"
    )
    db.add(row)
    audit(
        db,
        current,
        "counter_operator",
        row.id,
        "assign",
        changes={"counter_id": str(counter_id), "user_id": str(body.user_id), "status": "ACTIVE"},
    )
    await db.flush()
    return row


async def operator_status(
    db: AsyncSession,
    current: Access,
    counter_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OperatorStatusUpdate,
) -> CounterOperator:
    await get(db, current, CheckoutCounter, counter_id)
    row = await db.scalar(
        select(CounterOperator)
        .where(
            CounterOperator.company_id == current.context.company_id,
            CounterOperator.counter_id == counter_id,
            CounterOperator.user_id == user_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ConflictError("counter operator is not assigned")
    expected(row, body.expected_version)
    if row.status != body.status:
        row.status = body.status
        row.row_version += 1
        row.updated_by = current.actor.user_id
        audit(
            db,
            current,
            "counter_operator",
            row.id,
            "status",
            reason=body.reason,
            changes={"status": body.status},
        )
    return row


async def assert_operator(
    db: AsyncSession, current: Access, counter_id: uuid.UUID, *, lock: bool = True
) -> None:
    statement = (
        select(CounterOperator.id)
        .where(
            CounterOperator.company_id == current.context.company_id,
            CounterOperator.counter_id == counter_id,
            CounterOperator.user_id == current.actor.user_id,
            CounterOperator.status == "ACTIVE",
        )
        .limit(1)
    )
    assigned = await db.scalar(statement.with_for_update() if lock else statement)
    if assigned is None:
        raise PermissionDeniedError("operator is not assigned to this counter")


async def outlet_status(
    db: AsyncSession, current: Access, outlet_id: uuid.UUID, body: MasterStatusUpdate
) -> CounterOutlet:
    outlet = await get(db, current, CounterOutlet, outlet_id, lock=True)
    expected(outlet, body.expected_version)
    if outlet.status == body.status:
        return outlet
    if body.status == "INACTIVE":
        opened = await db.scalar(
            select(CounterSession.id)
            .join(CheckoutCounter, CheckoutCounter.id == CounterSession.counter_id)
            .where(
                CounterSession.company_id == current.context.company_id,
                CheckoutCounter.company_id == current.context.company_id,
                CheckoutCounter.outlet_id == outlet.id,
                CounterSession.status == "OPEN",
            )
            .limit(1)
        )
        if opened is not None:
            raise ConflictError("close outlet counter sessions before deactivation")
    outlet.status = body.status
    outlet.row_version += 1
    outlet.updated_by = current.actor.user_id
    audit(db, current, "counter_outlet", outlet.id, "status")
    return outlet


async def counter_status(
    db: AsyncSession, current: Access, counter_id: uuid.UUID, body: MasterStatusUpdate
) -> CheckoutCounter:
    counter = await get(db, current, CheckoutCounter, counter_id, lock=True)
    expected(counter, body.expected_version)
    if counter.status == body.status:
        return counter
    if body.status == "INACTIVE":
        opened = await db.scalar(
            select(CounterSession.id)
            .where(
                CounterSession.company_id == current.context.company_id,
                CounterSession.counter_id == counter.id,
                CounterSession.status == "OPEN",
            )
            .limit(1)
        )
        if opened is not None:
            raise ConflictError("close the counter session before deactivation")
    else:
        outlet = await get(db, current, CounterOutlet, counter.outlet_id)
        if outlet.status != "ACTIVE":
            raise ConflictError("counter cannot be activated under an inactive outlet")
    counter.status = body.status
    counter.row_version += 1
    counter.updated_by = current.actor.user_id
    audit(db, current, "checkout_counter", counter.id, "status")
    return counter


async def session_open(db: AsyncSession, current: Access, body: SessionOpen) -> CounterSession:
    if body.currency != current.context.base_currency:
        raise ValidationFailedError("counter cash uses the company base currency")
    counter = await get(db, current, CheckoutCounter, body.counter_id, lock=True)
    await assert_operator(db, current, counter.id)
    outlet = await get(db, current, CounterOutlet, counter.outlet_id)
    if counter.status != "ACTIVE" or outlet.status != "ACTIVE":
        raise ConflictError("counter or outlet is inactive")
    active = await db.scalar(
        select(CounterSession.id)
        .where(
            CounterSession.company_id == current.context.company_id,
            CounterSession.counter_id == counter.id,
            CounterSession.status == "OPEN",
        )
        .limit(1)
    )
    if active is not None:
        raise ConflictError("counter already has an open session")
    row = CounterSession(
        **values(current),
        counter_id=counter.id,
        status="OPEN",
        currency=body.currency,
        opened_at=utcnow(),
        opened_by=current.actor.user_id,
        opening_cash=body.opening_cash,
    )
    db.add(row)
    audit(db, current, "counter_session", row.id, "open")
    await db.flush()
    return row


async def cash_movement(
    db: AsyncSession, current: Access, session_id: uuid.UUID, body: CashMovement
) -> CounterCashEvent:
    shift = await get(db, current, CounterSession, session_id, lock=True)
    expected(shift, body.expected_version)
    if shift.status != "OPEN" or shift.opened_by != current.actor.user_id:
        raise ConflictError("counter session is not open for this cashier")
    await assert_operator(db, current, shift.counter_id)
    voucher = await get(db, current, m.Voucher, body.source_voucher_id)
    revision = await get(db, current, m.VoucherRevision, body.source_revision_id)
    if revision.voucher_id != voucher.id:
        raise ValidationFailedError("cash movement source revision differs from voucher")
    kind = await get(db, current, m.VoucherType, voucher.type_id)
    if kind.kind not in {"PAYMENT", "RECEIPT"}:
        raise ValidationFailedError("drawer movement needs a money voucher source")
    if kind.kind == "PAYMENT" and body.direction != "OUT":
        raise ValidationFailedError("payment can only remove drawer cash")
    if kind.kind == "RECEIPT" and body.direction != "IN":
        raise ValidationFailedError("receipt can only add drawer cash")
    posted = await db.scalar(
        select(m.VoucherOperation.id)
        .where(
            m.VoucherOperation.company_id == current.context.company_id,
            m.VoucherOperation.revision_id == revision.id,
            m.VoucherOperation.purpose == "POST",
            m.VoucherOperation.status == "COMMITTED",
        )
        .limit(1)
    )
    if posted is None:
        raise ConflictError("cash movement source is not posted")
    attached = await db.scalar(
        select(VoucherCounterContext.id)
        .where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.revision_id == revision.id,
        )
        .limit(1)
    )
    if attached is not None:
        raise ConflictError("source voucher is already attached to a counter session")
    cash_tender = await db.scalar(
        select(func.coalesce(func.sum(m.VoucherTender.amount), 0)).where(
            m.VoucherTender.company_id == current.context.company_id,
            m.VoucherTender.revision_id == revision.id,
            m.VoucherTender.mode == "CASH",
        )
    )
    if Decimal(cash_tender or 0) != body.amount:
        raise ValidationFailedError("drawer movement must match the posted cash tender")
    row = CounterCashEvent(
        **values(current),
        session_id=shift.id,
        event_key=body.event_key,
        source_voucher_id=voucher.id,
        source_revision_id=revision.id,
        direction=body.direction,
        reason=body.reason,
        amount=body.amount,
        currency=shift.currency,
        occurred_at=utcnow(),
        operator_id=current.actor.user_id,
    )
    db.add(row)
    shift.row_version += 1
    audit(db, current, "counter_cash_event", row.id, "create")
    await db.flush()
    return row


async def expected_cash(db: AsyncSession, current: Access, shift: CounterSession) -> Decimal:
    events = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (CounterCashEvent.direction == "IN", CounterCashEvent.amount),
                        else_=-CounterCashEvent.amount,
                    )
                ),
                0,
            )
        ).where(
            CounterCashEvent.company_id == current.context.company_id,
            CounterCashEvent.session_id == shift.id,
        )
    )
    posted = exists(
        select(m.VoucherOperation.id).where(
            m.VoucherOperation.company_id == current.context.company_id,
            m.VoucherOperation.revision_id == m.VoucherTender.revision_id,
            m.VoucherOperation.purpose == "POST",
            m.VoucherOperation.status == "COMMITTED",
        )
    )
    tenders = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            m.VoucherType.kind.in_(["PAYMENT", "CREDIT_NOTE"]),
                            -m.VoucherTender.amount,
                        ),
                        else_=m.VoucherTender.amount,
                    )
                ),
                0,
            )
        )
        .select_from(VoucherCounterContext)
        .join(m.VoucherTender, m.VoucherTender.revision_id == VoucherCounterContext.revision_id)
        .join(m.VoucherRevision, m.VoucherRevision.id == VoucherCounterContext.revision_id)
        .join(m.Voucher, m.Voucher.id == m.VoucherRevision.voucher_id)
        .join(m.VoucherType, m.VoucherType.id == m.Voucher.type_id)
        .where(
            VoucherCounterContext.company_id == current.context.company_id,
            m.VoucherTender.company_id == current.context.company_id,
            m.VoucherRevision.company_id == current.context.company_id,
            m.Voucher.company_id == current.context.company_id,
            m.VoucherType.company_id == current.context.company_id,
            VoucherCounterContext.session_id == shift.id,
            m.VoucherTender.mode == "CASH",
            posted,
        )
    )
    return shift.opening_cash + Decimal(events or 0) + Decimal(tenders or 0)


async def session_close(
    db: AsyncSession, current: Access, session_id: uuid.UUID, body: SessionClose
) -> CounterSession:
    shift = await get(db, current, CounterSession, session_id, lock=True)
    expected(shift, body.expected_version)
    if shift.status != "OPEN":
        raise ConflictError("counter session is not open")
    pending = await db.scalar(
        select(m.VoucherOperation.id)
        .select_from(VoucherCounterContext)
        .join(
            m.VoucherOperation, m.VoucherOperation.revision_id == VoucherCounterContext.revision_id
        )
        .where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.session_id == shift.id,
            m.VoucherOperation.status == "PENDING",
        )
        .limit(1)
    )
    if pending is not None:
        raise ConflictError("counter posting is still pending")
    unresolved = await db.scalar(
        select(VoucherCounterContext.id)
        .select_from(VoucherCounterContext)
        .join(m.VoucherRevision, m.VoucherRevision.id == VoucherCounterContext.revision_id)
        .join(m.Voucher, m.Voucher.id == m.VoucherRevision.voucher_id)
        .where(
            VoucherCounterContext.company_id == current.context.company_id,
            VoucherCounterContext.session_id == shift.id,
            m.Voucher.status == "ISSUED",
            exists(
                select(m.VoucherTender.id).where(
                    m.VoucherTender.revision_id == m.VoucherRevision.id
                )
            ),
            ~exists(
                select(m.VoucherOperation.id).where(
                    m.VoucherOperation.revision_id == m.VoucherRevision.id,
                    m.VoucherOperation.purpose == "POST",
                    m.VoucherOperation.status.in_(["COMMITTED", "REJECTED", "CANCELLED"]),
                )
            ),
        )
        .limit(1)
    )
    if unresolved is not None:
        raise ConflictError("issued counter tender has no terminal posting result")
    expected_amount = await expected_cash(db, current, shift)
    variance = body.counted_cash - expected_amount
    if variance != 0 or shift.opened_by != current.actor.user_id:
        authorize(current, "counter.supervise")
        if shift.opened_by == current.actor.user_id:
            raise PermissionDeniedError("cashier cannot approve their own cash variance")
        if not body.reason or not body.reason.strip():
            raise ValidationFailedError("supervised closure requires an approval reason")
    else:
        await assert_operator(db, current, shift.counter_id)
    shift.status = "CLOSED"
    shift.closed_at = utcnow()
    shift.closed_by = current.actor.user_id
    shift.counted_cash = body.counted_cash
    shift.expected_cash = expected_amount
    shift.variance = variance
    shift.close_reason = body.reason
    shift.row_version += 1
    audit(db, current, "counter_session", shift.id, "close")
    await db.flush()
    return shift


async def session_detail(
    db: AsyncSession, current: Access, session_id: uuid.UUID
) -> dict[str, Any]:
    shift = await get(db, current, CounterSession, session_id)
    target = ScopePath(company_id=current.context.company_id)
    if not (
        current.actor.allows_scope("vouchers.counter.read", target=target)
        or current.actor.allows_scope("vouchers.counter.supervise", target=target)
    ):
        authorize(current, "counter.operate")
        if shift.opened_by != current.actor.user_id:
            raise PermissionDeniedError("counter session belongs to another cashier")
        await assert_operator(db, current, shift.counter_id, lock=False)
    return {
        "id": shift.id,
        "company_id": shift.company_id,
        "counter_id": shift.counter_id,
        "status": shift.status,
        "currency": shift.currency,
        "opening_cash": shift.opening_cash,
        "expected_cash": shift.expected_cash
        if shift.status == "CLOSED"
        else await expected_cash(db, current, shift),
        "counted_cash": shift.counted_cash,
        "variance": shift.variance,
        "opened_by": shift.opened_by,
        "closed_by": shift.closed_by,
        "row_version": shift.row_version,
    }

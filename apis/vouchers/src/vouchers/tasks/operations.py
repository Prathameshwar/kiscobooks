"""Terminal results are immutable; a lost acknowledgment never creates a new identity."""

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.domain.configuration import digest
from vouchers.events.execution import ExecutionResult
from vouchers.models import core as m


async def apply_result(db: AsyncSession, result: ExecutionResult) -> m.VoucherOperation:
    # Same lock order as document/configuration commands: company, operation, voucher.
    await db.scalar(
        select(m.VoucherCompanyGuard)
        .where(m.VoucherCompanyGuard.company_id == result.company_id)
        .with_for_update()
    )
    operation = await db.scalar(
        select(m.VoucherOperation)
        .where(
            m.VoucherOperation.company_id == result.company_id,
            m.VoucherOperation.id == result.operation_id,
        )
        .with_for_update()
    )
    if operation is None or operation.tenant_id != result.tenant_id:
        raise ConflictError("unknown execution operation")
    for field in ("execution_id", "content_hash", "configuration_hash", "request_hash"):
        if getattr(operation, field) != getattr(result, field):
            raise ConflictError("execution receipt identity differs")
    wire = result.model_dump(mode="json")
    if operation.status in {"COMMITTED", "REJECTED", "CANCELLED"}:
        if operation.result is None or digest(operation.result) != digest(wire):
            raise ConflictError("terminal execution result cannot change")
        return operation
    if result.outcome == "PENDING":
        return operation
    if result.outcome == "COMMITTED":
        target_status = "REVERSED" if operation.purpose == "REVERSE" else "POSTED"
        voucher = await db.scalar(
            select(m.Voucher)
            .where(m.Voucher.company_id == result.company_id, m.Voucher.id == operation.voucher_id)
            .with_for_update()
        )
        if voucher is None:
            raise ConflictError("execution voucher is unavailable")
        db.add(
            m.VoucherTransition(
                id=uuid7(),
                tenant_id=result.tenant_id,
                company_id=result.company_id,
                voucher_id=voucher.id,
                revision_id=operation.revision_id,
                action="execution_commit",
                from_status=voucher.status,
                to_status=target_status,
                reason="",
                voucher_version=voucher.row_version + 1,
            )
        )
        voucher.status = target_status
        voucher.row_version += 1
        if target_status == "POSTED":
            from vouchers.tasks.notifications import automatic

            revision = await db.get(m.VoucherRevision, operation.revision_id)
            if revision is None:
                raise ConflictError("execution revision is unavailable")
            await automatic(db, voucher, revision)
        elif target_status == "REVERSED":
            from vouchers.tasks.notifications import emit_terminal_state

            emit_terminal_state(db, voucher)
    operation.status = result.outcome
    operation.result = wire
    operation.row_version += 1
    from billing_platform.outbox import audit_payload, emit

    event = "vouchers.operation.result"
    emit(
        db,
        aggregate_type="vouchers.operation",
        aggregate_id=operation.id,
        event_type=event,
        tenant_id=operation.tenant_id,
        payload=audit_payload(
            action=event,
            category="money",
            entity_type="vouchers.operation",
            entity_id=operation.id,
            actor_user_id=None,
            company_id=operation.company_id,
        )
        | {"actor_type": "system"},
    )
    for effect in result.effects:
        db.add(
            m.VoucherPostingReference(
                id=uuid7(),
                tenant_id=result.tenant_id,
                company_id=result.company_id,
                operation_id=operation.id,
                owner=effect.owner,
                effect_kind=effect.effect_kind,
                effect_id=effect.effect_id,
            )
        )
    return operation

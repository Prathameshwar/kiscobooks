"""Atomic owner protocol. Production profiles remain disabled until their delivery batch."""

import datetime as dt
import hashlib
from collections.abc import Awaitable, Callable
from typing import Literal

from billing_platform.db.claims import insert_candidate
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import EffectReference, ExecutionCommand, ExecutionResult
from voucher_execution.transport import command_digest

from accounting.models.fiscal import FinancialSetup, FiscalPeriod
from accounting.models.masters import AccountingSetup
from accounting.models.voucher_execution import VoucherExecution, VoucherSourceGuard

# A later native profile must validate its typed payload and commit all effects in this session.
EffectExecutor = Callable[[AsyncSession, ExecutionCommand], Awaitable[tuple[EffectReference, ...]]]


async def execute(
    db: AsyncSession,
    command: ExecutionCommand,
    *,
    executor: EffectExecutor | None = None,
    stale_authority: bool = False,
    content_rejected: bool = False,
) -> ExecutionResult:
    if command_digest(command) != command.request_hash:
        raise ConflictError("execution request digest differs")
    if hashlib.sha256(canonical_json(command.source_payload)).hexdigest() != command.content_hash:
        raise ConflictError("execution content digest differs")
    # The same company row serializes existing fiscal transitions, journal commits and this adapter.
    setup = await db.scalar(
        select(AccountingSetup)
        .where(AccountingSetup.company_id == command.company_id)
        .with_for_update()
    )
    await insert_candidate(
        db,
        VoucherSourceGuard,
        {
            "id": uuid7(),
            "tenant_id": command.tenant_id,
            "company_id": command.company_id,
            "voucher_id": command.voucher_id,
        },
    )
    source = await db.scalar(
        select(VoucherSourceGuard)
        .where(
            VoucherSourceGuard.company_id == command.company_id,
            VoucherSourceGuard.voucher_id == command.voucher_id,
        )
        .with_for_update()
    )
    assert source is not None
    previous = await db.scalar(
        select(VoucherExecution)
        .where(
            VoucherExecution.company_id == command.company_id,
            or_(
                VoucherExecution.execution_id == command.execution_id,
                VoucherExecution.operation_id == command.operation_id,
            ),
        )
        .with_for_update()
    )
    if previous:
        if (
            previous.execution_id != command.execution_id
            or previous.request_hash != command.request_hash
            or previous.operation_id != command.operation_id
            or previous.source_guard_id != source.id
        ):
            raise ConflictError("execution identity has different evidence")
        return ExecutionResult.model_validate(previous.result)
    code: (
        Literal[
            "STALE_AUTHORITY",
            "CLOSED_PERIOD",
            "CONFIGURATION_CHANGED",
            "SOURCE_CONFLICT",
            "UNSUPPORTED_PROFILE",
            "CONTENT_REJECTED",
        ]
        | None
    ) = None
    effects: tuple[EffectReference, ...] = ()
    outcome: Literal["COMMITTED", "REJECTED", "CANCELLED"] = (
        "CANCELLED" if command.purpose == "CANCEL" else "REJECTED"
    )
    receipt_id = uuid7()
    if command.purpose in {"POST", "REVERSE"}:
        reversing = command.purpose == "REVERSE"
        if (not reversing and source.committed_execution_id is not None) or (
            reversing
            and (
                command.reversal_of_execution_id is None
                or source.committed_execution_id != command.reversal_of_execution_id
            )
        ):
            code = "SOURCE_CONFLICT"
        elif (
            stale_authority
            or not utcnow() < command.authority_expires_at <= utcnow() + dt.timedelta(minutes=5)
        ):
            code = "STALE_AUTHORITY"
        elif content_rejected:
            code = "CONTENT_REJECTED"
        elif executor is None:
            code = "UNSUPPORTED_PROFILE"
        elif setup is None:
            code = "CONFIGURATION_CHANGED"
        else:
            finance = await db.scalar(
                select(FinancialSetup).where(FinancialSetup.company_id == command.company_id)
            )
            # The command's digest is compared with the live delegated context in `authority()`
            # before any executor runs. The digest stored at setup is not frozen book state
            # (`fiscal.frozen_settings_match`): comparing it here refused every voucher once a
            # feature was enabled after books setup.
            if finance is None:
                code = "CONFIGURATION_CHANGED"
            else:
                dates = {
                    value
                    for value in (command.posting_date, command.stock_date)
                    if value is not None
                }
                periods: dict[str, int] = {}
                for date in sorted(dates):
                    selected = list(
                        await db.scalars(
                            select(FiscalPeriod)
                            .where(
                                FiscalPeriod.company_id == command.company_id,
                                FiscalPeriod.start_date <= date,
                                FiscalPeriod.end_date >= date,
                            )
                            .with_for_update()
                        )
                    )
                    if (
                        len(selected) != 1
                        or selected[0].status != "OPEN"
                        or date < finance.books_begin_date
                    ):
                        code = "CLOSED_PERIOD"
                        break
                    periods[str(selected[0].id)] = selected[0].row_version
                if code is None and (
                    not dates
                    or periods
                    != {str(key): value for key, value in command.period_versions.items()}
                ):
                    code = "CLOSED_PERIOD"
                if code is None:
                    # Roll back receipt and effects together; no network inside this transaction.
                    effects = await executor(db, command)
                    if command.authority_expires_at <= utcnow():
                        # Roll back callback effects; reconcile the original attempt later.
                        raise ConflictError("execution authority expired before commit")
                    if any(effect.effect_kind == "SOURCE_RECEIPT" for effect in effects):
                        raise ConflictError("the protocol owns source receipt identity")
                    effects += (
                        EffectReference(
                            owner="accounting", effect_kind="SOURCE_RECEIPT", effect_id=receipt_id
                        ),
                    )
                    setup.generation += 1
                    if not reversing:
                        source.committed_execution_id = command.execution_id
                        source.row_version += 1
                    outcome = "COMMITTED"
    result = ExecutionResult(
        protocol_version=command.protocol_version,
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        operation_id=command.operation_id,
        execution_id=command.execution_id,
        content_hash=command.content_hash,
        configuration_hash=command.configuration_hash,
        request_hash=command.request_hash,
        outcome=outcome,
        effects=effects,
        committed_at=utcnow() if outcome == "COMMITTED" else None,
        committed_generation=setup.generation
        if outcome == "COMMITTED" and setup is not None
        else None,
        rejection_code=code,
    )
    db.add(
        VoucherExecution(
            id=receipt_id,
            tenant_id=command.tenant_id,
            company_id=command.company_id,
            source_guard_id=source.id,
            execution_id=command.execution_id,
            operation_id=command.operation_id,
            request_hash=command.request_hash,
            command=command.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            created_by=command.actor_user_id,
            updated_by=command.actor_user_id,
        )
    )
    event = "accounting.voucher_execution.record"
    emit(
        db,
        aggregate_type="accounting.voucher_execution",
        aggregate_id=receipt_id,
        tenant_id=command.tenant_id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="system",
            entity_type="accounting.voucher_execution",
            entity_id=receipt_id,
            actor_user_id=None,
            company_id=command.company_id,
        )
        | {"actor_type": "system"},
    )
    await db.flush()
    from accounting.tasks.stock_reporting import capture

    await capture(db, command, result)
    return result

"""Durable prepare/reserve/commit for common voucher money effects."""

import hashlib
import logging

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.diagnostics import log_failure
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.outbox import emit
from identity_posting import PostingClient, ReservationError
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution import EffectReference, ExecutionCommand, ExecutionResult
from voucher_execution.transport import command_digest

from accounting.api.auth import Access, delegated_access
from accounting.models.ledger import Journal, JournalLine
from accounting.models.subledger import OpenItem
from accounting.models.voucher_execution import VoucherExecution, VoucherSourceGuard
from accounting.models.voucher_money import (
    BankInstrument,
    VoucherMoneyAllocation,
    VoucherMoneyIntent,
)
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks import voucher_money_effects as effects
from accounting.tasks.commands import setup_lock
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.journal_drafts import create_in_transaction
from accounting.tasks.journal_posting import (
    PostingDependencyError,
    commit_post,
    intent_values,
    prepare_in_transaction,
)
from accounting.tasks.voucher_execution import execute


def authority(command: ExecutionCommand, secret: bytes) -> Access:
    delegated = command.authority
    if delegated is None or command.protocol_version != 2:
        raise AuthenticationRequiredError("money execution requires delegated gateway authority")
    current = delegated_access(
        delegated,
        secret,
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        actor_user_id=command.actor_user_id,
    )
    actor = current.actor
    facts = financial_context(current)
    for permission in (
        "vouchers.reverse" if command.purpose == "REVERSE" else "vouchers.post",
        "ledger.post_journal",
    ):
        actor.require_scope(permission, target=ScopePath(company_id=command.company_id))
    if command.company_configuration_hash != facts.configuration_hash:
        raise ConflictError("company configuration changed")
    evidence = command.configuration_evidence or {}
    frozen = {key: value for key, value in evidence.items() if key != "digest"}
    if hashlib.sha256(canonical_json(frozen)).hexdigest() != command.configuration_hash or any(
        evidence.get(key) != value
        for key, value in {
            "kind": command.kind,
            "profile": command.profile,
            "company_configuration_hash": facts.configuration_hash,
        }.items()
    ):
        raise ConflictError("native configuration evidence differs")
    if (
        command_digest(command) != command.request_hash
        or hashlib.sha256(canonical_json(command.source_payload)).hexdigest()
        != command.content_hash
    ):
        raise ConflictError("money execution evidence differs")
    return current


async def existing(db: AsyncSession, command: ExecutionCommand) -> ExecutionResult | None:
    row = await db.scalar(
        select(VoucherExecution).where(
            VoucherExecution.company_id == command.company_id,
            VoucherExecution.execution_id == command.execution_id,
        )
    )
    if row is not None:
        if row.request_hash != command.request_hash or row.operation_id != command.operation_id:
            raise ConflictError("execution identity was reused")
        return ExecutionResult.model_validate(row.result)
    return None


async def prepare(
    db: AsyncSession, current: Access, command: ExecutionCommand
) -> VoucherMoneyIntent:
    await setup_lock(db, current)
    previous = await db.scalar(
        select(VoucherMoneyIntent)
        .where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.execution_id == command.execution_id,
        )
        .with_for_update()
    )
    if previous:
        if previous.request_hash != command.request_hash or previous.status != "PREPARED":
            raise ConflictError("posting intent evidence differs")
        return previous
    pending = await db.scalar(
        select(VoucherMoneyIntent.id).where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.voucher_id == command.voucher_id,
            VoucherMoneyIntent.status.in_(["PREPARED", "COMMITTED"]),
            VoucherMoneyIntent.execution_id != command.reversal_of_execution_id
            if command.reversal_of_execution_id
            else true(),
        )
    )
    guard = await db.scalar(
        select(VoucherSourceGuard).where(
            VoucherSourceGuard.company_id == command.company_id,
            VoucherSourceGuard.voucher_id == command.voucher_id,
        )
    )
    if pending or (command.purpose == "POST" and guard and guard.committed_execution_id):
        raise ConflictError("voucher has a pending or committed source execution")
    if command.purpose == "REVERSE":
        if command.source_payload.get("invoice") is not None:
            raise ConflictError("invoice reversal requires statutory and original-component guards")
        from accounting.tasks.voucher_money_reversal import prepare as prepare_reversal

        journal = await prepare_reversal(db, current, command)
    else:
        invoice_plan = None
        if command.source_payload.get("invoice") is not None:
            from accounting.tasks.invoice_execution import resolve

            invoice_plan = await resolve(db, current, command)
            body, policy = invoice_plan[2:]
        else:
            body, policy = effects.inputs(command)
        await effects.validate(db, current, command, resolved=(body, policy))
        journal = (
            await create_in_transaction(
                db,
                current,
                effects.draft(command, body),
                kind="VOUCHER",
                source_system="vouchers",
                source_type=command.kind.lower(),
                source_id=str(command.execution_id),
            )
            if body.accounts
            else None
        )
    intent = VoucherMoneyIntent(
        **effects.values(current),
        execution_id=command.execution_id,
        voucher_id=command.voucher_id,
        journal_id=journal.id if journal else None,
        request_hash=command.request_hash,
        kind=command.kind,
        posting_date=command.posting_date,
        status="PREPARED",
        command=command.model_dump(mode="json"),
    )
    db.add(intent)
    await db.flush()
    effects.audit(db, current, intent.id, "voucher_money_intent", "prepare")
    if command.purpose != "REVERSE" and invoice_plan is not None:
        from accounting.tasks.invoice_facts import store

        await store(db, current, intent, invoice_plan[0], invoice_plan[1], invoice_plan[2])
    if journal:
        db.info["voucher_money_execution"] = command.execution_id
        await prepare_in_transaction(
            db, current, journal.id, ExpectedVersion(expected_version=journal.row_version)
        )
    return intent


async def abandon(db: AsyncSession, command: ExecutionCommand, intent: VoucherMoneyIntent) -> None:
    """Service-authorized cancellation releases only this exact uncommitted intent."""
    if intent.status != "PREPARED" or intent.request_hash != command.request_hash:
        raise ConflictError("posting intent cannot be abandoned")
    from billing_platform.outbox import audit_payload

    if intent.journal_id:
        journal = await db.get(Journal, intent.journal_id)
        if journal is None or journal.status != "PREPARED":
            raise ConflictError("prepared journal cannot be abandoned")
        journal.status = "VOID"
        journal.row_version += 1
        journal.updated_by = command.actor_user_id
        from accounting.tasks.journal_posting import posting_delivery_values

        delivery_event, delivery_payload = await posting_delivery_values(db, journal, "abort")
        for event in ("accounting.journal.void", delivery_event):
            emit(
                db,
                aggregate_type="accounting.journal",
                aggregate_id=journal.id,
                tenant_id=command.tenant_id,
                event_type=event,
                payload=delivery_payload
                if event.endswith("abort")
                else audit_payload(
                    action=event,
                    category="system",
                    entity_type="accounting.journal",
                    entity_id=journal.id,
                    actor_user_id=None,
                    company_id=command.company_id,
                )
                | {"actor_type": "system"},
            )
    intent.status = "CANCELLED"
    intent.row_version += 1
    emit(
        db,
        aggregate_type="accounting.voucher_money_intent",
        aggregate_id=intent.id,
        tenant_id=command.tenant_id,
        event_type="accounting.voucher_money_intent.cancel",
        payload=audit_payload(
            action="accounting.voucher_money_intent.cancel",
            category="system",
            entity_type="accounting.voucher_money_intent",
            entity_id=intent.id,
            actor_user_id=None,
            company_id=command.company_id,
        )
        | {"actor_type": "system"},
    )


async def _dispatch(
    factory: async_sessionmaker[AsyncSession],
    command: ExecutionCommand,
    *,
    secret: bytes,
    client: PostingClient | None,
    enabled: bool = True,
) -> ExecutionResult:
    with tenant_scope(command.tenant_id):
        async with factory() as db:
            terminal = await existing(db, command)
            if terminal:
                return terminal
        current = None
        stale = command.authority_expires_at <= utcnow()
        if command.purpose != "CANCEL" and not stale:
            try:
                current = authority(command, secret)
            except AuthenticationRequiredError:
                # Signed service authority may resolve its own expired attempt, never post it.
                stale = True
        if command.purpose == "CANCEL" or stale or not enabled:
            async with factory() as db, db.begin():
                result = await execute(db, command, stale_authority=stale)
                pending = await db.scalar(
                    select(VoucherMoneyIntent).where(
                        VoucherMoneyIntent.company_id == command.company_id,
                        VoucherMoneyIntent.execution_id == command.execution_id,
                    )
                )
                if pending and pending.status == "PREPARED" and result.outcome != "COMMITTED":
                    await abandon(db, command, pending)
                return result
        assert current is not None
        async with factory() as db, db.begin():
            intent = await prepare(db, current, command)
            journal_id = intent.journal_id
            journal = await db.get(Journal, journal_id) if journal_id else None
            reservation = intent_values(journal) if journal else None
        receipt = None
        if journal_id and reservation:
            if client is None:
                raise PostingDependencyError("Identity posting authorization is not configured")
            try:
                receipt = await client.reserve(
                    command.tenant_id,
                    command.company_id,
                    operation_id=journal_id,
                    actor_user_id=command.actor_user_id,
                    configuration_hash=reservation["configuration_hash"],
                    features=reservation["features"],
                )
            except ReservationError as exc:
                raise PostingDependencyError(
                    "Identity authorization unavailable; reconcile and retry this execution"
                ) from exc

        async def commit(
            db: AsyncSession, accepted: ExecutionCommand
        ) -> tuple[EffectReference, ...]:
            intent = await db.scalar(
                select(VoucherMoneyIntent)
                .where(
                    VoucherMoneyIntent.company_id == accepted.company_id,
                    VoucherMoneyIntent.execution_id == accepted.execution_id,
                )
                .with_for_update()
            )
            if intent is None or intent.status != "PREPARED":
                raise ConflictError("posting intent is no longer live")
            db.info["voucher_money_execution"] = accepted.execution_id
            refs = []
            reversal_allocations = []
            if accepted.purpose == "REVERSE":
                from accounting.tasks.voucher_money_reversal import unwind

                reversal_allocations = await unwind(db, current, accepted)
            if journal_id:
                journal = await db.get(Journal, journal_id)
                if journal is None or receipt is None:
                    raise ConflictError("prepared journal or Identity reservation is unavailable")
                await commit_post(db, current, journal, receipt)
                refs.append(
                    EffectReference(owner="accounting", effect_kind="JOURNAL", effect_id=journal.id)
                )
                item_ids = list(
                    await db.scalars(
                        select(OpenItem.id).where(
                            OpenItem.company_id == accepted.company_id,
                            OpenItem.journal_line_id.in_(
                                select(JournalLine.id).where(JournalLine.journal_id == journal.id)
                            ),
                        )
                    )
                )
                refs.extend(
                    EffectReference(owner="accounting", effect_kind="OPEN_ITEM", effect_id=item_id)
                    for item_id in item_ids
                )
            elif accepted.purpose != "REVERSE":
                await effects.allocate(db, current, accepted, {})
            allocation_ids = list(
                await db.scalars(
                    select(VoucherMoneyAllocation.allocation_id).where(
                        VoucherMoneyAllocation.company_id == accepted.company_id,
                        VoucherMoneyAllocation.intent_id == intent.id,
                    )
                )
            )
            allocation_ids.extend(reversal_allocations)
            bank_ids = list(
                await db.scalars(
                    select(BankInstrument.id).where(
                        BankInstrument.company_id == accepted.company_id,
                        BankInstrument.intent_id == intent.id,
                    )
                )
            )
            refs.extend(
                EffectReference(
                    owner="accounting", effect_kind="BANK_INSTRUMENT", effect_id=identity
                )
                for identity in bank_ids
            )
            refs.extend(
                EffectReference(owner="accounting", effect_kind="ALLOCATION", effect_id=identity)
                for identity in allocation_ids
            )
            intent.status = "COMMITTED"
            intent.row_version += 1
            effects.audit(db, current, intent.id, "voucher_money_intent", "commit")
            return tuple(refs)

        async with factory() as db, db.begin():
            result = await execute(db, command, executor=commit)
            if result.outcome != "COMMITTED":
                remaining_intent = await db.scalar(
                    select(VoucherMoneyIntent).where(
                        VoucherMoneyIntent.company_id == command.company_id,
                        VoucherMoneyIntent.execution_id == command.execution_id,
                    )
                )
                if remaining_intent and remaining_intent.status == "PREPARED":
                    await abandon(db, command, remaining_intent)
            return result


async def dispatch(
    factory: async_sessionmaker[AsyncSession],
    command: ExecutionCommand,
    *,
    secret: bytes,
    client: PostingClient | None,
    enabled: bool = True,
    invoices_enabled: bool = False,
) -> ExecutionResult:
    """Known domain rejections terminate only after the entire effects transaction rolled back.

    A referenced object that is missing or foreign (NotFoundError, PermissionDeniedError) is a
    property of the accepted content, not a transient dependency fault: retrying the same
    command can never succeed, so it ends as CONTENT_REJECTED instead of escaping as a 404
    that the Vouchers delivery worker would retry forever while the voucher stays locked.
    """
    from billing_platform.errors import (
        NotFoundError,
        PermissionDeniedError,
        ValidationFailedError,
    )

    if command.source_payload.get("invoice") is not None and not invoices_enabled:
        enabled = False
    try:
        return await _dispatch(factory, command, secret=secret, client=client, enabled=enabled)
    except (ConflictError, ValidationFailedError, PermissionDeniedError, NotFoundError) as error:
        # The result carries only a code; the sanitized error class tells operators which rule.
        log_failure(
            logging.getLogger("accounting.voucher_execution"),
            service="accounting",
            event="voucher.execution.content_rejected",
            error=error,
        )
        with tenant_scope(command.tenant_id):
            async with factory() as db, db.begin():
                result = await execute(db, command, content_rejected=True)
                intent = await db.scalar(
                    select(VoucherMoneyIntent).where(
                        VoucherMoneyIntent.company_id == command.company_id,
                        VoucherMoneyIntent.execution_id == command.execution_id,
                    )
                )
                if intent and intent.status == "PREPARED" and result.outcome != "COMMITTED":
                    await abandon(db, command, intent)
                return result

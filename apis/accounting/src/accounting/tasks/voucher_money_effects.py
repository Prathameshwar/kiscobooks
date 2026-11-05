"""Authoritative GL-adjacent effects, composed inside the same Accounting transaction."""

import uuid
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand
from voucher_execution.money import MoneyInput, MoneyPolicy, validate_entry_controls

from accounting.api.auth import Access
from accounting.domain.voucher_money import MoneyAccount, validate_accounts
from accounting.models.ledger import Journal
from accounting.models.subledger import OpenItem
from accounting.models.voucher_money import VoucherMoneyAllocation, VoucherMoneyIntent
from accounting.schemas.credit import CreditCheck
from accounting.schemas.ledger import JournalCreate, JournalLineCreate
from accounting.schemas.subledger import AllocationCreate
from accounting.tasks import allocation_targets
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.journal_drafts import lines, validate_lines


def values(access: Access) -> dict[str, Any]:
    return {
        "id": uuid7(),
        "tenant_id": access.actor.tenant_id,
        "company_id": access.context.company_id,
        "created_by": access.actor.user_id,
        "updated_by": access.actor.user_id,
    }


def audit(
    db: AsyncSession,
    access: Access,
    identity: uuid.UUID,
    entity: str,
    action: str,
    *,
    reason: str | None = None,
) -> None:
    event = "accounting." + entity + "." + action
    emit(
        db,
        aggregate_type="accounting." + entity,
        aggregate_id=identity,
        tenant_id=access.actor.tenant_id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="money",
            entity_type="accounting." + entity,
            entity_id=identity,
            actor_user_id=access.actor.user_id,
            company_id=access.context.company_id,
            reason=reason,
        ),
    )


def inputs(command: ExecutionCommand) -> tuple[MoneyInput, MoneyPolicy]:
    source = command.source_payload
    if (
        source.get("mode") != "ACCOUNTS"
        or source.get("lines")
        or source.get("stock_date")
        or source.get("statutory_date")
    ):
        raise ValidationFailedError("ordinary money execution cannot produce inventory or tax")
    evidence = command.configuration_evidence or {}
    policy = evidence.get("policy", {})
    if not isinstance(policy, dict):
        raise ValidationFailedError("invalid native voucher policy")
    try:
        body = MoneyInput.model_validate(source.get("financial"))
        controls = MoneyPolicy.model_validate(policy.get("financial") or {})
        validate_entry_controls(
            body,
            controls,
            kind=command.kind,
            profile=command.profile,
            posting_date=command.posting_date,
        )
        if command.purpose == "POST" and (
            command.posting_date is None
            or str(source.get("posting_date")) != str(command.posting_date)
        ):
            raise ValueError("posting date must match the accepted revision")
        return body, controls
    except ValueError as error:
        raise ValidationFailedError("invalid ordinary financial sections") from error


def draft(command: ExecutionCommand, body: MoneyInput) -> JournalCreate:
    if len(str(command.source_payload.get("narration") or "")) > 1000:
        raise ValidationFailedError("financial narration is limited to 1000 characters")
    if command.posting_date is None or str(command.source_payload.get("posting_date")) != str(
        command.posting_date
    ):
        raise ValidationFailedError("posting date must match the accepted revision")
    return JournalCreate.model_validate(
        {
            "document_date": command.source_payload.get("document_date"),
            "posting_date": command.posting_date,
            "description": command.source_payload.get("narration")
            or command.kind.title() + " voucher",
            "lines": [
                JournalLineCreate.model_validate(
                    entry.model_dump(
                        include={
                            "account_id",
                            "side",
                            "currency",
                            "amount",
                            "exchange_rate",
                            "description",
                        }
                    )
                )
                for entry in body.accounts
            ],
        }
    )


async def intent_for(db: AsyncSession, journal: Journal) -> VoucherMoneyIntent:
    intent = await db.scalar(
        select(VoucherMoneyIntent).where(
            VoucherMoneyIntent.company_id == journal.company_id,
            VoucherMoneyIntent.journal_id == journal.id,
        )
    )
    if intent is None or intent.status != "PREPARED":
        raise ConflictError("voucher journal requires its live posting intent")
    return intent


async def resolved_inputs(
    db: AsyncSession, command: ExecutionCommand
) -> tuple[MoneyInput, MoneyPolicy]:
    if command.source_payload.get("invoice") is None:
        return inputs(command)
    from accounting.tasks.invoice_facts import load_money

    intent = await db.scalar(
        select(VoucherMoneyIntent).where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.execution_id == command.execution_id,
        )
    )
    if intent is None:
        raise ConflictError("invoice posting intent is unavailable")
    evidence = command.configuration_evidence or {}
    return await load_money(db, intent), MoneyPolicy.model_validate(
        evidence["policy"].get("financial") or {}
    )


async def validate(
    db: AsyncSession,
    access: Access,
    command: ExecutionCommand,
    *,
    resolved: tuple[MoneyInput, MoneyPolicy] | None = None,
) -> None:
    body, policy = resolved if resolved is not None else inputs(command)
    if command.posting_date is None:
        raise ValidationFailedError("posting date is required")
    if not body.accounts and (
        command.kind != "JOURNAL"
        or body.purpose != "BILL_ADJUSTMENT"
        or not policy.allocations_allowed
    ):
        raise ValidationFailedError("allocation-only profile is unavailable")
    if command.source_payload.get("invoice") is None:
        # Invoices prove their targets in the shared preview, which prepare and commit re-run.
        await allocation_targets.check_allocation_targets(
            db,
            access,
            body.allocations,
            posting_date=command.posting_date,
            new_bills={
                entry.line_key: allocation_targets.NewBill(entry.account_id, entry.currency)
                for entry in body.accounts
            },
        )
    if not body.accounts:
        return
    _, accounts = await validate_lines(db, access, draft(command, body), kind="VOUCHER")
    if command.source_payload.get("invoice") is not None:
        for entry in body.accounts:
            account = accounts[entry.account_id]
            if account.row_version != entry.source_version:
                raise ConflictError("invoice posting account version changed")
            if account.kind != "TAX" and account.kind not in policy.allowed_account_kinds:
                raise ValidationFailedError("invoice account kind is excluded by configuration")
    else:
        validate_accounts(
            body,
            policy,
            {
                key: MoneyAccount(
                    row.id, row.kind, row.posting_policy, row.party_role, row.row_version
                )
                for key, row in accounts.items()
            },
            kind=command.kind,
            profile=command.profile,
            base_currency=access.context.base_currency,
            posting_date=command.posting_date,
        )
    from accounting.tasks.credit import assess, can_constrain
    from accounting.tasks.party_documents import enforce_holds, party_account, policy_at

    # Aggregate repeated debt legs before credit control; splitting a line cannot bypass a limit.
    debt: dict[tuple[uuid.UUID, str, Decimal], Decimal] = {}
    for entry in body.accounts:
        account = accounts[entry.account_id]
        if account.kind == "PARTY":
            await party_account(db, access, account.id)
            control = await policy_at(db, access, account, command.posting_date)
            enforce_holds(control, command.kind)
            if command.source_payload.get("invoice") is not None and body.tenders:
                if command.kind in {"PURCHASE", "CREDIT_NOTE"}:
                    enforce_holds(control, "PAYMENT")
            if control and not control.bill_wise and entry.tracking == "NEW_REF":
                raise ValidationFailedError("new bill references are disabled for this party role")
            if (account.party_role == "CUSTOMER") == (entry.side == "DEBIT"):
                key = (account.id, entry.currency, entry.exchange_rate)
                debt[key] = debt.get(key, Decimal(0)) + entry.amount
    # Same account at multiple rates would need an aggregated base-currency credit request.
    if len({key[0] for key in debt}) != len(debt):
        raise ValidationFailedError(
            "debt entries for one account require one currency and exchange rate"
        )
    for (account_id, currency, rate), amount in debt.items():
        if not await can_constrain(
            db,
            accounts[account_id],
            command.posting_date,
            limits_enabled="credit_limits" in access.context.features,
        ):
            continue  # nothing could be refused: no assessment and no credit data to read
        decision = await assess(
            db,
            access,
            CreditCheck(
                account_id=account_id,
                currency=currency,
                amount=amount,
                exchange_rate=rate,
                posting_date=command.posting_date,
            ),
        )
        if decision.status not in {"ALLOW", "WARN"}:
            raise ConflictError("credit control requires resolution before voucher posting")
    facts = financial_context(access)
    today = utcnow().astimezone(ZoneInfo(facts.timezone)).date()
    if any(
        t.recognition == "MATURITY_DATE" and t.instrument_date and t.instrument_date > today
        for t in body.tenders
    ):
        raise ConflictError("post-dated maturity recognition is pending until the instrument date")
    if (
        command.kind in {"RECEIPT", "JOURNAL", "SALES", "DEBIT_NOTE"}
        and facts.cash_receipt_limit is not None
    ):
        valued, _ = await validate_lines(db, access, draft(command, body), kind="VOUCHER")
        cash = sum(
            (
                line.base_amount
                for line in valued
                if accounts[line.entry.account_id].kind == "CASH" and line.entry.side == "DEBIT"
            ),
            Decimal(0),
        )
        from accounting.tasks.cash_receipts import check

        await check(
            db,
            access,
            command.posting_date,
            cash,
            {row.party_id for row in accounts.values() if row.party_id},
        )


async def before_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    intent = await intent_for(db, journal)
    if db.info.get("voucher_money_execution") != intent.execution_id:
        raise ConflictError("voucher journals must post through their execution protocol")
    command = ExecutionCommand.model_validate(intent.command)
    if command.source_payload.get("stock") is not None:
        from accounting.tasks.stock_execution import validate_journal

        await validate_journal(db, access, intent, journal)
        return
    if command.source_payload.get("invoice") is not None:
        from accounting.tasks.invoice_execution import resolve
        from accounting.tasks.invoice_facts import load_money

        _, _, body, policy = await resolve(db, access, command)
        if body != await load_money(db, intent):
            raise ConflictError(
                "prepared invoice journal differs from current accepted calculation"
            )
        await validate(db, access, command, resolved=(body, policy))
    else:
        await validate(db, access, command)


async def allocate(
    db: AsyncSession,
    access: Access,
    command: ExecutionCommand,
    new_items: dict[uuid.UUID, uuid.UUID],
) -> list[uuid.UUID]:
    from accounting.tasks.allocations import create_in_transaction

    body, _ = await resolved_inputs(db, command)
    assert command.posting_date is not None
    result = []
    for allocation in body.allocations:
        selected = []
        for target in (allocation.debt, allocation.credit):
            item_id = target.item_id or new_items.get(target.line_key or uuid.UUID(int=0))
            if item_id is None:
                raise ConflictError("new bill target is unavailable")
            item = await company_object(db, OpenItem, item_id, company_id=command.company_id)
            if item.currency != allocation.currency:
                raise ValidationFailedError("allocation currency differs from selected bills")
            selected.append(item_id)
        effect = await create_in_transaction(
            db,
            access,
            AllocationCreate(
                debt_item_id=selected[0],
                credit_item_id=selected[1],
                amount=allocation.amount,
                posting_date=command.posting_date,
                fx_account_id=allocation.fx_account_id,
            ),
        )
        result.append(effect.row.id)
        intent = await db.scalar(
            select(VoucherMoneyIntent).where(
                VoucherMoneyIntent.company_id == command.company_id,
                VoucherMoneyIntent.execution_id == command.execution_id,
            )
        )
        if intent is None:
            raise ConflictError("allocation intent is unavailable")
        link = VoucherMoneyAllocation(
            **values(access),
            intent_id=intent.id,
            allocation_id=effect.row.id,
            allocation_key=allocation.allocation_key,
        )
        db.add(link)
        audit(db, access, link.id, "voucher_money_allocation", "create")
    return result


async def after_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    from accounting.tasks.subledger_posting import make_items

    intent = await intent_for(db, journal)
    command = ExecutionCommand.model_validate(intent.command)
    if command.source_payload.get("stock") is not None and (
        command.source_payload.get("invoice") is None
    ):
        return  # Native stock effects and clearing GL commit in the common owner callback.
    # An invoice, including a goods Purchase bill (B24), opens its party bill, tenders and
    # adjustments from its retained invoice distribution.
    body, _ = await resolved_inputs(db, command)
    stored = await lines(db, journal.company_id, journal.id)
    new_items = {}
    by_key = {}
    for entry, line in zip(body.accounts, stored, strict=True):
        by_key[entry.line_key] = line
        if line.party_id:
            await make_items(
                db,
                access,
                journal,
                line,
                [
                    {
                        "amount": str(line.amount),
                        "reference": entry.bill_reference or str(command.voucher_id),
                        "document_date": journal.document_date.isoformat(),
                        "due_date": (entry.due_date or journal.document_date).isoformat(),
                    }
                ],
                {
                    "voucher_id": str(command.voucher_id),
                    "tracking": entry.tracking,
                    "configuration_hash": command.configuration_hash,
                },
            )
            item = await db.scalar(
                select(OpenItem).where(
                    OpenItem.company_id == journal.company_id, OpenItem.journal_line_id == line.id
                )
            )
            assert item is not None
            new_items[entry.line_key] = item.id
    await allocate(db, access, command, new_items)
    from accounting.tasks.finance_records import create_row

    for tender in body.tenders:
        line = by_key[tender.line_key]
        instrument = await create_row(
            db,
            access,
            "bank_instrument",
            intent_id=intent.id,
            journal_line_id=line.id,
            account_id=line.account_id,
            tender_key=tender.tender_key,
            mode=tender.mode,
            reference=tender.reference,
            instrument_date=tender.instrument_date,
            booking_date=journal.posting_date,
            recognition=tender.recognition,
            currency=tender.currency,
            amount=tender.amount,
        )
        await create_row(
            db,
            access,
            "bank_instrument_event",
            instrument_id=instrument.id,
            action="BOOKED",
            event_date=journal.posting_date,
            reference=None,
            reason="Voucher posting",
        )

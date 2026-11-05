"""Accounting-owned source contracts, dated terms and settlement drafts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandResult, canonical_json
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.ledger import Installment, Term, base_value, payment_schedule
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.masters import (
    Account,
    Party,
    PartyAccountingPolicy,
    PaymentTerm,
    PaymentTermLine,
)
from accounting.models.subledger import SourceDocument
from accounting.resources import BY_NAME
from accounting.schemas.ledger import JournalCreate, JournalLineCreate
from accounting.schemas.subledger import SourceCreate
from accounting.tasks.access import authorize, readable
from accounting.tasks.commands import values_of
from accounting.tasks.finance_records import create_row
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.journal_drafts import create_in_transaction


async def party_account(db: AsyncSession, access: Access, account_id: uuid.UUID) -> Account:
    account = await company_object(db, Account, account_id, company_id=access.context.company_id)
    authorize(access, BY_NAME["account"], "read")
    if not {"party_id", "party_role", "kind", "status", "currency", "currency_mode"} <= readable(
        access, BY_NAME["account"], values_of(account, BY_NAME["account"])
    ):
        raise PermissionDeniedError("party account attributes are not readable")
    if (
        account.kind != "PARTY"
        or account.party_id is None
        or account.party_role not in {"CUSTOMER", "SUPPLIER"}
        or account.status != "ACTIVE"
    ):
        raise ConflictError("an active debtor or creditor account is required")
    party = await company_object(db, Party, account.party_id, company_id=account.company_id)
    authorize(access, BY_NAME["party"], "read")
    if "status" not in readable(access, BY_NAME["party"], values_of(party, BY_NAME["party"])):
        raise PermissionDeniedError("party status is not readable")
    if party.status != "ACTIVE":
        raise ConflictError("party is not active")
    return account


async def policy_at(
    db: AsyncSession, access: Access, account: Account, date: dt.date
) -> PartyAccountingPolicy | None:
    policies = list(
        await db.scalars(
            select(PartyAccountingPolicy)
            .where(
                PartyAccountingPolicy.company_id == account.company_id,
                PartyAccountingPolicy.party_id == account.party_id,
                PartyAccountingPolicy.role == account.party_role,
                PartyAccountingPolicy.valid_from <= date,
                (PartyAccountingPolicy.valid_to.is_(None))
                | (PartyAccountingPolicy.valid_to >= date),
            )
            .limit(2)
        )
    )
    if len(policies) > 1:
        raise ConflictError("overlapping accounting policies")
    if not policies:
        return None
    spec = BY_NAME["party_accounting_policy"]
    authorize(access, spec, "read")
    if not {
        "payment_term_id",
        "bill_wise",
        "settlement_currency",
        "transaction_hold",
        "payment_hold",
        "valid_from",
        "valid_to",
    } <= readable(access, spec, values_of(policies[0], spec)):
        raise PermissionDeniedError("accounting policy inputs are not readable")
    return policies[0]


def enforce_holds(policy: PartyAccountingPolicy | None, kind: str) -> None:
    if policy and (policy.transaction_hold or (kind == "PAYMENT" and policy.payment_hold)):
        raise ConflictError("party is on transaction or payment hold")


async def schedule(
    db: AsyncSession, access: Access, body: SourceCreate, account: Account
) -> tuple[tuple[Installment, ...], dict[str, Any]]:
    facts = financial_context(access)
    policy = await policy_at(db, access, account, body.posting_date)
    enforce_holds(policy, body.kind)
    snapshot: dict[str, Any] = {
        "policy_id": str(policy.id) if policy else None,
        "policy_version": policy.row_version if policy else None,
        "bill_wise": policy.bill_wise if policy else True,
        "settlement_currency": policy.settlement_currency if policy else body.currency,
    }
    if body.due_date is not None:
        if body.due_date < body.document_date:
            raise ValidationFailedError("due date cannot precede document date")
        return (Installment(1, body.amount, body.due_date),), snapshot
    if body.kind in {"RECEIPT", "PAYMENT", "CREDIT_NOTE"}:
        return (Installment(1, body.amount, body.document_date),), snapshot
    terms: tuple[Term, ...]
    if policy:
        term = await company_object(
            db, PaymentTerm, policy.payment_term_id, company_id=account.company_id
        )
        if term.status != "ACTIVE":
            raise ConflictError("payment term is not active")
        for name in ("payment_term", "payment_term_line"):
            spec = BY_NAME[name]
            authorize(access, spec, "read")
            required = (
                {"status"}
                if name == "payment_term"
                else {"sequence", "percentage", "basis", "days"}
            )
            if not required <= readable(access, spec):
                raise PermissionDeniedError("payment term inputs are not readable")
        stored = list(
            await db.scalars(
                select(PaymentTermLine)
                .where(
                    PaymentTermLine.company_id == account.company_id,
                    PaymentTermLine.payment_term_id == term.id,
                )
                .order_by(PaymentTermLine.sequence)
                .limit(25)
            )
        )
        terms = tuple(Term(row.sequence, row.percentage, row.basis, row.days) for row in stored)
        snapshot["term_id"] = str(term.id)
        snapshot["term_version"] = term.row_version
    else:
        terms = (Term(1, Decimal(100), "INVOICE_DATE", facts.default_payment_terms_days),)
    snapshot["terms"] = [
        {
            "sequence": term.sequence,
            "percentage": str(term.percentage),
            "basis": term.basis,
            "days": term.days,
        }
        for term in terms
    ]
    return payment_schedule(
        body.amount,
        body.document_date,
        terms,
        precision=facts.amount_precision,
        rounding=facts.rounding_mode,
    ), snapshot


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: SourceCreate, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        account = await party_account(db, access, body.account_id)
        role = account.party_role
        if (body.kind in {"INVOICE", "RECEIPT"} and role != "CUSTOMER") or (
            body.kind in {"BILL", "PAYMENT"} and role != "SUPPLIER"
        ):
            raise ValidationFailedError("document kind does not match the debtor or creditor role")
        offset = await company_object(
            db, Account, body.counterpart_account_id, company_id=account.company_id
        )
        if offset.kind == "PARTY" or offset.id == account.id:
            raise ValidationFailedError("counterpart must be a non-party account")
        if body.kind in {"RECEIPT", "PAYMENT"} and offset.kind not in {"CASH", "BANK"}:
            raise ValidationFailedError("settlement counterpart must be cash or bank")
        installments, snapshot = await schedule(db, access, body, account)
        facts = financial_context(access)
        base = base_value(
            body.amount,
            body.currency,
            body.exchange_rate,
            access.context.base_currency,
            facts.amount_precision,
            facts.rounding_mode,
        )
        if body.kind == "RECEIPT" and offset.kind == "CASH":
            from accounting.tasks.cash_receipts import check

            await check(
                db,
                access,
                body.posting_date,
                base,
                {account.party_id} if account.party_id else set(),
                include_prepared=True,
            )
        direction = "DEBT" if body.kind in {"INVOICE", "BILL"} else "CREDIT"
        debit = (role == "CUSTOMER") == (direction == "DEBT")
        counterpart_currency = (
            body.currency
            if offset.currency_mode == "FIXED" and offset.currency == body.currency
            else access.context.base_currency
        )
        outcome = None
        if body.tax is not None:
            from accounting.tasks.fiscal import posting_period
            from accounting.tasks.voucher_tax import resolve_source

            await posting_period(db, access, body.posting_date)
            outcome = await resolve_source(db, access, body, account, offset)
            outcome.require_ready()
        draft = (
            outcome.draft(body)
            if outcome is not None
            else JournalCreate(
                document_date=body.document_date,
                posting_date=body.posting_date,
                description=body.description,
                lines=[
                    JournalLineCreate(
                        account_id=account.id,
                        side="DEBIT" if debit else "CREDIT",
                        currency=body.currency,
                        amount=body.amount,
                        exchange_rate=body.exchange_rate,
                    ),
                    JournalLineCreate(
                        account_id=offset.id,
                        side="CREDIT" if debit else "DEBIT",
                        currency=counterpart_currency,
                        amount=body.amount if counterpart_currency == body.currency else base,
                        exchange_rate=body.exchange_rate
                        if counterpart_currency == body.currency
                        else Decimal(1),
                    ),
                ],
            )
        )
        journal = await create_in_transaction(
            db,
            access,
            draft,
            kind=body.kind,
            source_system=body.source_system,
            source_type=body.source_type,
            source_id=body.source_id,
            tax=outcome,
        )
        existing = await db.scalar(
            select(SourceDocument).where(
                SourceDocument.company_id == account.company_id,
                SourceDocument.journal_id == journal.id,
            )
        )
        from accounting.tasks.voucher_tax import source_request

        request = source_request(body)
        if existing:
            if canonical_json(existing.payload["request"]) != canonical_json(request):
                raise ConflictError(
                    "source identity was reused with different party document content"
                )
            return FinancialEffect(existing)
        payload = {
            "request": request,
            "terms": snapshot,
            "installments": [
                {
                    "sequence": item.sequence,
                    "amount": str(item.amount),
                    "due_date": item.due_date.isoformat(),
                }
                for item in installments
            ],
        }
        row = await create_row(
            db,
            access,
            "source_document",
            journal_id=journal.id,
            account_id=account.id,
            party_id=account.party_id,
            role=role,
            status="DRAFT",
            kind=body.kind,
            direction=direction,
            currency=body.currency,
            amount=body.amount,
            posting_date=body.posting_date,
            reference=body.reference,
            payload=payload,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["source_document"],
        "create",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        status=201,
    )

"""Snapshot-based overdue previews with allocation history and coverage guards."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.charges import ChargeTerms, Movement, total_charge
from accounting.models.charges import ChargeAssessment, ChargePolicy
from accounting.models.ledger import Journal, JournalLine
from accounting.models.subledger import Allocation, OpenItem
from accounting.schemas.charges import ChargePreview, ChargeRequest
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.subledger_reads import require_inputs


async def preview(
    db: AsyncSession, access: Access, body: ChargeRequest, *, exclude: uuid.UUID | None = None
) -> ChargePreview:
    require_inputs(access)
    require_fields(
        access,
        "charge_policy",
        {
            "account_id",
            "currency",
            "valid_from",
            "valid_to",
            "accrual_start_date",
            "method",
            "rate",
            "rate_period",
            "compound",
            "basis",
            "day_basis",
            "grace_days",
            "minimum",
            "cap",
            "charge_on_charge",
            "tax_treatment",
            "offset_account_id",
        },
    )
    require_fields(
        access,
        "charge_assessment",
        {
            "item_id",
            "policy_id",
            "coverage_start_date",
            "coverage_end_date",
            "amount",
            "cumulative_amount",
            "status",
            "snapshot",
            "input_hash",
        },
    )
    facts = financial_context(access)
    item = await company_object(db, OpenItem, body.item_id, company_id=access.context.company_id)
    if item.due_date is None or item.document_date is None:
        raise ConflictError(
            "unknown-date on-account balances cannot accrue automatic overdue charges"
        )
    policy = await company_object(db, ChargePolicy, body.policy_id, company_id=item.company_id)
    if (
        item.direction != "DEBT"
        or item.reversal_date is not None
        or policy.account_id != item.account_id
        or policy.currency != item.currency
    ):
        raise ConflictError("charge policy must match an unreversed debt item")
    line = await company_object(db, JournalLine, item.journal_line_id, company_id=item.company_id)
    journal = await company_object(db, Journal, line.journal_id, company_id=item.company_id)
    if journal.kind == "CHARGE" and not policy.charge_on_charge:
        raise ConflictError("this policy excludes charges on charges")
    try:
        origin = max(
            item.due_date + dt.timedelta(days=policy.grace_days + 1),
            policy.accrual_start_date,
            policy.valid_from,
            facts.books_begin_date,
            item.posting_date,
        )
        today = utcnow().astimezone(ZoneInfo(facts.timezone)).date()
        if body.coverage_end_date > today + dt.timedelta(days=1):
            raise ValidationFailedError("charges cannot accrue beyond today")
        last_day = body.coverage_end_date - dt.timedelta(days=1)
    except OverflowError as exc:
        raise ValidationFailedError("charge dates exceed the supported range") from exc
    if body.posting_date < last_day or body.due_date < body.posting_date:
        raise ValidationFailedError("charge posting or due date precedes its coverage")
    if policy.valid_to is not None and last_day > policy.valid_to:
        raise ConflictError("charge coverage extends beyond the policy's effective dates")
    prior = list(
        await db.scalars(
            select(ChargeAssessment)
            .where(
                ChargeAssessment.company_id == item.company_id,
                ChargeAssessment.item_id == item.id,
                ChargeAssessment.status.not_in(["REVERSED", "REJECTED"]),
                *([ChargeAssessment.id != exclude] if exclude else []),
            )
            .order_by(ChargeAssessment.coverage_end_date.desc())
            .limit(2)
        )
    )
    previous = prior[0] if prior else None
    if previous and previous.status in {"DRAFT", "APPROVED"}:
        raise ConflictError("complete the pending charge assessment before another run")
    start = max(origin, previous.coverage_end_date) if previous else origin
    if body.coverage_end_date <= start:
        raise ConflictError("charge interval is empty or already covered")
    stored = list(
        await db.scalars(
            select(Allocation)
            .where(
                Allocation.company_id == item.company_id,
                Allocation.debt_item_id == item.id,
                Allocation.posting_date < body.coverage_end_date,
            )
            .order_by(Allocation.id)
            .limit(10001)
        )
    )
    if len(stored) > 10000:
        raise ConflictError("charge history exceeds the supported movement capacity")
    movements = []
    evidence = []
    for row in stored:
        movements.append(Movement(row.posting_date, row.amount))
        if row.reversal_date is not None and row.reversal_date < body.coverage_end_date:
            movements.append(Movement(row.reversal_date, -row.amount))
        evidence.append(
            {
                "id": str(row.id),
                "amount": str(row.amount),
                "posting_date": row.posting_date.isoformat(),
                "reversal_date": row.reversal_date.isoformat()
                if row.reversal_date is not None and row.reversal_date < body.coverage_end_date
                else None,
            }
        )
    terms = ChargeTerms(
        policy.method,
        policy.rate,
        policy.rate_period,
        policy.compound,
        policy.basis,
        policy.day_basis,
        policy.minimum,
        policy.cap,
    )
    total = total_charge(
        item.amount,
        origin,
        body.coverage_end_date,
        tuple(movements),
        terms,
        precision=facts.amount_precision,
        rounding=facts.rounding_mode,
    )
    already = (
        previous.cumulative_amount if previous and previous.policy_id == policy.id else Decimal(0)
    )
    if policy.method == "FIXED":
        fixed_before = await db.scalar(
            select(ChargeAssessment.id)
            .where(
                ChargeAssessment.company_id == item.company_id,
                ChargeAssessment.item_id == item.id,
                ChargeAssessment.status.in_(["POSTED", "WAIVED"]),
                ChargeAssessment.snapshot["terms"]["method"].as_string() == "FIXED",
                *([ChargeAssessment.id != exclude] if exclude else []),
            )
            .limit(1)
        )
        if fixed_before:
            total = already
    if total < already:
        raise ConflictError("charge inputs changed after earlier coverage")
    snapshot = {
        "request": body.model_dump(mode="json"),
        "origin": origin.isoformat(),
        "principal": str(item.amount),
        "item_version": item.row_version,
        "policy_version": policy.row_version,
        "allocations": evidence,
        "previous_id": str(previous.id) if previous else None,
        "already_assessed": str(already),
        "precision": facts.amount_precision,
        "rounding": facts.rounding_mode.value,
        "terms": {
            "method": policy.method,
            "rate": str(policy.rate),
            "rate_period": policy.rate_period,
            "compound": policy.compound,
            "basis": policy.basis,
            "day_basis": policy.day_basis,
            "minimum": str(policy.minimum),
            "cap": str(policy.cap) if policy.cap is not None else None,
        },
    }
    fingerprint = hashlib.sha256(canonical_json(snapshot)).hexdigest()
    return ChargePreview(
        item_id=item.id,
        policy_id=policy.id,
        coverage_start_date=start,
        coverage_end_date=body.coverage_end_date,
        currency=item.currency,
        amount=total - already,
        cumulative_amount=total,
        input_hash=fingerprint,
        snapshot=snapshot,
    )

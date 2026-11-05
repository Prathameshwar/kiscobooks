"""Company-scoped, reviewed exchange quotes and exact conversion previews."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import uuid
from decimal import Decimal, localcontext
from typing import cast

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.money import MoneyError, quantize_storage, round_for_display
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import CursorCodec
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.reference import validate_reference
from accounting.models.exchange_rates import ExchangeRateQuote
from accounting.schemas.exchange_rates import (
    RateCandidate,
    RateConversion,
    RateConversionView,
    RateDecision,
    RateImport,
    RateListItem,
    RateListQuery,
    RateView,
)
from accounting.tasks.access import authority_fingerprint


def authorize(access: Access, write: bool) -> None:
    access.actor.require_scope(
        "accounting.finance.manage" if write else "accounting.finance.read",
        target=ScopePath(company_id=access.context.company_id),
    )


def view(row: ExchangeRateQuote) -> RateView:
    return RateView.model_validate(row, from_attributes=True)


def emit_change(
    db: AsyncSession, access: Access, row: ExchangeRateQuote, action: str, reason: str | None = None
) -> None:
    event = f"accounting.exchange_rate_quote.{action}"
    emit(
        db,
        aggregate_type="accounting.exchange_rate_quote",
        aggregate_id=row.id,
        event_type=event,
        tenant_id=access.actor.tenant_id,
        payload=audit_payload(
            action=event,
            category="money",
            entity_type="accounting.exchange_rate_quote",
            entity_id=row.id,
            actor_user_id=access.actor.user_id,
            company_id=row.company_id,
            reason=reason,
            changes={"status": {"to": row.status}, "source_kind": {"to": row.source_kind}},
        )
        | {"actor_type": "user"},
    )


def validate_scope(access: Access, body: RateCandidate) -> None:
    context = access.context
    validate_reference(None, None, [body.from_currency, body.to_currency])
    if "multi_currency" not in context.features:
        raise ConflictError("multi_currency is disabled")
    if (
        body.from_currency not in context.allowed_currencies
        or body.to_currency != context.base_currency
    ):
        raise ConflictError("rate pair is not enabled for this company")
    if (body.purpose == "GST_GOODS") != (body.source_kind == "CUSTOMS"):
        raise ValidationFailedError("GST goods quotes require a Customs-notified source")
    if body.source_kind == "CSV" and not body.source_reference.startswith("csv:"):
        raise ValidationFailedError("CSV source reference must identify its import")


async def candidate(
    db: AsyncSession,
    access: Access,
    body: RateCandidate,
    *,
    csv_sha256: str | None = None,
) -> RateView:
    authorize(access, True)
    validate_scope(access, body)
    if csv_sha256 is None and body.source_kind == "CSV":
        raise ValidationFailedError("use the CSV import route for CSV rates")
    if csv_sha256 is not None and body.source_kind != "CSV":
        raise ValidationFailedError("CSV import accepts CSV rates only")
    row = ExchangeRateQuote(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=access.context.company_id,
        from_currency=body.from_currency,
        to_currency=body.to_currency,
        purpose=body.purpose,
        effective_date=body.effective_date,
        rate=body.rate,
        source_kind=body.source_kind,
        source_reference=body.source_reference,
        source_sha256=csv_sha256
        or hashlib.sha256(canonical_json(body.model_dump(mode="json"))).hexdigest(),
        status="CANDIDATE",
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
    )
    db.add(row)
    emit_change(db, access, row, "create")
    await db.flush()
    return view(row)


async def import_csv(db: AsyncSession, access: Access, body: RateImport) -> list[RateView]:
    authorize(access, True)
    digest = hashlib.sha256(body.csv_text.encode()).hexdigest()
    reader = csv.DictReader(io.StringIO(body.csv_text, newline=""))
    required = {"from_currency", "to_currency", "purpose", "effective_date", "rate"}
    if (
        reader.fieldnames is None
        or len(reader.fieldnames) != len(required)
        or set(reader.fieldnames) != required
    ):
        raise ValidationFailedError("CSV header must contain only the required rate columns")
    rows = list(reader)
    if not 1 <= len(rows) <= 500:
        raise ValidationFailedError("CSV import must contain 1 to 500 rates")
    try:
        parsed = [
            RateCandidate.model_validate(
                entry
                | {"source_kind": "CSV", "source_reference": f"csv:{body.source_reference}:{index}"}
            )
            for index, entry in enumerate(rows, 2)
        ]
    except ValidationError as exc:
        raise ValidationFailedError("CSV rate row failed validation") from exc
    return [await candidate(db, access, entry, csv_sha256=digest) for entry in parsed]


async def get(
    db: AsyncSession, access: Access, quote_id: uuid.UUID, *, lock: bool = False
) -> ExchangeRateQuote:
    query = select(ExchangeRateQuote).where(
        ExchangeRateQuote.id == quote_id,
        ExchangeRateQuote.company_id == access.context.company_id,
    )
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFoundError("exchange quote not found")
    return row


async def listing(
    db: AsyncSession, access: Access, query: RateListQuery, secret: bytes
) -> Page[RateListItem]:
    authorize(access, False)
    if query.q or query.sort not in (None, "id", "-id"):
        raise ValidationFailedError("unsupported rate search or sort")
    model = ExchangeRateQuote
    statement = select(
        model.id,
        model.from_currency,
        model.to_currency,
        model.purpose,
        model.effective_date,
        model.rate,
        model.source_kind,
        model.status,
    ).where(model.company_id == access.context.company_id)
    for name in ("from_currency", "purpose", "status", "effective_date"):
        value = getattr(query, name)
        if value is not None:
            statement = statement.where(getattr(model, name) == value)
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "exchange_rate_quote",
            "tenant": str(access.actor.tenant_id),
            "company": str(access.context.company_id),
            "authority": authority_fingerprint(access),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=lambda row: RateListItem.model_validate(dict(row)),
    )


async def decide(
    db: AsyncSession, access: Access, quote_id: uuid.UUID, body: RateDecision, action: str
) -> RateView:
    authorize(access, True)
    if action not in {"approve", "withdraw"}:
        raise ValidationFailedError("unsupported rate decision")
    row = await get(db, access, quote_id, lock=True)
    if row.row_version != body.expected_version:
        raise ConflictError("exchange quote version changed")
    if action == "approve":
        if row.status != "CANDIDATE" or row.created_by == access.actor.user_id:
            raise ConflictError("approval requires a separate reviewer and a candidate")
        validate_scope(
            access,
            RateCandidate.model_validate(
                {
                    "from_currency": row.from_currency,
                    "to_currency": row.to_currency,
                    "purpose": row.purpose,
                    "effective_date": row.effective_date,
                    "rate": row.rate,
                    "source_kind": row.source_kind,
                    "source_reference": row.source_reference,
                }
            ),
        )
        row.status = "APPROVED"
        row.approved_by = access.actor.user_id
        row.approved_at = utcnow()
        row.approval_reason = body.reason
    else:
        if row.status != "APPROVED":
            raise ConflictError("only an approved quote may be withdrawn")
        row.status = "WITHDRAWN"
        row.withdrawn_by = access.actor.user_id
        row.withdrawn_at = utcnow()
        row.withdrawal_reason = body.reason
    row.updated_by = access.actor.user_id
    row.row_version += 1
    emit_change(db, access, row, action, body.reason)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "an approved rate already exists for this currency, date and purpose"
        ) from exc
    return view(row)


async def effective(
    db: AsyncSession,
    access: Access,
    from_currency: str,
    purpose: str,
    effective_date: dt.date,
) -> RateView:
    authorize(access, False)
    if "multi_currency" not in access.context.features:
        raise ConflictError("multi_currency is disabled")
    if from_currency not in access.context.allowed_currencies:
        raise ConflictError("rate currency is not enabled for this company")
    row = await db.scalar(
        select(ExchangeRateQuote).where(
            ExchangeRateQuote.company_id == access.context.company_id,
            ExchangeRateQuote.from_currency == from_currency,
            ExchangeRateQuote.to_currency == access.context.base_currency,
            ExchangeRateQuote.purpose == purpose,
            ExchangeRateQuote.effective_date == effective_date,
            ExchangeRateQuote.status == "APPROVED",
        )
    )
    if row is None:
        raise NotFoundError("no approved rate exists for this exact date and purpose")
    return view(row)


async def approved_for(
    db: AsyncSession,
    company_id: uuid.UUID,
    from_currency: str,
    to_currency: str,
    purpose: str,
    effective_date: dt.date,
) -> ExchangeRateQuote | None:
    """Internal exact-date lookup under an already authorized financial command."""
    return cast(
        ExchangeRateQuote | None,
        await db.scalar(
            select(ExchangeRateQuote)
            .where(
                ExchangeRateQuote.company_id == company_id,
                ExchangeRateQuote.from_currency == from_currency,
                ExchangeRateQuote.to_currency == to_currency,
                ExchangeRateQuote.purpose == purpose,
                ExchangeRateQuote.effective_date == effective_date,
                ExchangeRateQuote.status == "APPROVED",
            )
            .with_for_update(read=True)
        ),
    )


async def previously_reviewed(
    db: AsyncSession,
    company_id: uuid.UUID,
    from_currency: str,
    to_currency: str,
    purpose: str,
    effective_date: dt.date,
) -> bool:
    return (
        await db.scalar(
            select(ExchangeRateQuote.id)
            .where(
                ExchangeRateQuote.company_id == company_id,
                ExchangeRateQuote.from_currency == from_currency,
                ExchangeRateQuote.to_currency == to_currency,
                ExchangeRateQuote.purpose == purpose,
                ExchangeRateQuote.effective_date == effective_date,
                ExchangeRateQuote.status.in_(("APPROVED", "WITHDRAWN")),
            )
            .limit(1)
        )
        is not None
    )


async def convert(db: AsyncSession, access: Access, body: RateConversion) -> RateConversionView:
    quote = await effective(db, access, body.from_currency, body.purpose, body.effective_date)
    finance = access.context.finance
    if finance is None:
        raise ConflictError("financial company context is unavailable")
    try:
        with localcontext() as calculation:
            calculation.prec = 64
            amount = quantize_storage(
                round_for_display(
                    body.amount * Decimal(quote.rate),
                    finance.amount_precision,
                    finance.rounding_mode,
                )
            )
    except MoneyError as exc:
        raise ValidationFailedError("converted amount exceeds supported money precision") from exc
    return RateConversionView(
        rate_id=quote.id,
        rate=quote.rate,
        rate_date=quote.effective_date,
        source_reference=quote.source_reference,
        from_currency=quote.from_currency,
        to_currency=quote.to_currency,
        amount=body.amount,
        converted_amount=amount,
    )

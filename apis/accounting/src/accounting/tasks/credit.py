"""Credit exposure and source-bound reservations under the company write lock."""

import datetime as dt
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from billing_platform.db.access import company_object
from billing_platform.db.types import Money, utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.credit import decide
from accounting.domain.ledger import base_value
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.credit import CreditOverride, CreditReservation
from accounting.models.masters import Account, PartyCreditPolicy
from accounting.models.subledger import OpenItem, SourceDocument
from accounting.resources import BY_NAME
from accounting.schemas.credit import (
    CreditCheck,
    CreditDecision,
    CreditRequest,
    OverrideApprove,
    OverrideRequest,
    ReservationRenew,
)
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.subledger import SourceCreate
from accounting.tasks.access import authorize, readable
from accounting.tasks.commands import values_of
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.party_documents import enforce_holds, party_account, policy_at
from accounting.tasks.subledger_reads import remaining, require_inputs


def base_amount(access: Access, body: CreditCheck) -> Decimal:
    facts = financial_context(access)
    if (
        body.currency != access.context.base_currency
        and "multi_currency" not in access.context.features
    ):
        raise ConflictError("foreign credit requires multi_currency")
    from accounting.domain.reference import validate_reference

    validate_reference(None, None, [body.currency])
    return base_value(
        body.amount,
        body.currency,
        body.exchange_rate,
        access.context.base_currency,
        facts.amount_precision,
        facts.rounding_mode,
    )


def valid_expiry(expires_at: dt.datetime) -> None:
    if not utcnow() < expires_at <= utcnow() + dt.timedelta(days=7):
        raise ValidationFailedError("credit authorization must expire within seven days")


def policy_filters(account: Account, date: dt.date) -> tuple[ColumnElement[bool], ...]:
    return (
        PartyCreditPolicy.company_id == account.company_id,
        PartyCreditPolicy.party_id == account.party_id,
        PartyCreditPolicy.role == account.party_role,
        PartyCreditPolicy.valid_from <= date,
        (PartyCreditPolicy.valid_to.is_(None)) | (PartyCreditPolicy.valid_to >= date),
    )


async def can_constrain(
    db: AsyncSession, account: Account, date: dt.date, *, limits_enabled: bool
) -> bool:
    """Whether debt on this party account can be limited, so a posting must assess credit.

    With `credit_limits` off `decide` raises no reason, so `assess` can only ALLOW. With it on,
    a customer always has the company default limit and the overdue rules, and a supplier is
    unlimited unless a credit policy covers the date. Where `assess` can only ALLOW, posting
    must not demand read access to credit data it would never consult. Holds are enforced by
    the caller either way.
    """
    if not limits_enabled:
        return False
    if account.party_role == "CUSTOMER":
        return True
    found = await db.scalar(
        select(PartyCreditPolicy.id).where(*policy_filters(account, date)).limit(1)
    )
    return found is not None


async def assess(
    db: AsyncSession,
    access: Access,
    body: CreditCheck,
    *,
    exclude_reservation: uuid.UUID | None = None,
) -> CreditDecision:
    require_inputs(access)
    require_fields(
        access,
        "credit_reservation",
        {"party_id", "role", "currency", "amount", "base_amount", "status", "expires_at"},
    )
    account = await party_account(db, access, body.account_id)
    expected = (
        access.context.base_currency
        if account.currency_mode == "BASE"
        else account.currency
        if account.currency_mode == "FIXED"
        else body.currency
    )
    if body.currency != expected:
        raise ValidationFailedError("credit currency differs from its account")
    policy = await policy_at(db, access, account, body.posting_date)
    enforce_holds(policy, "INVOICE" if account.party_role == "CUSTOMER" else "BILL")
    facts = financial_context(access)
    controls = list(
        await db.scalars(
            select(PartyCreditPolicy).where(*policy_filters(account, body.posting_date)).limit(2)
        )
    )
    if len(controls) > 1:
        raise ConflictError("overlapping credit policies")
    control = controls[0] if controls else None
    if control:
        spec = BY_NAME["party_credit_policy"]
        authorize(access, spec, "read")
        if not {
            "limit_mode",
            "limit_amount",
            "currency",
            "enforcement",
            "overdue_days",
            "overdue_tolerance",
            "valid_from",
            "valid_to",
        } <= readable(access, spec, values_of(control, spec)):
            raise PermissionDeniedError("credit policy inputs are not readable")
    enabled = "credit_limits" in access.context.features
    if enabled and control and account.party_role == "SUPPLIER" and control.limit_mode == "INHERIT":
        raise ConflictError("supplier credit policy must explicitly choose limited or unlimited")
    currency = (
        control.currency
        if control and control.limit_mode != "INHERIT"
        else access.context.base_currency
    )
    base = currency == access.context.base_currency
    if not base and currency != body.currency:
        raise ConflictError("credit policy currency requires an explicit supported conversion")
    proposed_base = base_amount(access, body)
    proposed = proposed_base if base else body.amount
    limit = (
        (
            control.limit_amount
            if control.limit_mode == "LIMITED"
            else None
            if control.limit_mode == "UNLIMITED"
            else facts.credit_limit_default
        )
        if control
        else facts.credit_limit_default
        if account.party_role == "CUSTOMER"
        else None
    )
    # A backdated source cannot ignore debt already posted today. Future-dated debt
    # is included conservatively; future allocations do not reduce today's exposure.
    date = max(body.posting_date, utcnow().astimezone(ZoneInfo(facts.timezone)).date())
    amount = remaining(date, base=base)
    filters = [
        OpenItem.company_id == account.company_id,
        OpenItem.party_id == account.party_id,
        OpenItem.role == account.party_role,
        OpenItem.direction == "DEBT",
        (OpenItem.reversal_date.is_(None)) | (OpenItem.reversal_date > date),
    ]
    if not base:
        filters.append(OpenItem.currency == currency)
    exposure = await db.scalar(
        select(type_coerce(func.coalesce(func.sum(amount), 0), Money)).where(*filters)
    ) or Decimal(0)
    overdue = Decimal(0)
    unknown_due = await db.scalar(
        select(type_coerce(func.coalesce(func.sum(amount), 0), Money)).where(
            *filters, OpenItem.due_date.is_(None)
        )
    ) or Decimal(0)
    if control:
        overdue = await db.scalar(
            select(type_coerce(func.coalesce(func.sum(amount), 0), Money)).where(
                *filters, OpenItem.due_date < date - dt.timedelta(days=control.overdue_days)
            )
        ) or Decimal(0)
    reserve_filters = [
        CreditReservation.company_id == account.company_id,
        CreditReservation.party_id == account.party_id,
        CreditReservation.role == account.party_role,
        CreditReservation.status == "ACTIVE",
        CreditReservation.expires_at > utcnow(),
    ]
    if not base:
        reserve_filters.append(CreditReservation.currency == currency)
    if exclude_reservation:
        reserve_filters.append(CreditReservation.id != exclude_reservation)
    reserved = await db.scalar(
        select(
            type_coerce(
                func.coalesce(
                    func.sum(CreditReservation.base_amount if base else CreditReservation.amount), 0
                ),
                Money,
            )
        ).where(*reserve_filters)
    ) or Decimal(0)
    decision = decide(
        exposure,
        reserved,
        proposed,
        limit,
        overdue,
        control.overdue_tolerance if control else Decimal(0),
        control.enforcement if control else "BLOCK",
        enabled=enabled,
    )
    return CreditDecision(
        status=decision.status,
        currency=currency,
        exposure=exposure,
        reserved=reserved,
        proposed=proposed,
        projected=decision.projected,
        limit=limit,
        overdue=overdue,
        unknown_due=unknown_due,
        overdue_history_complete=unknown_due == 0,
        reasons=[*decision.reasons, *(["unknown_due_history"] if unknown_due else [])],
        policy_id=control.id if control else None,
        policy_version=control.row_version if control else None,
        assessed_date=date,
    )


def source_matches(
    row: CreditReservation | CreditOverride, body: CreditRequest | SourceCreate
) -> bool:
    return all(
        getattr(row, key) == getattr(body, key)
        for key in ("account_id", "currency", "amount", "source_system", "source_type", "source_id")
    )


async def enforce(
    db: AsyncSession,
    access: Access,
    decision: CreditDecision,
    body: CreditRequest | SourceCreate,
    override_id: uuid.UUID | None,
    *,
    reserved_override: bool = False,
) -> CreditOverride | None:
    if decision.status == "BLOCK":
        raise ConflictError("credit control blocked: " + ", ".join(decision.reasons))
    if decision.status != "OVERRIDE_REQUIRED":
        return None
    if override_id is None:
        raise ConflictError("a separately approved credit override is required")
    require_fields(
        access,
        "credit_override",
        {
            "account_id",
            "currency",
            "amount",
            "source_system",
            "source_type",
            "source_id",
            "status",
            "expires_at",
            "approved_by",
        },
    )
    row = await company_object(
        db, CreditOverride, override_id, company_id=access.context.company_id
    )
    if (
        not source_matches(row, body)
        or row.expires_at <= utcnow()
        or row.status not in ({"APPROVED", "USED"} if reserved_override else {"APPROVED"})
        or row.approved_by is None
        or row.approved_by == row.created_by
    ):
        raise ConflictError(
            "credit override is expired, used, unapproved or belongs to another source"
        )
    return row


async def reserve(
    factory: async_sessionmaker[AsyncSession], access: Access, body: CreditRequest, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        valid_expiry(body.expires_at)
        account = await party_account(db, access, body.account_id)
        existing = await db.scalar(
            select(CreditReservation).where(
                CreditReservation.company_id == account.company_id,
                CreditReservation.source_system == body.source_system,
                CreditReservation.source_type == body.source_type,
                CreditReservation.source_id == body.source_id,
            )
        )
        if existing:
            if (
                not source_matches(existing, body)
                or existing.base_amount != base_amount(access, body)
                or existing.expires_at != body.expires_at
                or existing.override_id != body.override_id
            ):
                raise ConflictError("credit source identity was reused with different content")
            return FinancialEffect(existing)
        from accounting.models.ledger import Journal

        posted = await db.scalar(
            select(Journal.id)
            .where(
                Journal.company_id == account.company_id,
                Journal.source_system == body.source_system,
                Journal.source_type == body.source_type,
                Journal.source_id == body.source_id,
                Journal.status == "POSTED",
            )
            .limit(1)
        )
        if posted:
            raise ConflictError("credit cannot be reserved for an already posted source")
        decision = await assess(db, access, body)
        override = await enforce(db, access, decision, body, body.override_id)
        row = await create_row(
            db,
            access,
            "credit_reservation",
            account_id=account.id,
            party_id=account.party_id,
            role=account.party_role,
            currency=body.currency,
            amount=body.amount,
            base_currency=access.context.base_currency,
            base_amount=base_amount(access, body),
            source_system=body.source_system,
            source_type=body.source_type,
            source_id=body.source_id,
            status="ACTIVE",
            expires_at=body.expires_at,
            journal_id=None,
            override_id=override.id if override else None,
            decision=decision.model_dump(mode="json"),
        )
        if override:
            await change_row(db, access, "credit_override", override, "consume", status="USED")
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["credit_reservation"],
        "reserve",
        body,
        key,
        mutate,
        permission="accounting.credit.manage",
        status=201,
    )


async def release(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, CreditReservation, object_id, company_id=access.context.company_id
        )
        if row.status != "ACTIVE" or row.row_version != body.expected_version:
            raise ConflictError("only a current active reservation can be released")
        await change_row(db, access, "credit_reservation", row, "release", status="RELEASED")
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["credit_reservation"],
        "release",
        body,
        key,
        mutate,
        permission="accounting.credit.manage",
        object_id=object_id,
    )


async def renew(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ReservationRenew,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        valid_expiry(body.expires_at)
        row = await company_object(
            db, CreditReservation, object_id, company_id=access.context.company_id
        )
        if row.status != "ACTIVE" or row.row_version != body.expected_version:
            raise ConflictError("only a current active reservation can be renewed")
        request = CreditRequest(
            account_id=row.account_id,
            currency=row.currency,
            amount=row.amount,
            exchange_rate=body.exchange_rate,
            posting_date=body.posting_date,
            source_system=row.source_system,
            source_type=row.source_type,
            source_id=row.source_id,
            expires_at=body.expires_at,
            override_id=row.override_id,
        )
        if base_amount(access, request) != row.base_amount:
            raise ConflictError("reservation renewal cannot change its exchange rate")
        decision = await assess(db, access, request, exclude_reservation=row.id)
        await enforce(db, access, decision, request, row.override_id, reserved_override=True)
        await change_row(
            db,
            access,
            "credit_reservation",
            row,
            "update",
            expires_at=body.expires_at,
            decision=decision.model_dump(mode="json"),
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["credit_reservation"],
        "renew",
        body,
        key,
        mutate,
        permission="accounting.credit.manage",
        object_id=object_id,
    )


async def request_override(
    factory: async_sessionmaker[AsyncSession], access: Access, body: OverrideRequest, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        valid_expiry(body.expires_at)
        if body.override_id is not None:
            raise ValidationFailedError("an override request cannot reference another override")
        decision = await assess(db, access, body)
        if decision.status != "OVERRIDE_REQUIRED":
            raise ConflictError("the policy does not permit or require an override")
        row = await create_row(
            db,
            access,
            "credit_override",
            account_id=body.account_id,
            currency=body.currency,
            amount=body.amount,
            source_system=body.source_system,
            source_type=body.source_type,
            source_id=body.source_id,
            status="REQUESTED",
            expires_at=body.expires_at,
            reason=body.reason,
            approved_by=None,
            approved_at=None,
            decision=decision.model_dump(mode="json"),
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["credit_override"],
        "request",
        body,
        key,
        mutate,
        permission="accounting.credit.manage",
        status=201,
    )


async def approve_override(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: OverrideApprove,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, CreditOverride, object_id, company_id=access.context.company_id
        )
        if (
            row.status != "REQUESTED"
            or row.row_version != body.expected_version
            or row.expires_at <= utcnow()
        ):
            raise ConflictError("override request is stale or expired")
        if row.created_by == access.actor.user_id:
            raise PermissionDeniedError("credit override requires a different approver")
        await change_row(
            db,
            access,
            "credit_override",
            row,
            "approve",
            status="APPROVED" if body.approve else "REJECTED",
            approved_by=access.actor.user_id,
            approved_at=utcnow(),
            reason=body.reason,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["credit_override"],
        "approve",
        body,
        key,
        mutate,
        permission="accounting.credit.override_approve",
        object_id=object_id,
    )


async def source_control(
    db: AsyncSession, access: Access, source: SourceDocument, *, consume: bool = False
) -> None:
    if source.direction != "DEBT":
        return
    body = SourceCreate.model_validate(source.payload["request"])
    request = CreditCheck(
        account_id=body.account_id,
        currency=body.currency,
        amount=body.amount,
        exchange_rate=body.exchange_rate,
        posting_date=body.posting_date,
    )
    reservation = None
    if body.credit_reservation_id:
        reservation = await company_object(
            db, CreditReservation, body.credit_reservation_id, company_id=source.company_id
        )
        if (
            not source_matches(reservation, body)
            or reservation.status != "ACTIVE"
            or reservation.expires_at <= utcnow()
            or reservation.base_amount != base_amount(access, request)
        ):
            raise ConflictError(
                "credit reservation is expired, consumed or belongs to another source"
            )
    decision = await assess(
        db, access, request, exclude_reservation=reservation.id if reservation else None
    )
    override = await enforce(
        db,
        access,
        decision,
        body,
        reservation.override_id if reservation else body.credit_override_id,
        reserved_override=reservation is not None,
    )
    if consume:
        if reservation:
            await change_row(
                db,
                access,
                "credit_reservation",
                reservation,
                "consume",
                status="CONSUMED",
                journal_id=source.journal_id,
            )
        if override and override.status == "APPROVED":
            await change_row(db, access, "credit_override", override, "consume", status="USED")
        await change_row(
            db,
            access,
            "source_document",
            source,
            "update",
            payload=source.payload | {"credit_decision": decision.model_dump(mode="json")},
        )

"""Financial context and local guard boundary tests."""

import datetime as dt
import secrets
import time
from dataclasses import replace
from decimal import Decimal

import pytest
from pydantic import ValidationError

from billing_platform.authz import Grant, Scope
from billing_platform.company_context import (
    CompanyContext,
    FinancialContext,
    sign_company_context,
    verify_company_context,
)
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode
from billing_platform.posting import PostingPeriod, assert_postable


def facts() -> FinancialContext:
    return FinancialContext(
        configuration_hash="a" * 64,
        company_active=True,
        books_begin_date=dt.date(2026, 4, 1),
        fiscal_year_start_month=4,
        fiscal_year_start_day=1,
        amount_precision=2,
        rounding_mode=RoundingMode.HALF_UP,
        default_payment_terms_days=30,
        credit_limit_default=Decimal("50000.0000"),
        timezone="Asia/Kolkata",
    )


def scenario(
    permissions: frozenset[str] = frozenset({"period.post"}),
) -> tuple[Actor, CompanyContext, PostingPeriod]:
    tenant, company, user = uuid7(), uuid7(), uuid7()
    actor = Actor(
        tenant,
        user,
        (
            Grant(
                permissions=permissions,
                scope=Scope("company", company),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    context = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        base_currency="INR",
        finance=facts(),
    )
    period = PostingPeriod(
        uuid7(), tenant, company, dt.date(2026, 4, 1), dt.date(2026, 4, 30), "OPEN"
    )
    return actor, context, period


def test_signed_financial_facts_and_master_compatibility() -> None:
    import base64
    import json

    actor, context, _ = scenario()
    secret = secrets.token_bytes(32)
    token, signature = sign_company_context(context, secret)
    wire = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    assert "report_display" not in wire  # Old non-Reports readers forbid unknown fields.
    verified = verify_company_context(token, signature, secret)
    assert verified == context
    assert verified.finance is not None
    assert type(verified.finance.credit_limit_default) is Decimal
    legacy = context.model_dump()
    legacy.pop("finance")
    assert CompanyContext.model_validate(legacy).finance is None
    with pytest.raises(AuthenticationRequiredError):
        verify_company_context(token, "0" * 64, secret)
    with pytest.raises(AuthenticationRequiredError):
        verified.assert_current(actor, uuid7())


def test_signed_company_currency_allowance_is_bounded_and_strict() -> None:
    _, context, _ = scenario()
    values = context.model_dump()
    values["allowed_currencies"] = ["USD"]
    reviewed = CompanyContext.model_validate(values)
    secret = secrets.token_bytes(32)
    token, signature = sign_company_context(reviewed, secret)
    assert verify_company_context(token, signature, secret).allowed_currencies == frozenset({"USD"})
    values["allowed_currencies"] = ["usd"]
    with pytest.raises(ValidationError):
        CompanyContext.model_validate(values)
    values["allowed_currencies"] = [
        chr(65 + index // 26) + chr(65 + index % 26) + "A" for index in range(65)
    ]
    with pytest.raises(ValidationError):
        CompanyContext.model_validate(values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("credit_limit_default", 0.1),
        ("credit_limit_default", True),
        ("cash_receipt_limit", "NaN"),
        ("cash_receipt_limit", "0.00001"),
        ("credit_limit_default", "-1"),
        ("credit_limit_default", "1000000000000000"),
        ("timezone", "invalid/timezone"),
        ("fiscal_year_start_month", 13),
        ("fiscal_year_start_month", 2),
        ("version", 2),
    ],
)
def test_financial_context_rejects_inexact_or_invalid_facts(field: str, value: object) -> None:
    values = facts().model_dump() | {"fiscal_year_start_day": 30, field: value}
    with pytest.raises(ValidationError):
        FinancialContext.model_validate(values)


@pytest.mark.parametrize("status", ["FUTURE", "CLOSED", "LOCKED", "UNKNOWN"])
def test_closed_and_unknown_periods_reject_every_actor(status: str) -> None:
    actor, context, period = scenario(
        frozenset({"period.post", "period.post_adjustment", "period.lock"})
    )
    with pytest.raises(ConflictError):
        assert_postable(
            context.company_id,
            period.start_date,
            actor,
            context=context,
            period=replace(period, status=status),
        )


def test_guard_checks_scope_dates_authority_and_missing_facts() -> None:
    actor, context, period = scenario()
    assert (
        assert_postable(
            context.company_id, period.start_date, actor, context=context, period=period
        )
        == period
    )
    with pytest.raises(ConflictError, match="context"):
        assert_postable(
            context.company_id,
            period.start_date,
            actor,
            context=context.model_copy(update={"finance": None}),
            period=period,
        )
    with pytest.raises(ConflictError, match="active"):
        assert_postable(
            context.company_id,
            period.start_date,
            actor,
            context=context.model_copy(
                update={"finance": facts().model_copy(update={"company_active": False})}
            ),
            period=period,
        )
    with pytest.raises(ValidationFailedError, match="books begin"):
        assert_postable(
            context.company_id, dt.date(2026, 3, 31), actor, context=context, period=period
        )
    with pytest.raises(ConflictError, match="generated"):
        assert_postable(context.company_id, period.start_date, actor, context=context, period=None)
    for foreign in (replace(period, tenant_id=uuid7()), replace(period, company_id=uuid7())):
        with pytest.raises(PermissionDeniedError):
            assert_postable(
                context.company_id, period.start_date, actor, context=context, period=foreign
            )
    with pytest.raises(ConflictError, match="outside"):
        assert_postable(
            context.company_id, dt.date(2026, 5, 1), actor, context=context, period=period
        )
    with pytest.raises(PermissionDeniedError):
        assert_postable(
            context.company_id,
            period.start_date,
            replace(actor, grants=()),
            context=context,
            period=period,
        )
    with pytest.raises(PermissionDeniedError, match="support"):
        assert_postable(
            context.company_id,
            period.start_date,
            replace(actor, impersonation_id=uuid7()),
            context=context,
            period=period,
        )
    with pytest.raises(PermissionDeniedError, match="adjustment"):
        assert_postable(
            context.company_id,
            period.start_date,
            actor,
            context=context,
            period=replace(period, status="SOFT_CLOSED"),
        )


def test_backdate_limit_uses_company_timezone_and_scoped_adjustment_authority() -> None:
    actor, context, period = scenario()
    context = context.model_copy(
        update={"finance": facts().model_copy(update={"backdated_posting_limit_days": 0})}
    )
    at = dt.datetime(2026, 4, 2, 18, 29, tzinfo=dt.UTC)
    assert_postable(
        context.company_id, dt.date(2026, 4, 2), actor, context=context, period=period, now=at
    )
    with pytest.raises(PermissionDeniedError, match="backdated"):
        assert_postable(
            context.company_id,
            dt.date(2026, 4, 2),
            actor,
            context=context,
            period=period,
            now=at + dt.timedelta(minutes=1),
        )
    adjusted = replace(
        actor,
        grants=(
            *actor.grants,
            Grant(
                permissions=frozenset({"period.post_adjustment"}),
                scope=Scope("company", context.company_id),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    assert_postable(
        context.company_id,
        period.start_date,
        adjusted,
        context=context,
        period=replace(period, status="SOFT_CLOSED"),
        now=at,
    )
    foreign = replace(
        actor,
        grants=(
            *actor.grants,
            Grant(
                permissions=frozenset({"period.post_adjustment"}),
                scope=Scope("company", uuid7()),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    with pytest.raises(PermissionDeniedError, match="backdated"):
        assert_postable(
            context.company_id, period.start_date, foreign, context=context, period=period, now=at
        )
    with pytest.raises(ValueError, match="aware"):
        assert_postable(
            context.company_id,
            period.start_date,
            actor,
            context=context,
            period=period,
            now=dt.datetime(2026, 4, 2),
        )

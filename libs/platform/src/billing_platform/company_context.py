"""Bounded gateway company facts, bound to the verified actor and a short lifetime.

The owner selects the facts and resolves policy subjects. Consumers still enforce
their own native fields, permissions and business rules inside local transactions.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import time
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from billing_platform.display import DisplayConfiguration
from billing_platform.errors import AuthenticationRequiredError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.money import RoundingMode


class FinancialContext(BaseModel):
    """Versioned Identity facts. Absence supports older master-only consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_active: bool = Field(strict=True)
    books_begin_date: dt.date
    fiscal_year_start_month: int = Field(strict=True, ge=1, le=12)
    fiscal_year_start_day: int = Field(strict=True, ge=1, le=31)
    amount_precision: int = Field(strict=True, ge=0, le=4)
    rounding_mode: RoundingMode
    default_payment_terms_days: int = Field(strict=True, ge=0, le=3650)
    credit_limit_default: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False
    )
    cash_receipt_limit: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False
    )
    backdated_posting_limit_days: int | None = Field(default=None, strict=True, ge=0)
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("credit_limit_default", "cash_receipt_limit", mode="before")
    @classmethod
    def exact_money(cls, value: Any) -> Any:
        if isinstance(value, float | bool):
            raise ValueError("money requires an exact decimal")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown company timezone") from exc
        return value

    @model_validator(mode="after")
    def valid_calendar(self) -> FinancialContext:
        dt.date(2000, self.fiscal_year_start_month, self.fiscal_year_start_day)
        return self


class CompanyContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    issued_at: int = Field(strict=True)
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    policy_namespaces: frozenset[Literal["accounting", "catalog", "vouchers", "reports"]] = (
        frozenset()
    )
    finance: FinancialContext | None = None
    report_display: DisplayConfiguration | None = None
    features: frozenset[str] = frozenset()
    allowed_currencies: frozenset[Annotated[str, Field(pattern=r"^[A-Z]{3}$")]] = Field(
        default_factory=frozenset, max_length=64
    )
    registrations: tuple[dict[str, Any], ...] = Field(default=(), max_length=200)
    bank_ids: frozenset[uuid.UUID] = Field(default=frozenset(), max_length=200)
    # Subject and scope applicability is resolved by Identity, not the browser.
    policies: tuple[dict[str, Any], ...] = Field(default=(), max_length=1000)
    layouts: tuple[dict[str, Any], ...] = Field(default=(), max_length=1000)

    def assert_current(self, actor: Actor, company_id: uuid.UUID) -> None:
        if (
            abs(time.time() - self.issued_at) > 60
            or self.tenant_id != actor.tenant_id
            or self.user_id != actor.user_id
            or self.company_id != company_id
            or company_id.int == 0
        ):
            raise AuthenticationRequiredError("company context is expired or has a different scope")


def sign_company_context(context: CompanyContext, secret: bytes) -> tuple[str, str]:
    values = context.model_dump(mode="json")
    # Readers-first rollout: older non-Reports consumers forbid unknown fields.
    # Identity sends this extension only on the Reports gateway route.
    if context.report_display is None:
        values.pop("report_display")
    body = canonical_json(values, maximum_bytes=24576)
    signature = hmac.new(secret, b"company-context.v1\n" + body, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(body).rstrip(b"=").decode(), signature


def verify_company_context(token: str, signature: str, secret: bytes) -> CompanyContext:
    try:
        if not 1 <= len(token) <= 32768 or len(signature) != 64:
            raise ValueError("context bounds")
        body = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        expected = hmac.new(secret, b"company-context.v1\n" + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        return CompanyContext.model_validate_json(body)
    except (ValueError, ValidationError) as exc:
        raise AuthenticationRequiredError("invalid company context") from exc

"""Typed stable quota identity and exact proposed caps; no live consumption."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class LimitIdentity:
    scope_kind: str
    metric: str
    period_basis: str
    timezone: str
    currency: str | None = None
    unit_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope_kind not in {"CAMPAIGN", "PROMOTION", "PROGRAM"}:
            raise ValidationFailedError("limit scope must be campaign, promotion or program")
        if self.metric not in {
            "TOTAL_USES",
            "PER_CUSTOMER_USES",
            "PER_ORDER_USES",
            "REWARD_UNITS",
            "BUDGET",
        }:
            raise ValidationFailedError("unsupported native limit metric")
        if self.period_basis not in {"LIFETIME", "DAY", "MONTH", "YEAR", "ORDER"} or (
            self.metric == "PER_ORDER_USES"
        ) != (self.period_basis == "ORDER"):
            raise ValidationFailedError(
                "per-order limits require order scope; other limits use a declared period"
            )
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValidationFailedError("limit periods require an IANA timezone") from exc
        if (self.metric == "BUDGET") != (self.currency is not None) or (
            self.metric == "REWARD_UNITS"
        ) != (self.unit_id is not None):
            raise ValidationFailedError(
                "budget limits require currency; reward quantity limits require a unit"
            )
        if self.currency is not None and (
            len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isupper()
            or not self.currency.isalpha()
        ):
            raise ValidationFailedError("limit currency must use an ISO code")
        if self.unit_id is not None and self.unit_id.int == 0:
            raise ValidationFailedError("limit unit must be a real native identity")


def validate_cap(
    identity: LimitIdentity,
    *,
    maximum_count: int | None = None,
    maximum_quantity: Decimal | None = None,
    maximum_amount: Decimal | None = None,
) -> int | Decimal:
    count = identity.metric not in {"REWARD_UNITS", "BUDGET"}
    if count:
        if (
            type(maximum_count) is not int
            or not 1 <= maximum_count <= 2**63 - 1
            or maximum_quantity is not None
            or maximum_amount is not None
        ):
            raise ValidationFailedError("count caps require one positive signed-64-bit integer")
        return maximum_count
    if (
        maximum_count is not None
        or (identity.metric == "REWARD_UNITS") != (maximum_quantity is not None)
        or (identity.metric == "BUDGET") != (maximum_amount is not None)
    ):
        raise ValidationFailedError("limit cap must match its stable metric")
    value = maximum_amount if identity.metric == "BUDGET" else maximum_quantity
    assert value is not None
    try:
        exact = exact_decimal(value)
    except MoneyError as exc:
        raise ValidationFailedError("limit cap must be an exact native amount or quantity") from exc
    if exact <= 0:
        raise ValidationFailedError("limit cap must be positive")
    return exact

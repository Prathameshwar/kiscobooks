"""Exact source-component entitlements, independent of today's prices and tax recipes.

The owner supplies committed/reserved claims under its company fence. Final eligible
claims receive the original residual; nonreturnable fees never become a refund.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_calculation import exact, money


@dataclass(frozen=True)
class Entitlement:
    key: str
    amount: Decimal
    treatment: str = "PROPORTIONAL"


@dataclass(frozen=True)
class ReturnClaim:
    basis: Decimal
    amounts: tuple[tuple[str, Decimal], ...]


def allocate(
    original_basis: Decimal,
    entitlements: tuple[Entitlement, ...],
    previous: tuple[ReturnClaim, ...],
    requested_basis: Decimal,
    *,
    precision: int,
    rounding_mode: str,
) -> ReturnClaim:
    basis, requested = exact(original_basis), exact(requested_basis)
    if basis <= 0 or requested <= 0 or not 1 <= len(entitlements) <= 410 or len(previous) > 1000:
        raise ValidationFailedError("return requires a positive bounded original basis")
    source = {row.key: row for row in entitlements}
    if len(source) != len(entitlements) or any(not key or len(key) > 100 for key in source):
        raise ValidationFailedError("return source components must have distinct native identities")
    for row in entitlements:
        value = exact(row.amount)
        if row.treatment not in {"PROPORTIONAL", "NONRETURNABLE"}:
            raise ValidationFailedError("return treatment requires a separately supported profile")
        if money(value, precision, rounding_mode) != row.amount:
            raise ValidationFailedError("original component differs from its retained precision")
    consumed = {key: Fraction() for key in source}
    consumed_basis = Fraction()
    for prior in previous:
        part = exact(prior.basis)
        if (
            part <= 0
            or len(prior.amounts) != len(source)
            or set(dict(prior.amounts)) != set(source)
        ):
            raise ValidationFailedError("original return claim history is incomplete")
        consumed_basis += part
        for key, amount in prior.amounts:
            original, value = exact(source[key].amount), exact(amount)
            if money(value, precision, rounding_mode) != amount:
                raise ValidationFailedError("prior return differs from its retained precision")
            if (
                original < 0 < value
                or original > 0 > value
                or (original == 0 and value != 0)
                or (source[key].treatment == "NONRETURNABLE" and value != 0)
            ):
                raise ValidationFailedError("return claim has an incompatible original component")
            consumed[key] += value
            if abs(consumed[key]) > abs(original):
                raise ValidationFailedError("prior returns exceed original component entitlement")
    if consumed_basis + requested > basis:
        raise ValidationFailedError("return exceeds the original unclaimed basis")
    final = consumed_basis + requested == basis
    result = []
    for key in sorted(source):
        row = source[key]
        original_amount = exact(row.amount)
        returned_amount = (
            Decimal("0.0000")
            if row.treatment == "NONRETURNABLE"
            else money(original_amount - consumed[key], precision, rounding_mode)
            if final
            else money(original_amount * requested / basis, precision, rounding_mode)
        )
        if abs(exact(returned_amount) + consumed[key]) > abs(original_amount):
            raise ValidationFailedError(
                "rounded return exceeds the remaining component entitlement"
            )
        result.append((key, returned_amount))
    return ReturnClaim(money(requested, 4), tuple(result))

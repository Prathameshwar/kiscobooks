"""Exact cash-tender evidence; denominations cannot create another payment."""

from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class Denomination:
    face_value: Decimal
    count: int


def validate_cash_tender(
    tender_amount: Decimal,
    rows: tuple[Denomination, ...],
    *,
    allowed_faces: frozenset[Decimal],
) -> Decimal:
    """Return the exact observed total only when it equals one cash tender."""
    if not rows or len(rows) > 100:
        raise ValidationFailedError("cash denomination rows are required and bounded")
    try:
        expected = exact_decimal(tender_amount)
        faces = frozenset(exact_decimal(face) for face in allowed_faces)
    except MoneyError as exc:
        raise ValidationFailedError("cash tender or denomination exceeds exact storage") from exc
    if expected <= 0 or not faces or any(face <= 0 for face in faces):
        raise ValidationFailedError("cash tender and allowed denominations must be positive")
    if len({row.face_value for row in rows}) != len(rows):
        raise ValidationFailedError("cash denomination faces must be distinct")
    total = Decimal(0)
    for row in rows:
        if row.face_value not in faces:
            raise ValidationFailedError("cash denomination is not allowed for this tender")
        if type(row.count) is not int or not 0 <= row.count <= 1_000_000:
            raise ValidationFailedError("cash denomination count is invalid")
        total += row.face_value * row.count
    try:
        observed = exact_decimal(total)
    except MoneyError as exc:
        raise ValidationFailedError("cash denomination total exceeds exact storage") from exc
    if observed != expected:
        raise ValidationFailedError("cash denominations do not equal the cash tender")
    return observed

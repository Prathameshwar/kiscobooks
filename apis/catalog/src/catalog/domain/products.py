"""Draft goods/service and unit applicability, independent of storage and HTTP."""

from decimal import Decimal

from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError

from catalog.domain.units import QuantityRule


def validate_structure(
    *,
    kind: str,
    type_kind: str,
    dimension: str,
    allowed_dimensions: tuple[str, ...],
    quantity: QuantityRule,
    minimum_sale: Decimal | None,
) -> None:
    if kind not in {"GOODS", "SERVICE"} or type_kind not in {kind, "BOTH"}:
        raise ValidationFailedError("product kind is incompatible with its type revision")
    if dimension not in allowed_dimensions:
        raise ValidationFailedError("base unit dimension is not permitted by the product type")
    if minimum_sale is not None:
        if minimum_sale <= 0:
            raise ValidationFailedError("minimum sale quantity must be positive")
        try:
            quantity.validate(minimum_sale)
        except MoneyError as exc:
            raise ValidationFailedError("minimum sale quantity does not fit the base unit") from exc

"""Native reusable-profile rules; definition authoring never executes stock or claims."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal


def strict_flags(*values: bool) -> None:
    if any(type(value) is not bool for value in values):
        raise ValidationFailedError("profile flags must be booleans")


def bounded_days(value: int | None, *, required: bool = False, allow_zero: bool = False) -> None:
    if value is None:
        if required:
            raise ValidationFailedError("profile duration is required")
        return
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= 36500:
        raise ValidationFailedError("profile duration must be one to 36500 days")


@dataclass(frozen=True, slots=True)
class IdentifierRequirement:
    identifier_type: str
    namespace_rule: str
    min_count: int
    max_count: int
    requires_slot: bool

    def __post_init__(self) -> None:
        strict_flags(self.requires_slot)
        if self.identifier_type not in {"SERIAL", "IMEI"}:
            raise ValidationFailedError("unsupported identifier requirement")
        if self.namespace_rule not in {"COMPANY", "MANUFACTURER_SKU"}:
            raise ValidationFailedError("unsupported identifier namespace")
        if (
            type(self.min_count) is not int
            or type(self.max_count) is not int
            or not 0 <= self.min_count <= self.max_count <= 8
            or self.max_count < 1
        ):
            raise ValidationFailedError("identifier counts must be coherent and bounded")
        if self.max_count > 1 and not self.requires_slot:
            raise ValidationFailedError("multiple identifiers require explicit slots")
        if self.identifier_type == "IMEI" and self.namespace_rule != "COMPANY":
            raise ValidationFailedError("IMEI identity uses company scope")


def validate_identifier_requirements(requirements: tuple[IdentifierRequirement, ...]) -> None:
    if not 1 <= len(requirements) <= 2 or len({row.identifier_type for row in requirements}) != len(
        requirements
    ):
        raise ValidationFailedError("identifier requirements must have distinct supported types")


@dataclass(frozen=True, slots=True)
class InventoryRules:
    lot_tracking: bool
    serial_tracking: bool
    expiry_required: bool
    manufacture_date_required: bool
    shelf_life_days: int | None
    minimum_remaining_life_days: int | None
    issue_strategy: str
    valuation_method: str
    has_identifier_profile: bool
    negative_stock_policy: str = "BLOCK"

    def __post_init__(self) -> None:
        strict_flags(
            self.lot_tracking,
            self.serial_tracking,
            self.expiry_required,
            self.manufacture_date_required,
            self.has_identifier_profile,
        )
        bounded_days(self.shelf_life_days)
        bounded_days(self.minimum_remaining_life_days, allow_zero=True)
        if self.negative_stock_policy not in {"BLOCK", "WARN", "ALLOW"}:
            raise ValidationFailedError("unsupported negative stock policy")
        if self.issue_strategy not in {"FIFO", "FEFO"} or self.valuation_method not in {
            "FIFO",
            "MOVING_AVERAGE",
            "SPECIFIC",
        }:
            raise ValidationFailedError("unsupported inventory issue or valuation requirement")
        if (
            self.expiry_required
            or self.manufacture_date_required
            or self.shelf_life_days is not None
            or self.minimum_remaining_life_days is not None
        ) and not self.lot_tracking:
            raise ValidationFailedError("inventory date requirements need batch tracking")
        if (
            self.issue_strategy == "FEFO" or self.minimum_remaining_life_days is not None
        ) and not self.expiry_required:
            raise ValidationFailedError("expiry-based issue requirements need mandatory expiry")
        if (
            self.shelf_life_days is not None
            and self.minimum_remaining_life_days is not None
            and self.minimum_remaining_life_days > self.shelf_life_days
        ):
            raise ValidationFailedError("remaining life exceeds declared shelf life")
        if (
            self.has_identifier_profile or self.valuation_method == "SPECIFIC"
        ) and not self.serial_tracking:
            raise ValidationFailedError(
                "identifier and specific-cost requirements need serialized stock"
            )


@dataclass(frozen=True, slots=True)
class WarrantyRules:
    duration: int
    duration_unit: str
    start_trigger: str

    def __post_init__(self) -> None:
        maximum = {"DAYS": 36500, "MONTHS": 1200, "YEARS": 100}.get(self.duration_unit)
        if maximum is None or type(self.duration) is not int or not 1 <= self.duration <= maximum:
            raise ValidationFailedError(
                "warranty duration must use a supported bounded calendar unit"
            )
        if self.start_trigger not in {"SALE", "DELIVERY", "INSTALLATION"}:
            raise ValidationFailedError("unsupported warranty start trigger")


@dataclass(frozen=True, slots=True)
class HandlingRules:
    temperature_min: Decimal | None
    temperature_max: Decimal | None
    temperature_unit: str | None
    fragile: bool
    keep_dry: bool
    keep_upright: bool

    def __post_init__(self) -> None:
        strict_flags(self.fragile, self.keep_dry, self.keep_upright)
        for name in ("temperature_min", "temperature_max"):
            raw = getattr(self, name)
            if raw is not None:
                try:
                    parsed = exact_decimal(raw)
                except ValueError as exc:
                    raise ValidationFailedError(
                        "handling bounds require exact decimal values"
                    ) from exc
                if parsed < Decimal("-273.15"):
                    raise ValidationFailedError(
                        "Celsius storage bounds cannot be below absolute zero"
                    )
                object.__setattr__(self, name, parsed)
        measured = self.temperature_min is not None or self.temperature_max is not None
        if (measured and self.temperature_unit != "CELSIUS") or (
            not measured and self.temperature_unit is not None
        ):
            raise ValidationFailedError("temperature bounds require their explicit supported unit")
        if (
            self.temperature_min is not None
            and self.temperature_max is not None
            and self.temperature_min > self.temperature_max
        ):
            raise ValidationFailedError("storage temperature minimum exceeds maximum")


RETURN_CONDITION_CODES = frozenset(
    {"ORIGINAL_PACKAGING", "PROOF_OF_PURCHASE", "COMPLETE_ACCESSORIES", "UNUSED", "UNDAMAGED"}
)


@dataclass(frozen=True, slots=True)
class ReturnRules:
    returns_allowed: bool
    window_days: int | None
    condition_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        strict_flags(self.returns_allowed)
        if not self.returns_allowed:
            if self.window_days is not None or self.condition_codes:
                raise ValidationFailedError("disabled returns cannot carry a window or conditions")
            return
        bounded_days(self.window_days, required=True, allow_zero=True)
        if (
            len(self.condition_codes) != len(set(self.condition_codes))
            or not set(self.condition_codes) <= RETURN_CONDITION_CODES
        ):
            raise ValidationFailedError("return conditions must be distinct supported codes")

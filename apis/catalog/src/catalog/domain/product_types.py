"""Closed product-type requirements; no custom fields or external execution rules."""

from dataclasses import dataclass

from billing_platform.errors import ValidationFailedError

from catalog.domain.profiles import InventoryRules


@dataclass(frozen=True, slots=True)
class TypeRequirements:
    kind: str
    inventory_modes: frozenset[str]
    tracking_modes: frozenset[str]
    unit_dimensions: frozenset[str]
    allow_variants: bool = True
    require_brand: bool = False
    require_manufacturer: bool = False
    require_expiry: bool = False

    def validate_profile_defaults(
        self, *, inventory: InventoryRules | None, has_handling: bool
    ) -> None:
        if self.kind != "GOODS" and (inventory is not None or has_handling):
            raise ValidationFailedError("physical profile defaults need a goods-only type")
        if inventory is None:
            return
        tracking = (
            "BATCH_SERIAL"
            if inventory.lot_tracking and inventory.serial_tracking
            else "BATCH"
            if inventory.lot_tracking
            else "SERIAL"
            if inventory.serial_tracking
            else "NONE"
        )
        if "STOCK" not in self.inventory_modes or tracking not in self.tracking_modes:
            raise ValidationFailedError("inventory default is outside the type's allowed modes")
        if self.require_expiry and not inventory.expiry_required:
            raise ValidationFailedError(
                "inventory default must require the type's mandatory expiry"
            )

    def __post_init__(self) -> None:
        valid = (
            self.kind in {"GOODS", "SERVICE", "BOTH"}
            and bool(self.inventory_modes)
            and self.inventory_modes <= {"NON_STOCK", "STOCK"}
            and bool(self.tracking_modes)
            and self.tracking_modes <= {"NONE", "BATCH", "SERIAL", "BATCH_SERIAL"}
            and bool(self.unit_dimensions)
            and self.unit_dimensions <= {"COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"}
            and all(
                type(value) is bool
                for value in (
                    self.allow_variants,
                    self.require_brand,
                    self.require_manufacturer,
                    self.require_expiry,
                )
            )
        )
        if not valid:
            raise ValidationFailedError("unsupported product-type requirement")
        if self.kind == "SERVICE" and (
            self.inventory_modes != {"NON_STOCK"} or self.tracking_modes != {"NONE"}
        ):
            raise ValidationFailedError("services cannot require physical inventory or tracking")
        if self.kind != "GOODS" and (self.require_manufacturer or self.require_expiry):
            raise ValidationFailedError("physical required fields need a goods-only type")
        if self.kind == "BOTH" and (
            "NON_STOCK" not in self.inventory_modes or "NONE" not in self.tracking_modes
        ):
            raise ValidationFailedError("a mixed type must admit a service configuration")
        if "NON_STOCK" in self.inventory_modes and "NONE" not in self.tracking_modes:
            raise ValidationFailedError("non-stock items need an untracked configuration")
        if self.inventory_modes == {"NON_STOCK"} and self.tracking_modes != {"NONE"}:
            raise ValidationFailedError("physical tracking needs stock capability")
        serial = {"SERIAL", "BATCH_SERIAL"}
        if self.tracking_modes & serial and "COUNT" not in self.unit_dimensions:
            raise ValidationFailedError("serial tracking requires a count-unit option")
        if self.tracking_modes <= serial and self.unit_dimensions != {"COUNT"}:
            raise ValidationFailedError("exclusively serialized types require count units")
        if self.require_expiry and (
            self.inventory_modes != {"STOCK"}
            or not self.tracking_modes <= {"BATCH", "BATCH_SERIAL"}
        ):
            raise ValidationFailedError("expiry requires stock with batch tracking")

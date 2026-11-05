"""Definition-capable external document entities retain their owner contracts."""

from typing import Any

from billing_platform.custom_fields import CustomDefinition
from billing_platform.fields import NativeField

from identity.domain import catalog_fields, voucher_fields


def owner(entity: str) -> Any:
    return voucher_fields if entity.startswith("vouchers.") else catalog_fields


def contracts() -> dict[str, Any]:
    return catalog_fields.contracts() | voucher_fields.contracts()


def contract(entity: str) -> dict[str, Any]:
    return (
        voucher_fields.contract(entity)
        if entity.startswith("vouchers.")
        else catalog_fields.contract(entity)
    )


def native_field(entity: str, key: str) -> NativeField:
    return (
        voucher_fields.native_field(entity, key)
        if entity.startswith("vouchers.")
        else catalog_fields.native_field(entity, key)
    )


def validate_options(entity: str, definitions: tuple[CustomDefinition, ...]) -> None:
    owner(entity).validate_options(entity, definitions)

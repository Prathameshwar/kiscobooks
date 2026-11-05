"""Voucher field contract; no dependency on Vouchers ORM or executable policy."""

from typing import Any

from billing_platform.errors import ValidationFailedError
from billing_platform.fields import NativeField

HEADER = (
    "type_revision_id",
    "class_id",
    "issue_number",
    "document_date",
    "posting_date",
    "stock_date",
    "statutory_date",
    "credit_terms_date",
    "currency",
    "mode",
    "narration",
    "financial",
    "stock",
    "invoice",
    "fulfillment_terms",
    "lines",
    "parties",
    "references",
    "attachments",
    "links",
    "assignments",
    "counter",
    "custom_fields",
)
ITEM = (
    "opening",
    "warehouse_id",
    "bin_id",
    "lot_id",
    "unit_ids",
    "received_value",
    "zero_value_reason",
    "destination_warehouse_id",
    "destination_bin_id",
    "source_movement_id",
    "opening_journal_line_id",
    "item_id",
    "item_version",
    "unit_id",
    "actual_quantity",
    "billed_quantity",
    "planned_quantity",
    "custom_fields",
)
CONFIG = (
    "derived_from_revision_id",
    "type_revision_id",
    "code",
    "name",
    "kind",
    "profile",
    "policy",
    "family",
    "prefix",
    "padding",
    "title",
    "fields",
)


def contracts() -> dict[str, dict[str, Any]]:
    return {
        entity: {
            "fields": {key: {} for key in keys},
            "forms": {key: {"required": False, "hideable": True} for key in keys},
            "option_sources": {
                key: {"parent_source": None} for key in ("items", "parties", "voucher_types")
            },
            "permissions": {
                "read": "vouchers.read",
                "write": "vouchers.edit"
                if entity != "vouchers.configuration"
                else "vouchers.configuration.manage",
            },
        }
        for entity, keys in (
            ("vouchers.voucher", HEADER),
            ("vouchers.voucher_item", ITEM),
            ("vouchers.configuration", CONFIG),
        )
    }


def contract(entity: str) -> dict[str, Any]:
    result = contracts().get(entity)
    if result is None:
        raise ValidationFailedError("voucher field entity is not supported")
    return result


def native_field(entity: str, key: str) -> NativeField:
    if key not in contract(entity)["fields"]:
        raise ValidationFailedError("voucher field is not registered")
    return NativeField()


def validate_options(entity: str, definitions: Any) -> None:
    sources = contract(entity)["option_sources"]
    for definition in definitions:
        if definition.option_source_key and (
            definition.option_source_key not in sources or definition.depends_on_key
        ):
            raise ValidationFailedError("unsupported voucher option source")

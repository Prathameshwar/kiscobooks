"""Pure item-direction and physical-applicability checks for accepted vouchers."""

from billing_platform.errors import ConflictError

from vouchers.schemas.sources import ItemTransactionFacts

SALE_KINDS = frozenset({"SALES_ORDER", "SALES", "DELIVERY_NOTE"})
PURCHASE_KINDS = frozenset({"PURCHASE_ORDER", "PURCHASE", "RECEIPT_NOTE"})
PHYSICAL_KINDS = frozenset(
    {
        "DELIVERY_NOTE",
        "RECEIPT_NOTE",
        "REJECTIONS_IN",
        "REJECTIONS_OUT",
        "PHYSICAL_STOCK",
        "MATERIAL_IN",
        "MATERIAL_OUT",
    }
)


def assert_item_use(
    facts: ItemTransactionFacts,
    *,
    kind: str,
    profile: str,
    supply_kind: str | None = None,
) -> None:
    if supply_kind is not None and supply_kind != facts.kind:
        raise ConflictError("invoice supply kind differs from item kind")
    if (kind in SALE_KINDS and not facts.sellable) or (
        kind in PURCHASE_KINDS and not facts.purchasable
    ):
        raise ConflictError("item is not enabled for this transaction direction")
    if kind in PHYSICAL_KINDS or (kind == "STOCK_JOURNAL" and profile != "REQUISITION"):
        if facts.inventory_mode != "STOCK" or facts.kind != "GOODS":
            raise ConflictError("physical voucher requires stock-tracked goods")

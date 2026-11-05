"""Goods, service and non-stock item use stays independent from amount calculation."""

import pytest
from billing_platform.errors import ConflictError
from pydantic import ValidationError

from vouchers.domain.item_eligibility import assert_item_use
from vouchers.schemas.sources import ItemTransactionFacts


@pytest.mark.parametrize(
    ("kind", "sellable", "purchasable", "blocked"),
    [
        ("SALES_ORDER", False, True, True),
        ("PURCHASE_ORDER", False, True, False),
        ("SALES", True, False, False),
        ("PURCHASE", True, False, True),
    ],
)
def test_directions_are_independent(kind, sellable, purchasable, blocked):
    facts = ItemTransactionFacts(
        kind="GOODS", item_version=1, inventory_mode="NON_STOCK",
        sellable=sellable, purchasable=purchasable,
    )
    if blocked:
        with pytest.raises(ConflictError, match="not enabled"):
            assert_item_use(facts, kind=kind, profile="STANDARD")
    else:
        assert_item_use(facts, kind=kind, profile="STANDARD")


def test_service_invoice_kind_and_physical_stock_are_guarded():
    service = ItemTransactionFacts(
        kind="SERVICE", item_version=1, inventory_mode="NON_STOCK",
        sellable=True, purchasable=True,
    )
    assert_item_use(service, kind="SALES", profile="STANDARD", supply_kind="SERVICE")
    with pytest.raises(ConflictError, match="differs from item kind"):
        assert_item_use(service, kind="SALES", profile="STANDARD", supply_kind="GOODS")
    with pytest.raises(ConflictError, match="stock-tracked goods"):
        assert_item_use(service, kind="DELIVERY_NOTE", profile="DELIVERY_CHALLAN")
    with pytest.raises(ConflictError, match="stock-tracked goods"):
        assert_item_use(service, kind="STOCK_JOURNAL", profile="TRANSFER")
    assert_item_use(service, kind="STOCK_JOURNAL", profile="REQUISITION")


def test_source_linked_return_is_not_blocked_by_a_later_direction_stop():
    stopped = ItemTransactionFacts(
        kind="GOODS", item_version=3, inventory_mode="NON_STOCK",
        sellable=False, purchasable=False,
    )
    assert_item_use(stopped, kind="CREDIT_NOTE", profile="STANDARD", supply_kind="GOODS")
    assert_item_use(stopped, kind="DEBIT_NOTE", profile="STANDARD", supply_kind="GOODS")


def test_owner_policy_rejects_coerced_direction_flags():
    with pytest.raises(ValidationError):
        ItemTransactionFacts.model_validate({
            "kind": "GOODS", "item_version": 1, "inventory_mode": "NON_STOCK",
            "sellable": "false", "purchasable": True,
        })

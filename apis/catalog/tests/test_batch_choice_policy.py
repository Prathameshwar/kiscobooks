"""Mandatory physical rules cannot be weakened by an optional product choice."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.tasks import product_stock_choice


def template(**changes):
    return SimpleNamespace(
        **{
            "identifier_profile_id": None,
            "lot_tracking": True,
            "serial_tracking": False,
            "expiry_required": False,
            "manufacture_date_required": False,
            "shelf_life_days": None,
            "minimum_remaining_life_days": None,
            "issue_strategy": "FIFO",
            "valuation_method": "FIFO",
            "negative_stock_policy": "BLOCK",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "rules",
    [
        {"expiry_required": True},
        {"manufacture_date_required": True},
        {"shelf_life_days": 30},
        {"expiry_required": True, "minimum_remaining_life_days": 0},
        {"expiry_required": True, "issue_strategy": "FEFO"},
    ],
)
async def test_template_date_policy_requires_batches(rules):
    inventory = template(**rules)
    access = SimpleNamespace(
        reference=AsyncMock(side_effect=[
            inventory,
            SimpleNamespace(tracking_modes=["NONE", "BATCH"], require_expiry=False),
        ]),
        context=AsyncMock(return_value=SimpleNamespace(
            features={"inventory", "batch_tracking", "expiry_tracking"}
        )),
    )
    config = SimpleNamespace(profiles=SimpleNamespace(inventory_template_revision_id=uuid7()))
    options = await product_stock_choice.available(access, config, uuid7(), "GOODS")
    assert options["available"] and options["required"]


@pytest.mark.parametrize(
    "rules",
    [
        {"expiry_required": True},
        {"manufacture_date_required": True},
        {"shelf_life_days": 30},
        {"minimum_remaining_life_days": 0},
        {"issue_strategy": "FEFO"},
        {"serial_tracking": True},
    ],
)
def test_existing_batch_off_choice_cannot_rewrite_mandatory_policy(rules):
    with pytest.raises(ValidationFailedError, match="mandatory"):
        product_stock_choice.profile_values(template(**rules), SimpleNamespace(batch_enabled=False))


def test_optional_batch_off_remains_untracked():
    values = product_stock_choice.profile_values(template(), SimpleNamespace(batch_enabled=False))
    assert not values["lot_tracking"]
    assert not values["expiry_required"]
    assert values["issue_strategy"] == "FIFO"


def test_batch_on_preserves_policy():
    inventory = template(expiry_required=True, issue_strategy="FEFO", minimum_remaining_life_days=5)
    values = product_stock_choice.profile_values(inventory, SimpleNamespace(batch_enabled=True))
    assert values["lot_tracking"] and values["expiry_required"]
    assert values["issue_strategy"] == "FEFO" and values["minimum_remaining_life_days"] == 5

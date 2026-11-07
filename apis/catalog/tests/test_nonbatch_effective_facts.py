"""Published effective facts must honor the SKU's saved optional batch choice."""

import pytest
from billing_platform.ids import uuid7

from catalog.tasks.pricing_commands import business_date
from tests.test_simple_batch_creation import batch_starter
from tests.test_simple_product_creation import finish

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_effective_inventory_uses_saved_nonbatch_choice(client, factory, tenant_a):
    root, auth, unit = await batch_starter(factory, tenant_a)
    today = business_date("Asia/Kolkata").isoformat()
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth
        | {
            "Idempotency-Key": str(uuid7()),
        },
        json={
            "name": "Nonbatch effective facts",
            "base_unit_id": unit,
            "batch_enabled": False,
            "purchase_price": "10",
            "sale_price": "20",
        },
    )
    assert created.status_code == 201, created.text
    completed = await finish(client, root, auth, created.json()["id"])
    facts = await client.get(
        root + "/items/" + completed["item_id"] + "/effective-facts?as_of=" + today, headers=auth
    )
    assert facts.status_code == 200, facts.text
    inventory = facts.json()["inventory"]
    assert inventory["lot_tracking"] is False
    assert inventory["expiry_required"] is False
    assert inventory["manufacture_date_required"] is False
    assert inventory["shelf_life_days"] is None
    assert inventory["minimum_remaining_life_days"] is None
    assert inventory["issue_strategy"] == "FIFO"

"""Immediate item evidence preserves the opening coordinator's retry boundary."""

from billing_platform.ids import uuid7

from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks.simple_creation_steps import after_command, next_command


async def test_opening_hands_off_exact_source_before_creating_voucher():
    tenant, company, creation, item, unit = (uuid7() for _ in range(5))
    body = SimpleCreationInput(
        name="Tea", base_unit_id=unit, opening_quantity="2", purchase_price="10"
    )

    class Owners:
        source_delivery = object()

        async def item_source_bundle(self, given_tenant, given_company, given_item, given_creation):
            assert (given_tenant, given_company, given_item, given_creation) == (
                tenant,
                company,
                item,
                creation,
            )
            return {"message_id": str(creation), "masters": []}

    progress = {"source_delivery": True}
    next_step, _ = after_command(
        "OPENING", body, progress, {"body": {"lines": []}}, {"id": str(uuid7())}
    )
    assert next_step == "SOURCE"
    source = await next_command(
        Owners(), company, creation, next_step, body, progress, item, tenant
    )
    assert source == {
        "service": "source",
        "path": "/internal/v1/sources",
        "body": {"message_id": str(creation), "masters": []},
    }
    next_step, _ = after_command("SOURCE", body, progress, source, {"applied": True})
    assert next_step == "VOUCHER"
    assert progress["source_delivered"] is True


def test_existing_snapshot_path_remains_when_push_is_unconfigured():
    body = SimpleCreationInput(
        name="Tea", base_unit_id=uuid7(), opening_quantity="2", purchase_price="10"
    )
    progress = {"source_delivery": False}
    step, _ = after_command("OPENING", body, progress, {"body": {}}, {"id": str(uuid7())})
    assert step == "VOUCHER"

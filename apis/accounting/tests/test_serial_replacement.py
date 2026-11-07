"""Unused identity replacement keeps the old registry and audits both records."""

import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from accounting.models.stock_tracking import StockTrackingEvent, StockUnitIdentifier
from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import prepare
from tests.test_stock_tracking import (  # noqa: F401
    BASE,
    FEATURES,
    ITEM,
    KEYS,
    PROFILE,
    auth,
    create_batch,
    serial,
    source,
)


async def original(client):
    await prepare(client)
    lot = await create_batch(client)
    response = await client.post(BASE + "/serials", json=serial(lot["id"]), headers=auth())
    assert response.status_code == 201, response.text
    return lot, response.json()


def replacement(lot, old, **changes):
    return serial(
        lot["id"],
        "SERIAL-CORRECTED",
        replaces_unit_id=old["id"],
        expected_replaced_version=old["row_version"],
        **changes,
    )


async def test_replacement_is_atomic_audited_and_replayable(client, app):
    lot, old = await original(client)
    body, key = replacement(lot, old), auth()
    response = await client.post(BASE + "/serials", json=body, headers=key)
    assert response.status_code == 201, response.text
    new = response.json()
    retired = (await client.get(BASE + "/serials/" + old["id"], headers=auth())).json()
    assert retired["status"] == "RETIRED"
    assert retired["identifiers"] == old["identifiers"]
    assert retired["row_version"] == old["row_version"] + 1
    assert new["id"] != old["id"] and new["operational_ready"] is False
    replay = await client.post(BASE + "/serials", json=body, headers=key)
    assert replay.status_code == 201 and replay.json() == new
    assert replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = (
                await db.scalars(
                    select(StockTrackingEvent).where(
                        StockTrackingEvent.target_id.in_(
                            [uuid.UUID(old["id"]), uuid.UUID(new["id"])]
                        )
                    )
                )
            ).all()
            linked = [event for event in events if "id" in event.evidence]
            assert len(linked) == 2
            assert all(
                event.evidence["id"] == {"from": old["id"], "to": new["id"]} for event in linked
            )
            assert await db.scalar(select(func.count(StockUnitIdentifier.id))) == 2
    # Superseded identities stay reserved and cannot become receipt candidates again.
    reused = await client.post(BASE + "/serials", json=serial(lot["id"]), headers=auth())
    assert reused.status_code == 409
    reactivated = await client.post(
        BASE + "/serials/" + old["id"] + "/reactivate",
        json={"expected_version": retired["row_version"], "reason": "Try reused identity"},
        headers=auth(),
    )
    assert reactivated.status_code == 409


async def test_conflicting_replacement_leaves_original_active(client):
    lot, old = await original(client)
    body = replacement(lot, old)
    body["identifiers"] = old["identifiers"]
    response = await client.post(BASE + "/serials", json=body, headers=auth())
    assert response.status_code == 409, response.text
    unchanged = (await client.get(BASE + "/serials/" + old["id"], headers=auth())).json()
    assert unchanged["status"] == "ACTIVE" and unchanged["row_version"] == old["row_version"]


@pytest.mark.parametrize("case", ["stale", "held", "wrong_item", "missing_pair"])
async def test_replacement_rejects_ineligible_original(client, case):
    lot, old = await original(client)
    body = replacement(lot, old)
    if case == "stale":
        body["expected_replaced_version"] += 1
    elif case == "held":
        result = await client.post(
            BASE + "/serials/" + old["id"] + "/hold",
            json={"expected_version": old["row_version"], "reason": "Hold this unit"},
            headers=auth(),
        )
        assert result.status_code == 200
        body["expected_replaced_version"] = result.json()["row_version"]
    elif case == "wrong_item":
        body["item_id"] = str(uuid.uuid4())
    else:
        del body["expected_replaced_version"]
    response = await client.post(BASE + "/serials", json=body, headers=auth())
    assert response.status_code in {409, 422}, response.text


async def test_replacement_checks_original_company_and_write_policy(client):
    lot, old = await original(client)
    body = replacement(lot, old)
    denied = headers(permissions={"accounting.serial.read"}, features=FEATURES)
    assert (await client.post(BASE + "/serials", json=body, headers=denied)).status_code == 403
    other_company = uuid.uuid4()
    other = await client.post(
        BASE.replace(str(COMPANY), str(other_company)) + "/serials",
        json=body,
        headers=auth(company=other_company),
    )
    assert other.status_code == 403
    body["replaces_unit_id"] = str(uuid.uuid4())
    assert (await client.post(BASE + "/serials", json=body, headers=auth())).status_code in {
        403,
        404,
    }


async def test_received_serial_cannot_be_replaced(client, app):
    from tests.test_stock_ledger import item, ledger, line, warehouse

    lot, old = await original(client)
    product = item(tracking=True).model_copy(
        update={"item_id": ITEM, "profile_revision_id": PROFILE}
    )
    location = warehouse()
    eligible_headers = headers(permissions=KEYS | {"accounting.stock.read"}, features=FEATURES)
    selection = BASE + "/serials?id=" + old["id"] + "&receipt_eligible=true&limit=1"
    available = await client.get(selection, headers=eligible_headers)
    assert available.status_code == 200, available.text
    assert [unit["id"] for unit in available.json()["items"]] == [old["id"]]
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(
                line(
                    product,
                    location,
                    1,
                    lot_id=uuid.UUID(lot["id"]),
                    unit_ids=(uuid.UUID(old["id"]),),
                ),
                product,
                location,
                value=Decimal("10"),
            )
    response = await client.post(BASE + "/serials", json=replacement(lot, old), headers=auth())
    assert response.status_code == 409, response.text
    unchanged = (await client.get(BASE + "/serials/" + old["id"], headers=auth())).json()
    assert unchanged["status"] == "ACTIVE"
    used = await client.get(selection, headers=eligible_headers)
    assert used.status_code == 200 and used.json()["items"] == []


async def test_replacement_replay_rechecks_control_field_denies(client):
    lot, old = await original(client)
    body, key = replacement(lot, old), auth()
    response = await client.post(BASE + "/serials", json=body, headers=key)
    assert response.status_code == 201
    policy = [
        {
            "entity_type": "accounting.stock_unit",
            "field_key": "replaces_unit_id",
            "access": "write",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
            "condition": None,
        }
    ]
    replay = await client.post(
        BASE + "/serials", json=body, headers=auth(key=key["Idempotency-Key"], policies=policy)
    )
    assert replay.status_code == 403, replay.text

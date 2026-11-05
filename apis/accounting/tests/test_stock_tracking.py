"""Prepared tracking identities: native commands, scope, field policies and exact namespaces."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.api import stock_tracking as api
from accounting.models.stock_tracking import StockTrackingEvent, StockUnit
from accounting.schemas.stock_tracking import TrackingSource
from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import prepare

BASE = f"/v1/companies/{COMPANY}/stock-tracking"
ITEM = uuid7()
PROFILE = uuid7()
KEYS = frozenset(
    f"accounting.{kind}.{action}"
    for kind in ("batch", "serial")
    for action in ("read", "manage", "hold")
)
FEATURES = {"inventory", "batch_tracking", "serial_tracking", "expiry_tracking"}


async def test_stock_entry_context_requires_stock_read_without_serial_directory_access(
    client, monkeypatch
):
    calls = []

    async def verified(request, current, item, **kwargs):
        calls.append(kwargs)
        return facts(current.context.company_id, item)

    monkeypatch.setattr(api, "source", verified)
    path = BASE + "/context/" + str(ITEM) + "?resource=stock"
    assert (await client.get(path, headers=auth())).status_code == 403
    result = await client.get(
        path, headers=headers(permissions={"accounting.stock.read"}, features={"inventory"})
    )
    assert result.status_code == 200, result.text
    assert calls == [{"include_identifiers": False}]


async def test_used_batch_dates_and_on_hand_retirement_are_guarded(client, app, monkeypatch):
    from tests.test_stock_ledger import item, ledger, line, warehouse

    await prepare(client)
    async def verified(request, current, identity, **kwargs):
        return facts(current.context.company_id, identity).model_copy(
            update={"serial_tracking": False, "requirements": []}
        )

    monkeypatch.setattr(api, "source", verified)
    created = await client.post(BASE + "/batches", json=batch(), headers=auth())
    assert created.status_code == 201, created.text
    row = created.json()
    product = item(tracking=True).model_copy(
        update={"item_id": ITEM, "profile_revision_id": PROFILE, "serial_tracking": False}
    )
    location = warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, lot_id=uuid.UUID(row["id"])),
                product,
                location,
                value=Decimal("10"),
            )
    corrected = await client.patch(
        BASE + "/batches/" + row["id"],
        json={
            "expected_version": row["row_version"],
            "expires_on": "2028-01-01",
            "reason": "Try changing an already used expiry",
        },
        headers=auth(),
    )
    assert corrected.status_code == 409, corrected.text
    assert "posted stock" in corrected.json()["error"]["message"]
    retired = await client.post(
        BASE + "/batches/" + row["id"] + "/retire",
        json={"expected_version": row["row_version"], "reason": "Try retiring goods still on hand"},
        headers=auth(),
    )
    assert retired.status_code == 409, retired.text
    assert "remaining stock" in retired.json()["error"]["message"]
    unchanged = await client.get(BASE + "/batches/" + row["id"], headers=auth())
    assert unchanged.json()["row_version"] == row["row_version"]
    assert unchanged.json()["status"] == "ACTIVE"


def auth(**kwargs: Any) -> dict[str, str]:
    return headers(permissions=KEYS, features=FEATURES, **kwargs)


def facts(company: uuid.UUID = COMPANY, item: uuid.UUID = ITEM, **changes: Any) -> TrackingSource:
    return TrackingSource(
        company_id=company,
        item_id=item,
        as_of=dt.date.today(),
        profile_revision_id=PROFILE,
        lot_tracking=True,
        serial_tracking=True,
        expiry_required=True,
        manufacture_date_required=True,
        requirements=[
            {
                "identifier_type": "SERIAL",
                "namespace_rule": "COMPANY",
                "min_count": 1,
                "max_count": 1,
                "requires_slot": False,
            }
        ],
        source_digest="a" * 64,
        **changes,
    )


@pytest.fixture(autouse=True)
def source(monkeypatch: pytest.MonkeyPatch):
    async def verified(request, current, item, **kwargs):
        return facts(current.context.company_id, item)

    monkeypatch.setattr(api, "source", verified)


def batch(**changes: Any) -> dict[str, Any]:
    return {
        "item_id": str(ITEM),
        "code": "LOT-001",
        "manufactured_on": "2026-01-01",
        "expires_on": "2027-01-01",
        "reason": "Prepare the physical batch identity",
        **changes,
    }


def serial(lot: str, value: str = "SERIAL-001", **changes: Any) -> dict[str, Any]:
    return {
        "item_id": str(ITEM),
        "lot_id": lot,
        "identifiers": [{"identifier_type": "SERIAL", "slot": 1, "value": value}],
        "reason": "Prepare one physical unit",
        **changes,
    }


async def create_batch(client: httpx.AsyncClient, **changes: Any) -> dict[str, Any]:
    response = await client.post(BASE + "/batches", json=batch(**changes), headers=auth())
    assert response.status_code == 201, response.text
    return response.json()


async def test_batch_serial_lifecycle_history_and_replay(client: httpx.AsyncClient) -> None:
    await prepare(client)
    h = auth()
    response = await client.post(BASE + "/batches", json=batch(), headers=h)
    assert response.status_code == 201, response.text
    lot = response.json()
    assert lot["status"] == "ACTIVE" and lot["operational_ready"] is False
    replay = await client.post(BASE + "/batches", json=batch(), headers=h)
    assert replay.status_code == 201 and replay.json() == lot, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    response = await client.post(BASE + "/serials", json=serial(lot["id"]), headers=auth())
    assert response.status_code == 201, response.text
    unit = response.json()
    assert unit["identifiers"][0]["value"] == "SERIAL-001"
    for resource, row in (("batches", lot), ("serials", unit)):
        for action in ("hold", "release", "retire", "reactivate"):
            response = await client.post(
                BASE + f"/{resource}/{row['id']}/{action}",
                json={
                    "expected_version": row["row_version"],
                    "reason": "Controlled tracking change",
                },
                headers=auth(),
            )
            assert response.status_code == 200, response.text
            row = response.json()
        history = await client.get(BASE + f"/{resource}/{row['id']}/history", headers=auth())
        assert history.status_code == 200, history.text
        assert len(history.json()["items"]) == 5
    listing = await client.get(BASE + "/serials?q=serial-0", headers=auth())
    assert listing.status_code == 200, listing.text
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["identifiers"] == unit["identifiers"]


async def test_duplicate_normalization_rollback_and_slot_rules(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    lot = await create_batch(client)
    assert (
        await client.post(BASE + "/batches", json=batch(code="lot-001"), headers=auth())
    ).status_code == 409
    response = await client.post(BASE + "/serials", json=serial(lot["id"]), headers=auth())
    assert response.status_code == 201, response.text
    duplicate = await client.post(
        BASE + "/serials",
        json=serial(lot["id"], "\uff53\uff45\uff52\uff49\uff41\uff4c-001"),
        headers=auth(),
    )
    assert duplicate.status_code == 409, duplicate.text
    invalid = serial(lot["id"])
    invalid["identifiers"].append({"identifier_type": "SERIAL", "slot": 1, "value": "OTHER"})
    assert (await client.post(BASE + "/serials", json=invalid, headers=auth())).status_code == 422
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockUnit.id))) == 1
            assert await db.scalar(select(func.count(StockTrackingEvent.id))) == 2


async def test_permissions_field_denies_and_replay_revocation(client: httpx.AsyncClient) -> None:
    await prepare(client)
    assert (await client.get(BASE + "/batches")).status_code == 401
    assert (
        await client.get(BASE + "/batches", headers=headers(permissions=frozenset()))
    ).status_code == 403
    denied = [
        {
            "entity_type": "accounting.stock_lot",
            "field_key": "code",
            "access": "write",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
            "condition": None,
        }
    ]
    assert (
        await client.post(BASE + "/batches", json=batch(), headers=auth(policies=denied))
    ).status_code == 403
    h = auth()
    lot_response = await client.post(BASE + "/batches", json=batch(), headers=h)
    assert lot_response.status_code == 201, lot_response.text
    denied_replay = await client.post(
        BASE + "/batches", json=batch(), headers=auth(key=h["Idempotency-Key"], policies=denied)
    )
    assert denied_replay.status_code == 403, denied_replay.text
    lot = lot_response.json()
    protected = [{**denied[0], "access": "read"}]
    detail = await client.get(BASE + "/batches/" + lot["id"], headers=auth(policies=protected))
    assert detail.status_code == 200 and "code" not in detail.json(), detail.text
    assert (
        await client.get(BASE + "/batches?q=lot", headers=auth(policies=protected))
    ).status_code == 403
    no_hold = KEYS - {"accounting.batch.hold"}
    response = await client.post(
        BASE + "/batches/" + lot["id"] + "/hold",
        json={"reason": "Do not issue", "expected_version": 1},
        headers=headers(permissions=no_hold, features=FEATURES),
    )
    assert response.status_code == 403, response.text
    optional_denied = [{**denied[0], "field_key": "source_party_id"}]
    signed_optional = auth(policies=optional_denied)
    optional = batch(code="NO-OPTIONAL-PARTY", source_party_id=None)
    created_optional = await client.post(BASE + "/batches", json=optional, headers=signed_optional)
    assert created_optional.status_code == 201, created_optional.text
    replay_optional = await client.post(BASE + "/batches", json=optional, headers=signed_optional)
    assert replay_optional.status_code == 201, replay_optional.text


async def test_validation_stale_versions_and_configuration(client: httpx.AsyncClient) -> None:
    await prepare(client)
    for change in (
        {"manufactured_on": None},
        {"expires_on": None},
        {"code": "\u0000BAD"},
        {"expires_on": "2025-01-01"},
        {"quantity": "10"},
    ):
        response = await client.post(BASE + "/batches", json=batch(**change), headers=auth())
        assert response.status_code == 422, response.text
    disabled = await client.post(BASE + "/batches", json=batch(), headers=headers(permissions=KEYS))
    assert disabled.status_code == 409, disabled.text
    lot = await create_batch(client)
    path = BASE + "/batches/" + lot["id"]
    corrected = await client.patch(
        path,
        json={
            "manufactured_on": "2026-02-01",
            "expires_on": "2027-02-01",
            "reason": "Correct supplier evidence",
            "expected_version": 1,
        },
        headers=auth(),
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["row_version"] == 2
    stale = await client.post(
        path + "/hold",
        json={"expected_version": 1, "reason": "Hold for inspection"},
        headers=auth(),
    )
    assert stale.status_code == 409, stale.text
    assert (await client.get(BASE + "/batches?unexpected=1", headers=auth())).status_code == 422
    assert (await client.get(BASE + "/batches?limit=1&limit=2", headers=auth())).status_code == 422


async def test_same_tenant_company_and_cross_tenant_isolation(client: httpx.AsyncClient) -> None:
    await prepare(client)
    lot = await create_batch(client)
    for tenant, company in ((TENANT, uuid7()), (uuid7(), uuid7())):
        other = f"/v1/companies/{company}/stock-tracking"
        signed = headers(tenant=tenant, company=company, permissions=KEYS, features=FEATURES)
        response = await client.get(other + "/batches/" + lot["id"], headers=signed)
        assert response.status_code == (403 if tenant == TENANT else 404), response.text
        response = await client.get(other + "/batches", headers=signed)
        assert response.status_code == 200 and not response.json()["items"], response.text


async def test_preparation_replays_when_catalog_is_offline(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await prepare(client)
    signed = auth()
    created = await client.post(BASE + "/batches", json=batch(), headers=signed)
    assert created.status_code == 201

    async def unavailable(*args, **kwargs):
        from accounting.tasks.stock_tracking_source import TrackingSourceUnavailableError

        raise TrackingSourceUnavailableError("Catalog temporarily unavailable")

    monkeypatch.setattr(api, "source", unavailable)
    replay = await client.post(BASE + "/batches", json=batch(), headers=signed)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == created.json()["id"]


async def test_partial_date_correction_and_protected_history(client: httpx.AsyncClient) -> None:
    await prepare(client)
    lot = await create_batch(client)
    path = BASE + "/batches/" + lot["id"]
    policies = [
        {
            "entity_type": "accounting.stock_lot",
            "field_key": "manufactured_on",
            "access": access,
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
            "condition": None,
        }
        for access in ("read", "write")
    ]
    corrected = await client.patch(
        path,
        json={
            "expires_on": "2027-03-01",
            "reason": "Correct dated supplier evidence",
            "expected_version": 1,
        },
        headers=auth(policies=policies),
    )
    assert corrected.status_code == 200, corrected.text
    full = await client.get(path, headers=auth())
    assert full.json()["manufactured_on"] == "2026-01-01"
    events = (await client.get(path + "/history", headers=auth())).json()["items"]
    event = next(value for value in events if value["action"] == "CORRECT")
    proof = await client.get(path + "/history/" + event["id"], headers=auth(policies=policies))
    assert proof.status_code == 200, proof.text
    assert proof.json()["changes"] == [
        {"field": "expires_on", "before": "2027-01-01", "after": "2027-03-01"}
    ]
    other = await create_batch(client, code="OTHER")
    assert (
        await client.get(
            BASE + "/batches/" + other["id"] + "/history/" + event["id"], headers=auth()
        )
    ).status_code == 404

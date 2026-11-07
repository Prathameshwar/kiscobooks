"""Expiry feature admission covers corrections and idempotent replays."""

import pytest

from accounting.api import stock_tracking as api
from tests.conftest import headers
from tests.test_masters import prepare
from tests.test_stock_tracking import BASE, KEYS, batch, facts


@pytest.fixture(autouse=True)
def optional_dates(monkeypatch):
    async def verified(request, current, item, **kwargs):
        return facts(current.context.company_id, item).model_copy(
            update={
                "serial_tracking": False,
                "requirements": [],
                "expiry_required": False,
                "manufacture_date_required": False,
            }
        )

    monkeypatch.setattr(api, "source", verified)


def auth(*, expiry=False, key=None):
    features = {"inventory", "batch_tracking"}
    if expiry:
        features.add("expiry_tracking")
    return headers(permissions=KEYS, features=features, key=key)


async def create(client, *, expiry=None):
    await prepare(client)
    result = await client.post(
        BASE + "/batches",
        headers=auth(expiry=expiry is not None),
        json=batch(manufactured_on=None, expires_on=expiry),
    )
    assert result.status_code == 201, result.text
    return result.json()


async def test_correction_requires_expiry_feature_and_leaves_row_unchanged(client):
    row = await create(client)
    path = BASE + "/batches/" + row["id"]
    result = await client.patch(
        path,
        headers=auth(),
        json={
            "expected_version": row["row_version"],
            "expires_on": "2028-01-01",
            "reason": "Correct the declared expiry",
        },
    )
    assert result.status_code == 422, result.text
    current = await client.get(path, headers=auth())
    assert current.json()["expires_on"] is None
    assert current.json()["row_version"] == row["row_version"]


async def test_optional_expiry_can_be_removed_with_feature_disabled(client):
    row = await create(client, expiry="2028-01-01")
    result = await client.patch(
        BASE + "/batches/" + row["id"],
        headers=auth(),
        json={
            "expected_version": row["row_version"],
            "expires_on": None,
            "reason": "Remove an optional mistaken declaration",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["expires_on"] is None


async def test_correction_replay_rechecks_expiry_feature(client):
    row = await create(client)
    path = BASE + "/batches/" + row["id"]
    body = {
        "expected_version": row["row_version"],
        "expires_on": "2028-01-01",
        "reason": "Correct the declared expiry",
    }
    enabled = auth(expiry=True)
    result = await client.patch(path, headers=enabled, json=body)
    assert result.status_code == 200, result.text
    replay = await client.patch(path, headers=auth(key=enabled["Idempotency-Key"]), json=body)
    assert replay.status_code == 422, replay.text


async def test_prepare_replay_rechecks_expiry_feature(client):
    await prepare(client)
    body = batch(manufactured_on=None, expires_on="2028-01-01")
    enabled = auth(expiry=True)
    result = await client.post(BASE + "/batches", headers=enabled, json=body)
    assert result.status_code == 201, result.text
    replay = await client.post(
        BASE + "/batches", headers=auth(key=enabled["Idempotency-Key"]), json=body
    )
    assert replay.status_code == 422, replay.text

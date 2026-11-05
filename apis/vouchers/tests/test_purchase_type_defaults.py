"""A plain Purchase type can open invoice entry without losing authored policy."""

import datetime as dt

import pytest
from conftest import headers
from test_foundation import create_type


async def test_plain_purchase_has_usable_invoice_defaults_and_stable_replay(client, prefix):
    body = {"code": "PURCHASE", "name": "Purchase", "kind": "PURCHASE"}
    auth = headers()
    created = await client.post(prefix + "/voucher-types", headers=auth, json=body)
    assert created.status_code == 201, created.text
    row = created.json()
    assert "ACCOUNT" in row["policy"]["invoice"]["allowed_supply_kinds"]
    assert row["policy"]["default_mode"] == "ACCOUNTS"
    metadata = await client.get(
        prefix + "/voucher-types/" + row["id"] + "/field-set",
        params={"date": dt.date.today().isoformat()},
        headers=headers(),
    )
    assert metadata.status_code == 200, metadata.text
    assert (
        "ACCOUNT" in metadata.json()["configuration"]["policy"]["invoice"]["allowed_supply_kinds"]
    )
    assert "invoice" in metadata.json()["native"]["properties"]
    replay = await client.post(prefix + "/voucher-types", headers=auth, json=body)
    assert replay.status_code == 201 and replay.json()["revision_id"] == row["revision_id"]


@pytest.mark.parametrize(
    "policy", [{}, {"invoice": None}, {"invoice": {"allowed_supply_kinds": ["SERVICE"]}}]
)
async def test_authored_purchase_policy_is_preserved(client, prefix, policy):
    row = await create_type(client, prefix, kind="PURCHASE", policy=policy)
    if policy.get("invoice"):
        assert row["policy"]["invoice"]["allowed_supply_kinds"] == ["SERVICE"]
    else:
        assert row["policy"].get("invoice") is None


async def test_cloning_purchase_preserves_legacy_policy(client, prefix):
    source = await create_type(client, prefix, code="LEGACY", kind="PURCHASE", policy={})
    row = await create_type(
        client, prefix, code="COPY", kind="PURCHASE", derived_from_revision_id=source["revision_id"]
    )
    assert row["policy"].get("invoice") is None


async def test_other_kinds_keep_existing_defaults(client, prefix):
    row = await create_type(client, prefix)
    assert row["policy"].get("invoice") is None

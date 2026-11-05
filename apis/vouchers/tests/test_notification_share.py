"""Voucher sharing is authorized, pinned and idempotent."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import TENANT, headers
from sqlalchemy import select

from tests.test_foundation import create_type, draft
from vouchers.models import core as m
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


@pytest.mark.asyncio
async def test_manual_share_requires_policy_party_and_permission(client, prefix, app) -> None:
    kind = await create_type(
        client, prefix, code="SO-NOTIFY", kind="SALES_ORDER", name="Sales order"
    )
    unconfigured, _ = await draft(
        client, prefix, kind["revision_id"], mode="ITEMS",
        fulfillment_terms={"purpose": "SALE"},
    )
    missing = await client.post(
        prefix + f'/vouchers/{unconfigured["id"]}/share',
        json={"expected_version": 1, "party_id": str(uuid7()), "channel": "email"},
        headers=headers(),
    )
    assert missing.status_code == 409

    config = await client.post(
        prefix + "/voucher-configurations",
        json={
            "code": "SO_NOTIFY", "name": "Order sharing",
            "policy": {
                "schema_version": 2,
                "notification": {
                    "enabled": True, "manual_share_allowed": True,
                    "channels": ["email"], "automatic_events": [],
                },
            },
        },
        headers=headers(),
    )
    assert config.status_code == 201, config.text
    published = await client.post(
        prefix + f'/voucher-configurations/{config.json()["id"]}/publish',
        json={"expected_version": 1}, headers=headers(),
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + f'/voucher-types/{kind["id"]}/configuration-bindings',
        json={
            "expected_version": 1,
            "configuration_revision_id": published.json()["revision_id"],
            "valid_from": "2020-01-01",
        },
        headers=headers(),
    )
    assert bound.status_code == 201, bound.text
    party = uuid7()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(), tenant_id=TENANT, company_id=uuid.UUID(prefix.rsplit("/", 1)[1]),
            masters=({
                "entity_type": "party", "source_id": party,
                "source_version": 1, "status": "ACTIVE",
            },),
        ),
        "accounting",
    )
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], mode="ITEMS",
        fulfillment_terms={"purpose": "SALE"},
        parties=[{"role": "CUSTOMER", "party_id": str(party), "source_version": 1}],
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.Voucher, uuid.UUID(voucher["id"]))
            assert row is not None
            row.status = "ISSUED"

    path = prefix + f'/vouchers/{voucher["id"]}/share'
    body = {"expected_version": 1, "party_id": str(party), "channel": "email"}
    forbidden = await client.post(
        path, json=body, headers=headers(permissions=frozenset({"vouchers.read"})),
    )
    assert forbidden.status_code == 403
    share_only = await client.post(
        path, json=body, headers=headers(permissions=frozenset({"vouchers.share"})),
    )
    assert share_only.status_code == 403
    unknown = await client.post(
        path, json=body | {"party_id": str(uuid7())}, headers=headers(),
    )
    assert unknown.status_code == 422
    key = headers()
    sent = await client.post(path, json=body, headers=key)
    assert sent.status_code == 202, sent.text
    repeated = await client.post(path, json=body, headers=key)
    assert repeated.status_code == 202
    assert repeated.headers["Idempotency-Replayed"] == "true"
    assert repeated.json()["message_id"] == sent.json()["message_id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            sends = list((await db.scalars(select(Outbox).where(
                Outbox.event_type == "notification.send",
            ))).all())
            assert len(sends) == 1
            assert sends[0].message_id == uuid.UUID(sent.json()["message_id"])
            assert sends[0].payload["subject_type"] == "party_general"
            assert sends[0].payload["subject_id"] == str(party)

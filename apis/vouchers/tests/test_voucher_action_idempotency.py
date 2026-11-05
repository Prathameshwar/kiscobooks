"""The action body hash stays what it was before ``acknowledge_duplicate_bill`` existed.

A key stored by the previous release must still replay after a deploy: its stored request hash was
built from ``{expected_version, reason}``. The acknowledgement is part of the hash only when it is
true, so an acknowledged submit is still a different request from a plain one.
"""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import IdempotencyKey
from billing_platform.idempotency import CommandIdentity
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, USER, headers
from sqlalchemy import select
from test_purchase_approval_flow import NO_APPROVAL, accept_as, bill
from test_purchase_lifecycle_integrity import owner, path

from vouchers.tasks import common

ACTIONS = ("submit", "approve", "reject", "cancel", "accept", "decline", "expire")


def old_digest(action, object_id, body, *, key, user=USER):
    """The digest the previous release computed: the body dict has no acknowledgement field."""
    return CommandIdentity(
        TENANT,
        COMPANY,
        user,
        "vouchers." + action,
        key,
        {"object_id": str(object_id), "body": body},
    ).digest()


@pytest.fixture
def identities(monkeypatch):
    seen: list[CommandIdentity] = []
    real = common.execute_idempotent

    async def spy(factory, identity, **kwargs):
        seen.append(identity)
        return await real(factory, identity, **kwargs)

    monkeypatch.setattr(common, "execute_idempotent", spy)
    return seen


@pytest.mark.parametrize("action", ACTIONS)
async def test_action_body_hash_is_unchanged_for_existing_bodies(
    client, prefix, identities, action
):
    object_id = uuid7()
    for body, stored in (
        ({"expected_version": 2}, {"expected_version": 2, "reason": ""}),
        (
            {"expected_version": 2, "reason": "Because"},
            {"expected_version": 2, "reason": "Because"},
        ),
        (
            {"expected_version": 2, "reason": "Because", "acknowledge_duplicate_bill": False},
            {"expected_version": 2, "reason": "Because"},
        ),
    ):
        sent = headers()
        await client.post(f"{prefix}/vouchers/{object_id}/{action}", json=body, headers=sent)
        identity = identities[-1]
        assert identity.request["body"] == stored
        assert identity.digest() == old_digest(
            action, object_id, stored, key=sent["Idempotency-Key"]
        )


async def test_an_acknowledged_submit_hashes_differently_from_a_plain_one(
    client, prefix, identities
):
    object_id = uuid7()
    key = headers()["Idempotency-Key"]
    plain = {"expected_version": 2, "reason": ""}
    await client.post(
        f"{prefix}/vouchers/{object_id}/submit",
        json={"expected_version": 2},
        headers=headers(key=key),
    )
    await client.post(
        f"{prefix}/vouchers/{object_id}/submit",
        json={"expected_version": 2, "acknowledge_duplicate_bill": True},
        headers=headers(key=key),
    )
    plain_identity, acknowledged_identity = identities
    assert acknowledged_identity.request["body"] == plain | {"acknowledge_duplicate_bill": True}
    assert plain_identity.digest() == old_digest("submit", object_id, plain, key=key)
    assert acknowledged_identity.digest() != plain_identity.digest()


async def test_a_key_stored_before_the_field_existed_still_replays(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    accepted = await accept_as(client, prefix, document, user)
    sent = headers(user=user)
    key = sent["Idempotency-Key"]
    url = path(prefix, accepted, "/submit")
    body = {"expected_version": accepted["row_version"]}
    first = await client.post(url, json=body, headers=sent)
    assert first.status_code == 200, first.text
    # What the previous release stored for exactly this request.
    stored = old_digest(
        "submit",
        uuid.UUID(accepted["id"]),
        {"expected_version": accepted["row_version"], "reason": ""},
        key=key,
        user=user,
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(
                select(IdempotencyKey).where(IdempotencyKey.endpoint == "vouchers.submit")
            )
            assert row.request_hash == stored
    again = await client.post(url, json=body, headers=sent)
    assert again.status_code == 200, again.text
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["status"] == "APPROVED"
    # The same key with the acknowledgement set is a different request, not a replay.
    changed = await client.post(url, json=body | {"acknowledge_duplicate_bill": True}, headers=sent)
    assert changed.status_code == 422, changed.text
    assert "another request" in changed.json()["error"]["message"]

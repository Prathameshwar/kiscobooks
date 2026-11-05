"""A control left out of a type's policy is never read as "off".

The company envelope starts permissive (no approval, self-approval allowed) and a type narrows it.
A version 2 policy stores only the keys it was given, and for most keys a missing one inherits the
envelope. For the two approval controls that is the wrong direction: the form shows a missing
``approval_required`` as on and ``self_approval_allowed`` as off (the schema defaults), and with
submit now approving in one step where approval is not required, reading a missing key as the
envelope's value would let a bill skip a control the administrator sees as set.
"""

from billing_platform.ids import uuid7
from test_foundation import create_type
from test_purchase_approval_flow import (
    NEEDS_ANOTHER,
    accept_as,
    act,
    bill,
)
from test_purchase_lifecycle_integrity import owner

OMITTED = {"schema_version": 2, "invoice": {}}
EXPLICIT_OFF = {"schema_version": 2, "invoice": {}, "approval_required": False}


async def test_a_version_2_policy_that_leaves_approval_unset_still_requires_it(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, OMITTED, user=user)
    accepted = await accept_as(client, prefix, document, user)
    submitted = await act(client, prefix, accepted, "submit", user)
    assert submitted.status_code == 200, submitted.text
    # Waiting for a decision, not approved by the envelope's silence.
    assert submitted.json()["status"] == "SUBMITTED"


async def test_a_version_2_policy_that_leaves_self_approval_unset_forbids_it(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, OMITTED, user=user)
    submitted = (
        await act(client, prefix, await accept_as(client, prefix, document, user), "submit", user)
    ).json()
    refused = await act(client, prefix, submitted, "approve", user)
    assert refused.status_code == 403, refused.text
    assert NEEDS_ANOTHER in refused.json()["error"]["message"]
    approved = await act(client, prefix, submitted, "approve", uuid7())
    assert approved.status_code == 200, approved.text


async def test_an_explicit_no_approval_still_approves_on_submit(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, EXPLICIT_OFF, user=user)
    submitted = await act(
        client, prefix, await accept_as(client, prefix, document, user), "submit", user
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "APPROVED"


async def test_the_type_can_still_be_created_with_the_keys_left_out(client, prefix):
    kind = await create_type(client, prefix, kind="PURCHASE", policy=OMITTED)
    assert kind["revision_id"]

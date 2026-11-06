"""Approval is a configuration choice, not a hurdle every company must clear (decision D1).

When the effective policy does not require approval, ``submit`` approves in the same step, so a
single-user company can post. When it does, separation of duties is unchanged and is now enforced
for the whole voucher, not only for the revision that happens to be current (D1b).
"""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import func, select
from voucher_execution import ExecutionResult
from test_foundation import create_type
from test_invoice_capture import invoice_body
from test_money_posting import authority_headers
from test_purchase_lifecycle_integrity import (
    CALCULATION,
    TODAY,
    owner,
    path,
    request_for,
    seed,
)

from vouchers.domain.documents import transition
from vouchers.models import core as m
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle
from vouchers.tasks.operations import apply_result

NO_APPROVAL = {"invoice": {}, "approval_required": False}
REQUIRED = {"invoice": {}}
NEEDS_ANOTHER = "another authorized actor must approve"
AUTOMATIC = "approval not required by the voucher configuration"


async def bill(client, prefix, app, policy, *, user=None):
    """A saved account/service Purchase draft (created by ``user``) and its request."""
    kind = await create_type(client, prefix, kind="PURCHASE", policy=policy)
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    request = request_for(kind, body, supplier)
    created = await client.post(
        prefix + "/vouchers", json=request, headers=headers(user=user or uuid7())
    )
    assert created.status_code == 201, created.text
    return created.json(), request


async def accept_as(client, prefix, document, user, version=None):
    accepted = await client.post(
        path(prefix, document, "/invoice-acceptance"),
        json={
            "expected_version": version or document["row_version"],
            "calculation_hash": CALCULATION,
        },
        headers=headers(user=user),
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


async def act(client, prefix, document, action, user, **body):
    return await client.post(
        path(prefix, document, "/" + action),
        json={"expected_version": document["row_version"]} | body,
        headers=headers(user=user),
    )


# 1. The transition table ---------------------------------------------------------------------


def test_submit_goes_straight_to_approved_only_when_approval_is_not_required():
    assert transition("DRAFT", "submit", approval_required=False) == "APPROVED"
    assert transition("REJECTED", "submit", approval_required=False) == "APPROVED"
    assert transition("DRAFT", "submit", approval_required=True) == "SUBMITTED"
    assert transition("REJECTED", "submit", approval_required=True) == "SUBMITTED"
    for required in (True, False):
        # A voucher that is already approved by policy is never approved or rejected again.
        for action in ("approve", "reject"):
            with pytest.raises(ConflictError):
                transition("APPROVED", action, approval_required=required)
        with pytest.raises(ConflictError):
            transition("APPROVED", "submit", approval_required=required)


# 2. A company that needs no approval ---------------------------------------------------------


async def test_submit_approves_in_one_step_when_approval_is_not_required(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    accepted = await accept_as(client, prefix, document, user)
    submitted = await act(client, prefix, accepted, "submit", user)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "APPROVED"
    assert submitted.json()["row_version"] == accepted["row_version"] + 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherApproval.id))) == 0
            transitions = list(
                await db.scalars(
                    select(m.VoucherTransition)
                    .where(m.VoucherTransition.action == "submit")
                    .order_by(m.VoucherTransition.id)
                )
            )
            assert [(row.from_status, row.to_status) for row in transitions] == [
                ("DRAFT", "APPROVED")
            ]
            assert AUTOMATIC in transitions[0].reason
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "vouchers.voucher.submit")
            )
            assert AUTOMATIC in event.payload["reason"]
            assert event.payload["changes"]["to_status"] == "APPROVED"
            assert event.payload["changes"]["approval"] == "not_required"
            assert event.payload["actor_user_id"] == str(user)


async def test_a_voucher_approved_by_policy_cannot_be_approved_or_rejected_again(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    approved = (
        await act(client, prefix, await accept_as(client, prefix, document, user), "submit", user)
    ).json()
    assert approved["status"] == "APPROVED"
    for action, extra in (("approve", {}), ("reject", {"reason": "No"})):
        for actor in (user, uuid7()):
            refused = await act(client, prefix, approved, action, actor, **extra)
            assert refused.status_code == 409, refused.text
            assert "not allowed in its current state" in refused.json()["error"]["message"]
    unchanged = await client.get(path(prefix, approved), headers=headers(user=user))
    assert unchanged.json()["status"] == "APPROVED"
    assert unchanged.json()["row_version"] == approved["row_version"]


async def test_submit_replay_with_the_same_key_has_one_effect(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    accepted = await accept_as(client, prefix, document, user)
    key = headers(user=user)
    url = path(prefix, accepted, "/submit")
    first = await client.post(url, json={"expected_version": accepted["row_version"]}, headers=key)
    again = await client.post(url, json={"expected_version": accepted["row_version"]}, headers=key)
    assert first.status_code == again.status_code == 200
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["status"] == "APPROVED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherTransition.id))) == 1
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "vouchers.voucher.submit"
                    )
                )
                == 1
            )


async def test_editing_an_auto_approved_voucher_reopens_it_and_it_can_be_resubmitted(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, request = await bill(client, prefix, app, NO_APPROVAL, user=user)
    approved = (
        await act(client, prefix, await accept_as(client, prefix, document, user), "submit", user)
    ).json()
    edited = await client.put(
        path(prefix, approved),
        json={
            "expected_version": approved["row_version"],
            "content": request | {"narration": "Reworded"},
        },
        headers=headers(user=user),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "DRAFT"
    accepted = await accept_as(client, prefix, edited.json(), user)
    again = await act(client, prefix, accepted, "submit", user)
    assert again.status_code == 200 and again.json()["status"] == "APPROVED"


async def test_an_auto_approved_purchase_still_posts_without_approval_rows(
    client, prefix, app, monkeypatch
):
    """The execution command carries no approval ids and the worker's identity check accepts it."""
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    approved = (
        await act(client, prefix, await accept_as(client, prefix, document, user), "submit", user)
    ).json()
    assert approved["status"] == "APPROVED"
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {"start_date": TODAY, "end_date": TODAY},
                    }
                ],
            }
        ),
        "accounting",
    )
    app.state.settings.invoice_execution_enabled = True
    posted = await client.post(
        path(prefix, approved, "/post"),
        json={"expected_version": approved["row_version"]},
        headers=authority_headers(user=user),
    )
    assert posted.status_code == 202, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.get(m.VoucherOperation, uuid.UUID(posted.json()["operation_id"]))
            assert operation.status == "PENDING"
            assert operation.command["approval_ids"] == []
            assert await db.scalar(select(func.count(m.VoucherApproval.id))) == 0


async def test_posted_account_purchase_can_request_guarded_reversal(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    user = uuid7()
    document, request = await bill(client, prefix, app, NO_APPROVAL, user=user)
    approved = (
        await act(client, prefix, await accept_as(client, prefix, document, user), "submit", user)
    ).json()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {"start_date": TODAY, "end_date": TODAY},
                    }
                ],
            }
        ),
        "accounting",
    )
    app.state.settings.invoice_execution_enabled = True
    app.state.settings.money_execution_enabled = True
    posted = await client.post(
        path(prefix, approved, "/post"),
        json={"expected_version": approved["row_version"]},
        headers=authority_headers(user=user),
    )
    assert posted.status_code == 202, posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            operation = await db.get(m.VoucherOperation, uuid.UUID(posted.json()["operation_id"]))
            await apply_result(
                db,
                ExecutionResult(
                    protocol_version=2,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    operation_id=operation.id,
                    execution_id=operation.execution_id,
                    content_hash=operation.content_hash,
                    configuration_hash=operation.configuration_hash,
                    request_hash=operation.request_hash,
                    outcome="COMMITTED",
                    committed_at=dt.datetime.now(dt.UTC),
                    committed_generation=1,
                    effects=[
                        {"owner": "accounting", "effect_kind": "SOURCE_RECEIPT", "effect_id": uuid7()}
                    ],
                ),
            )
    current = await client.get(path(prefix, approved), headers=headers(user=user))
    assert current.json()["status"] == "POSTED"
    reversed_response = await client.post(
        path(prefix, approved, "/reverse"),
        json={
            "expected_version": current.json()["row_version"],
            "posting_date": TODAY,
            "reason": "Correct the supplier bill",
        },
        headers=authority_headers(user=user),
    )
    assert reversed_response.status_code == 202, reversed_response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            operation = await db.get(
                m.VoucherOperation, uuid.UUID(reversed_response.json()["operation_id"])
            )
            await apply_result(
                db,
                ExecutionResult(
                    protocol_version=2,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    operation_id=operation.id,
                    execution_id=operation.execution_id,
                    content_hash=operation.content_hash,
                    configuration_hash=operation.configuration_hash,
                    request_hash=operation.request_hash,
                    outcome="COMMITTED",
                    committed_at=dt.datetime.now(dt.UTC),
                    committed_generation=2,
                    effects=[
                        {"owner": "accounting", "effect_kind": "SOURCE_RECEIPT", "effect_id": uuid7()}
                    ],
                ),
            )
    original = (await client.get(path(prefix, approved), headers=headers(user=user))).json()
    assert original["status"] == "REVERSED"
    replacement_request = request | {
        "links": [
            {
                "purpose": "CORRECTION",
                "source_voucher_id": original["id"],
                "source_revision_id": original["revision_id"],
            }
        ]
    }
    replacement = await client.post(
        prefix + "/vouchers", json=replacement_request, headers=headers(user=user)
    )
    assert replacement.status_code == 201, replacement.text
    accepted = await accept_as(client, prefix, replacement.json(), user)
    resubmitted = await act(client, prefix, accepted, "submit", user)
    assert resubmitted.status_code == 200, resubmitted.text
    replacement_post = await client.post(
        path(prefix, resubmitted.json(), "/post"),
        json={"expected_version": resubmitted.json()["row_version"]},
        headers=authority_headers(user=user),
    )
    assert replacement_post.status_code == 202, replacement_post.text
    assert replacement_post.json()["operation_id"] != posted.json()["operation_id"]
    duplicate = await client.post(
        prefix + "/vouchers", json=replacement_request, headers=headers(user=user)
    )
    assert duplicate.status_code == 201, duplicate.text
    duplicate_accepted = await accept_as(client, prefix, duplicate.json(), user)
    duplicate_submitted = await act(
        client,
        prefix,
        duplicate_accepted,
        "submit",
        user,
        acknowledge_duplicate_bill=True,
    )
    assert duplicate_submitted.status_code == 200, duplicate_submitted.text
    second_post = await client.post(
        path(prefix, duplicate_submitted.json(), "/post"),
        json={"expected_version": duplicate_submitted.json()["row_version"]},
        headers=authority_headers(user=user),
    )
    assert second_post.status_code == 409
    assert "already has a posting replacement" in second_post.json()["error"]["message"]


async def test_a_legacy_submitted_voucher_under_no_approval_policy_needs_no_second_person(
    client, prefix, app, monkeypatch
):
    """Separation of duties applies only where approval is required."""
    owner(app, monkeypatch)
    user = uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=user)
    accepted = await accept_as(client, prefix, document, user)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            voucher = await db.get(m.Voucher, uuid.UUID(accepted["id"]))
            voucher.status = "SUBMITTED"  # submitted before the company stopped needing approval
            voucher.row_version += 1
            accepted = accepted | {"row_version": voucher.row_version}
    approved = await act(client, prefix, accepted, "approve", user)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


# 3. Approval required: separation of duties across every revision ----------------------------


async def test_approval_required_keeps_submit_and_a_second_approver(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    author, approver = uuid7(), uuid7()
    document, _ = await bill(client, prefix, app, REQUIRED, user=author)
    accepted = await accept_as(client, prefix, document, author)
    submitted = await act(client, prefix, accepted, "submit", author)
    assert submitted.status_code == 200 and submitted.json()["status"] == "SUBMITTED"
    mine = await act(client, prefix, submitted.json(), "approve", author)
    assert mine.status_code == 403, mine.text
    approved = await act(client, prefix, submitted.json(), "approve", approver)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherApproval.id))) == 1


async def test_the_creator_cannot_approve_after_someone_else_accepts_the_calculation(
    client, prefix, app, monkeypatch
):
    """A creates, B accepts (a new revision by B), A approves: refused. C approves: allowed."""
    owner(app, monkeypatch)
    creator, accepter, third = uuid7(), uuid7(), uuid7()
    document, _ = await bill(client, prefix, app, REQUIRED, user=creator)
    accepted = await accept_as(client, prefix, document, accepter)
    assert accepted["revision_number"] == 2
    submitted = (await act(client, prefix, accepted, "submit", accepter)).json()
    assert submitted["status"] == "SUBMITTED"
    by_creator = await act(client, prefix, submitted, "approve", creator)
    assert by_creator.status_code == 403, by_creator.text
    assert NEEDS_ANOTHER in by_creator.json()["error"]["message"]
    by_accepter = await act(client, prefix, submitted, "approve", accepter)
    assert by_accepter.status_code == 403, by_accepter.text
    unchanged = await client.get(path(prefix, submitted), headers=headers(user=third))
    assert unchanged.json()["status"] == "SUBMITTED"
    approved = await act(client, prefix, submitted, "approve", third)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


async def test_an_author_of_any_earlier_revision_cannot_approve(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    creator, editor = uuid7(), uuid7()
    document, request = await bill(client, prefix, app, REQUIRED, user=creator)
    edited = await client.put(
        path(prefix, document),
        json={
            "expected_version": document["row_version"],
            "content": request | {"narration": "Edited by someone else"},
        },
        headers=headers(user=editor),
    )
    assert edited.status_code == 200, edited.text
    accepted = await accept_as(client, prefix, edited.json(), editor)
    submitted = (await act(client, prefix, accepted, "submit", editor)).json()
    refused = await act(client, prefix, submitted, "approve", creator)
    assert refused.status_code == 403, refused.text


async def test_a_policy_that_allows_self_approval_still_lets_the_creator_approve(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    creator, accepter = uuid7(), uuid7()
    document, _ = await bill(
        client, prefix, app, REQUIRED | {"self_approval_allowed": True}, user=creator
    )
    accepted = await accept_as(client, prefix, document, accepter)
    submitted = (await act(client, prefix, accepted, "submit", accepter)).json()
    approved = await act(client, prefix, submitted, "approve", creator)
    assert approved.status_code == 200, approved.text


async def test_approval_needs_the_approve_permission_and_this_company(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    creator = uuid7()
    document, _ = await bill(client, prefix, app, REQUIRED, user=creator)
    accepted = await accept_as(client, prefix, document, creator)
    submitted = (await act(client, prefix, accepted, "submit", creator)).json()
    body = {"expected_version": submitted["row_version"]}
    url = path(prefix, submitted, "/approve")
    assert (await client.post(url, json=body)).status_code == 401
    lacking = headers(
        user=uuid7(),
        permissions=frozenset({"vouchers.read", "vouchers.submit"}),
    )
    assert (await client.post(url, json=body, headers=lacking)).status_code == 403
    other = uuid7()
    foreign = await client.post(
        url.replace(str(COMPANY), str(other)), json=body, headers=headers(company=other)
    )
    assert foreign.status_code == 403
    assert (
        await client.post(url, json={"expected_version": "x"}, headers=headers(user=uuid7()))
    ).status_code == 422


async def test_the_person_who_only_submitted_cannot_approve(client, prefix, app, monkeypatch):
    """A creates and accepts, B only submits: B is not an independent approver, C is."""
    owner(app, monkeypatch)
    creator, submitter, third = uuid7(), uuid7(), uuid7()
    document, _ = await bill(client, prefix, app, REQUIRED, user=creator)
    accepted = await accept_as(client, prefix, document, creator)
    submitted = await act(client, prefix, accepted, "submit", submitter)
    assert submitted.status_code == 200 and submitted.json()["status"] == "SUBMITTED"
    refused = await act(client, prefix, submitted.json(), "approve", submitter)
    assert refused.status_code == 403, refused.text
    assert NEEDS_ANOTHER in refused.json()["error"]["message"]
    by_creator = await act(client, prefix, submitted.json(), "approve", creator)
    assert by_creator.status_code == 403, by_creator.text
    unchanged = await client.get(path(prefix, submitted.json()), headers=headers(user=third))
    assert unchanged.json()["status"] == "SUBMITTED"
    approved = await act(client, prefix, submitted.json(), "approve", third)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


async def test_a_resubmitter_after_rejection_cannot_approve(client, prefix, app, monkeypatch):
    """Every submission counts, not only the latest: B submits, C rejects, A resubmits."""
    owner(app, monkeypatch)
    creator, first, rejecter = uuid7(), uuid7(), uuid7()
    document, _ = await bill(client, prefix, app, REQUIRED, user=creator)
    accepted = await accept_as(client, prefix, document, creator)
    submitted = (await act(client, prefix, accepted, "submit", first)).json()
    rejected = await act(client, prefix, submitted, "reject", rejecter, reason="Fix the bill")
    assert rejected.status_code == 200, rejected.text
    resubmitted = (await act(client, prefix, rejected.json(), "submit", creator)).json()
    assert resubmitted["status"] == "SUBMITTED"
    refused = await act(client, prefix, resubmitted, "approve", first)
    assert refused.status_code == 403, refused.text
    approved = await act(client, prefix, resubmitted, "approve", rejecter)
    assert approved.status_code == 200, approved.text


async def test_a_submitter_may_approve_when_self_approval_is_allowed(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    creator, submitter = uuid7(), uuid7()
    document, _ = await bill(
        client, prefix, app, REQUIRED | {"self_approval_allowed": True}, user=creator
    )
    accepted = await accept_as(client, prefix, document, creator)
    submitted = (await act(client, prefix, accepted, "submit", submitter)).json()
    approved = await act(client, prefix, submitted, "approve", submitter)
    assert approved.status_code == 200, approved.text


async def test_a_submitter_needs_no_approval_when_it_is_not_required(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    creator, submitter = uuid7(), uuid7()
    document, _ = await bill(client, prefix, app, NO_APPROVAL, user=creator)
    accepted = await accept_as(client, prefix, document, creator)
    submitted = await act(client, prefix, accepted, "submit", submitter)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "APPROVED"

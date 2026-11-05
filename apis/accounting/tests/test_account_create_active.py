"""`POST /accounts/create-active`: an account is created and activated in one atomic command.

`POST /accounts` leaves a draft and a second call activates it, which is not atomic and leaves a
draft behind when the second call fails. The one-shot command runs the very same create and
activate mutations in one transaction, so it is create-then-activate with nothing left on failure.
"""

from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models import MasterRevision
from tests.conftest import COMPANY, PERMISSIONS, TENANT, headers
from tests.test_masters import prepare

BASE = f"/v1/companies/{COMPANY}"
URL = BASE + "/accounts/create-active"


def body(groups: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {
        "code": "EXP-QA1",
        "name": "Quick expense",
        "group_id": groups["INDIRECT_EXPENSES"],
    } | extra


async def accounts(client: httpx.AsyncClient, **params: str) -> list[dict[str, Any]]:
    return (await client.get(BASE + "/accounts", headers=headers(), params=params)).json()["items"]


async def trail(app: FastAPI, object_id: str | None = None) -> dict[str, Any]:
    """Revisions and audit events for accounts: everything a failed command must leave untouched."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revisions = (
                await db.execute(
                    select(MasterRevision.action, MasterRevision.object_id).where(
                        MasterRevision.entity_type == "account"
                    )
                )
            ).all()
            events = (
                await db.scalars(
                    select(Outbox.event_type).where(Outbox.aggregate_type == "accounting.account")
                )
            ).all()
            total = await db.scalar(select(func.count()).select_from(Outbox))
    own = [action for action, ident in revisions if str(ident) == object_id]
    return {
        "revisions": len(revisions),
        "events": len(events),
        "outbox": total,
        "actions": own,
    }


async def test_one_call_creates_an_active_account_with_the_create_and_the_activate_audited(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    created = await client.post(URL, json=body(groups), headers=headers())
    assert created.status_code == 201, created.text
    account = created.json()
    assert created.headers["Location"] == f"../accounts/{account['id']}"
    assert created.headers["Idempotency-Replayed"] == "false"
    assert account["status"] == "ACTIVE"
    assert (account["code"], account["name"], account["group_id"]) == (
        "EXP-QA1",
        "Quick expense",
        groups["INDIRECT_EXPENSES"],
    )
    assert account["kind"] == "GENERAL" and account["currency_mode"] == "BASE"
    assert account["posting_policy"] == "MANUAL_ALLOWED" and account["row_version"] == 2
    assert (
        await client.get(BASE + "/accounts/" + account["id"], headers=headers())
    ).json() == account
    after = await trail(app, account["id"])
    assert after["actions"] == ["create", "activate"]
    assert after["revisions"] - before["revisions"] == 2
    assert after["events"] - before["events"] == 2


async def test_it_is_the_same_account_that_create_then_activate_gives(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    one_shot = (await client.post(URL, json=body(groups), headers=headers())).json()
    draft = await client.post(
        BASE + "/accounts", json=body(groups, code="EXP-QA2"), headers=headers()
    )
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT"
    two_step = await client.post(
        BASE + "/accounts/" + draft.json()["id"] + "/activate",
        json={"expected_version": draft.json()["row_version"]},
        headers=headers(),
    )
    assert two_step.status_code == 200, two_step.text
    ignored = {"id", "code", "created_at", "updated_at"}
    assert {k: v for k, v in one_shot.items() if k not in ignored} == {
        k: v for k, v in two_step.json().items() if k not in ignored
    }


async def test_a_refusal_is_the_one_create_would_give_and_leaves_nothing(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    # incompatible kind and group head: the same 422 as POST /accounts
    mismatched = {"kind": "CASH", "group_id": groups["INDIRECT_EXPENSES"]}
    plain = await client.post(
        BASE + "/accounts", json=body(groups, code="PLAIN", **mismatched), headers=headers()
    )
    after_plain = await trail(app)
    refused = await client.post(URL, json=body(groups, **mismatched), headers=headers())
    assert plain.status_code == refused.status_code == 422, (plain.text, refused.text)
    assert refused.json()["error"]["code"] == plain.json()["error"]["code"]
    assert await trail(app) == after_plain  # create-active added no revision or audit event
    assert [row["code"] for row in await accounts(client, code="EXP-QA1")] == []
    assert before["revisions"] == after_plain["revisions"]


async def test_unknown_and_invalid_fields_are_refused_before_anything_happens(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    for extra in ({"status": "ACTIVE"}, {"unknown": 1}, {"kind": "NOPE"}, {"currency": "usd"}):
        refused = await client.post(URL, json=body(groups, **extra), headers=headers())
        assert refused.status_code == 422, (extra, refused.text)
    missing = await client.post(URL, json={"code": "X1"}, headers=headers())
    assert missing.status_code == 422
    assert await trail(app) == before


async def test_a_group_of_another_company_is_not_found_and_leaves_nothing(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    foreign = await client.post(URL, json=body(groups, group_id=str(uuid7())), headers=headers())
    assert foreign.status_code == 404, foreign.text
    assert await trail(app) == before
    assert await accounts(client, code="EXP-QA1") == []


async def test_a_group_that_is_not_active_fails_the_activation_and_rolls_the_creation_back(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    head = (
        await client.get(BASE + "/account-groups/" + groups["INDIRECT_EXPENSES"], headers=headers())
    ).json()["head_id"]
    draft = await client.post(
        BASE + "/account-groups",
        json={"code": "DRAFTGRP", "name": "Draft group", "head_id": head},
        headers=headers(),
    )
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT", draft.text
    before = await trail(app)
    refused = await client.post(
        URL, json=body(groups, group_id=draft.json()["id"]), headers=headers()
    )
    # creating under a draft group is allowed, activating is not: the whole command is refused
    assert refused.status_code == 409, refused.text
    assert await trail(app) == before
    assert await accounts(client, code="EXP-QA1") == []


async def test_a_code_clash_is_refused_and_nothing_is_left_behind(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    assert (await client.post(URL, json=body(groups), headers=headers())).status_code == 201
    before = await trail(app)
    clash = await client.post(URL, json=body(groups, name="Another"), headers=headers())
    plain = await client.post(
        BASE + "/accounts", json=body(groups, name="Another"), headers=headers()
    )
    assert clash.status_code == plain.status_code, (clash.text, plain.text)
    assert clash.status_code in {409, 422}
    assert clash.json()["error"]["code"] == plain.json()["error"]["code"]
    after = await trail(app)
    assert after == before  # nothing new, not even a draft
    assert [row["name"] for row in await accounts(client, code="EXP-QA1")] == ["Quick expense"]


async def test_replay_with_the_same_key_returns_the_same_account_and_creates_no_second(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    authority = headers()
    first = await client.post(URL, json=body(groups), headers=authority)
    after_first = await trail(app)
    again = await client.post(URL, json=body(groups), headers=authority)
    assert first.status_code == again.status_code == 201, (first.text, again.text)
    assert again.json() == first.json()
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.headers["Location"] == first.headers["Location"]
    assert len(await accounts(client, code="EXP-QA1")) == 1
    assert await trail(app) == after_first
    # the same key with a different body is the client's bug, never a second account
    changed = await client.post(URL, json=body(groups, name="Different"), headers=authority)
    assert changed.status_code == 422, changed.text
    assert len(await accounts(client, code="EXP-QA1")) == 1


async def test_a_replay_is_not_shared_with_the_two_step_create(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    authority = headers()
    one_shot = await client.post(URL, json=body(groups), headers=authority)
    assert one_shot.status_code == 201
    # same key on the plain create is another operation: it meets the code clash, it is not replayed
    plain = await client.post(BASE + "/accounts", json=body(groups), headers=authority)
    assert plain.status_code in {409, 422}
    assert plain.headers.get("Idempotency-Replayed") != "true"


async def test_it_needs_authentication(client: httpx.AsyncClient, app: FastAPI) -> None:
    groups = await prepare(client)
    before = await trail(app)
    assert (await client.post(URL, json=body(groups))).status_code == 401
    assert await trail(app) == before


async def test_it_needs_both_manage_and_read_on_accounts(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    for missing in ("accounting.account.manage", "accounting.account.read"):
        refused = await client.post(
            URL, json=body(groups), headers=headers(permissions=PERMISSIONS - {missing})
        )
        assert refused.status_code == 403, (missing, refused.text)
    assert await trail(app) == before
    assert await accounts(client, code="EXP-QA1") == []


async def test_an_account_of_another_company_cannot_be_created_here(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await trail(app)
    # an actor whose grants are for this company, acting under another company's context
    other = uuid7()
    foreign = headers(company=other)
    mine = headers()
    foreign["X-Actor-Context"], foreign["X-Actor-Signature"] = (
        mine["X-Actor-Context"],
        mine["X-Actor-Signature"],
    )
    refused = await client.post(
        f"/v1/companies/{other}/accounts/create-active", json=body(groups), headers=foreign
    )
    assert refused.status_code == 403, refused.text
    assert await trail(app) == before


async def test_another_tenant_cannot_see_the_new_account(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    created = await client.post(URL, json=body(groups), headers=headers())
    assert created.status_code == 201
    outsider = headers(tenant=uuid7())
    assert (
        await client.get(BASE + "/accounts/" + created.json()["id"], headers=outsider)
    ).status_code == 404
    assert (await client.get(BASE + "/accounts", headers=outsider)).json()["items"] == []
    # and the same key under another tenant is another command, not this tenant's receipt
    other = await client.post(
        URL, json=body(groups), headers=headers(tenant=uuid7(), key="other-tenant")
    )
    assert other.status_code in {403, 404, 409, 422}


async def test_the_existing_two_step_create_and_activate_is_unchanged(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    draft = await client.post(BASE + "/accounts", json=body(groups), headers=headers())
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT"
    assert draft.headers["Location"] == "accounts/" + draft.json()["id"]
    active = await client.post(
        BASE + "/accounts/" + draft.json()["id"] + "/activate",
        json={"expected_version": draft.json()["row_version"]},
        headers=headers(),
    )
    assert active.status_code == 200 and active.json()["status"] == "ACTIVE"

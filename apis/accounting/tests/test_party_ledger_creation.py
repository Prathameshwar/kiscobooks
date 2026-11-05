"""A party is created with its ledger, always: one command, one transaction, one audit trail.

Every party role has exactly one active party account, created with the role
(docs/party-ledger-mandatory-plan.md). `POST /parties/create-with-details` therefore needs a
`role`, and creates the account (kind PARTY, its party and the role's account role) in the same
transaction, under the company's standard debtors/creditors group unless told otherwise. The body's
`ledger` is only optional choices (code, name, group, currency); leaving it out takes the defaults.
"""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models import MasterRevision
from accounting.models.masters import AccountGroup
from tests.conftest import COMPANY, PERMISSIONS, TENANT, headers
from tests.test_masters import activate, new_party, post, prepare

BASE = f"/v1/companies/{COMPANY}"
URL = BASE + "/parties/create-with-details"
# `ledger` only carries choices, so leaving it out and sending it empty are the same request.
LEDGER_CHOICES: list[dict[str, Any]] = [{}, {"ledger": {}}]
# party role -> (account role, standard group). The account table has no BROKER role, so a broker
# and an "other" party both hold an OTHER account, under Sundry Creditors.
LEDGER_FOR = {
    "SUPPLIER": ("SUPPLIER", "CREDITORS"),
    "CUSTOMER": ("CUSTOMER", "DEBTORS"),
    "BROKER": ("OTHER", "CREDITORS"),
    "OTHER": ("OTHER", "CREDITORS"),
}


def body(role: str | None = "SUPPLIER", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": "QS1",
        "name": "Quick supplier",
        "legal_name": "Quick supplier Pvt Ltd",
        "country_code": "IN",
    }
    if role:
        result["role"] = role
    return result | extra


async def accounts_of(client: httpx.AsyncClient, party_id: str) -> list[dict[str, Any]]:
    page = (
        await client.get(BASE + "/accounts", headers=headers(), params={"party_id": party_id})
    ).json()["items"]
    return [
        (await client.get(BASE + "/accounts/" + row["id"], headers=headers())).json()
        for row in page
    ]


async def counts(app: FastAPI) -> dict[str, int]:
    """What a failed command must leave exactly as it found it."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revisions = await db.scalar(
                select(func.count(MasterRevision.id)).where(
                    MasterRevision.entity_type.in_(["party", "party_role", "account"])
                )
            )
            events = await db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.aggregate_type.like("accounting.%"))
            )
    return {"revisions": revisions or 0, "events": events or 0}


async def listing(client: httpx.AsyncClient, resource: str) -> list[dict[str, Any]]:
    return (await client.get(BASE + "/" + resource, headers=headers())).json()["items"]


@pytest.mark.parametrize("omitted", [False, True])
@pytest.mark.parametrize("role", ["SUPPLIER", "CUSTOMER", "BROKER", "OTHER"])
async def test_the_ledger_is_created_with_the_party_under_the_standard_group(
    client: httpx.AsyncClient, role: str, omitted: bool
) -> None:
    groups = await prepare(client)
    # `ledger` only carries choices: leaving it out creates the same account as an empty one.
    request = body(role) if omitted else body(role, ledger={})
    created = await client.post(URL, json=request, headers=headers())
    assert created.status_code == 201, created.text
    party = created.json()
    assert party["status"] == "ACTIVE"
    roles = (
        await client.get(BASE + "/party-roles", headers=headers(), params={"party_id": party["id"]})
    ).json()["items"]
    assert [(row["role"], row["status"]) for row in roles] == [(role, "ACTIVE")]
    account_role, group = LEDGER_FOR[role]
    [ledger] = await accounts_of(client, party["id"])
    assert (
        ledger["kind"] == "PARTY"
        and ledger["party_id"] == party["id"]
        and ledger["party_role"] == account_role
    )
    assert ledger["group_id"] == groups[group]
    assert ledger["status"] == "ACTIVE" and ledger["posting_policy"] == "MANUAL_ALLOWED"
    assert ledger["currency_mode"] == "BASE" and ledger.get("currency") is None
    # defaults: the party's own code and name
    assert ledger["code"] == "QS1" and ledger["name"] == "Quick supplier"


async def test_code_and_name_can_be_chosen(client: httpx.AsyncClient) -> None:
    await prepare(client)
    created = await client.post(
        URL,
        json=body(ledger={"code": "QS1-PAY", "name": "Quick supplier payable"}),
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    [ledger] = await accounts_of(client, created.json()["id"])
    assert (ledger["code"], ledger["name"]) == ("QS1-PAY", "Quick supplier payable")


async def test_an_explicit_group_is_honoured(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    created = await client.post(
        URL, json=body(ledger={"group_id": groups["CURRENT_LIABILITIES"]}), headers=headers()
    )
    assert created.status_code == 201, created.text
    [ledger] = await accounts_of(client, created.json()["id"])
    assert ledger["group_id"] == groups["CURRENT_LIABILITIES"]


async def test_a_group_can_be_chosen_for_a_broker_or_other_party(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    # The OTHER account role can sit under any head, so the debtors group is allowed for it.
    created = await client.post(
        URL, json=body("OTHER", ledger={"group_id": groups["DEBTORS"]}), headers=headers()
    )
    assert created.status_code == 201, created.text
    [ledger] = await accounts_of(client, created.json()["id"])
    assert (ledger["party_role"], ledger["group_id"]) == ("OTHER", groups["DEBTORS"])


@pytest.mark.parametrize("role", [None, "VENDOR", "customer"])
async def test_a_role_is_required_and_must_be_known(
    client: httpx.AsyncClient, app: FastAPI, role: str | None
) -> None:
    await prepare(client)
    before = await counts(app)
    for choices in LEDGER_CHOICES:
        refused = await client.post(URL, json=body(role, **choices), headers=headers())
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "validation_failed"
    assert await listing(client, "parties") == []
    assert await counts(app) == before


async def test_a_ledger_group_must_be_this_companys_active_and_compatible(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    before = await counts(app)
    for group, role in (
        (str(uuid7()), "SUPPLIER"),
        (str(uuid7()), "BROKER"),
        (groups["DEBTORS"], "SUPPLIER"),
        (groups["CREDITORS"], "CUSTOMER"),
    ):
        refused = await client.post(
            URL, json=body(role, ledger={"group_id": group}), headers=headers()
        )
        assert refused.status_code == 422, refused.text
        assert "ledger.group_id" in refused.json()["error"]["fields"], refused.text
    assert await listing(client, "parties") == []
    assert await counts(app) == before


async def test_a_missing_standard_group_is_refused_not_guessed(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    # system groups cannot be retired through the API, so make the standard one unavailable directly
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.scalar(
                select(AccountGroup).where(AccountGroup.id == uuid.UUID(groups["CREDITORS"]))
            )
            assert row is not None
            row.status = "INACTIVE"
    # whether or not the caller said anything about the ledger: the party is never made without it
    for choices in LEDGER_CHOICES:
        refused = await client.post(URL, json=body(**choices), headers=headers())
        assert refused.status_code == 422, refused.text
        assert "ledger.group_id" in refused.json()["error"]["fields"]
    assert await listing(client, "parties") == []


async def test_a_code_clash_rolls_the_whole_command_back(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    first = await client.post(URL, json=body(ledger={}), headers=headers())
    assert first.status_code == 201, first.text
    before = await counts(app)
    parties, roles = await listing(client, "parties"), await listing(client, "party-roles")
    clash = await client.post(
        URL,
        json=body(code="QS2", name="Another", legal_name="Another", ledger={"code": "QS1"}),
        headers=headers(),
    )
    assert clash.status_code == 422, clash.text
    assert "ledger.code" in clash.json()["error"]["fields"]
    # the party, its role, the ledger and every audit row of the failed attempt are gone
    assert await listing(client, "parties") == parties
    assert await listing(client, "party-roles") == roles
    assert await counts(app) == before
    # the defaulted code (the party's own) clashes the same way
    again = await client.post(
        URL, json=body(code="QS1", name="Third", legal_name="Third", ledger={}), headers=headers()
    )
    assert again.status_code in {409, 422}, again.text
    assert await listing(client, "parties") == parties


async def test_a_defaulted_code_that_another_account_uses_is_refused_too(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    await post(
        client,
        "/accounts",
        {"code": "QS3", "name": "Taken", "group_id": groups["INDIRECT_EXPENSES"]},
    )
    before = await counts(app)
    # The party's own code is the ledger's default, so it is checked even when `ledger` is absent.
    for choices in LEDGER_CHOICES:
        request = body(code="QS3", name="Third", legal_name="Third", **choices)
        clash = await client.post(URL, json=request, headers=headers())
        assert clash.status_code == 422, clash.text
        assert "ledger.code" in clash.json()["error"]["fields"]
    assert await listing(client, "parties") == []
    assert await counts(app) == before


@pytest.mark.parametrize("choices", LEDGER_CHOICES)
async def test_replay_with_the_same_key_creates_one_party_and_one_ledger(
    client: httpx.AsyncClient, choices: dict[str, Any]
) -> None:
    await prepare(client)
    h = headers()
    first = await client.post(URL, json=body(**choices), headers=h)
    again = await client.post(URL, json=body(**choices), headers=h)
    assert first.status_code == again.status_code == 201, (first.text, again.text)
    assert again.json() == first.json() and again.headers["Idempotency-Replayed"] == "true"
    assert len(await listing(client, "parties")) == 1
    assert len(await accounts_of(client, first.json()["id"])) == 1
    # the same key with a changed ledger is a conflict of content, not a second ledger
    changed = await client.post(URL, json=body(ledger={"name": "Different"}), headers=h)
    assert changed.status_code == 422
    assert len(await accounts_of(client, first.json()["id"])) == 1


async def test_a_new_key_for_the_same_party_does_not_create_a_second_party(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    assert (await client.post(URL, json=body(ledger={}), headers=headers())).status_code == 201
    second = await client.post(URL, json=body(ledger={}), headers=headers())
    assert second.status_code in {409, 422}
    assert len(await listing(client, "parties")) == 1


async def test_without_ledger_manage_nothing_is_created(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    # The ledger is part of every creation, so its permissions are too: leaving `ledger` out of
    # the body does not let a caller who may not manage accounts create an account-less party.
    for missing in ("accounting.account.manage", "accounting.account.read"):
        for choices in LEDGER_CHOICES:
            refused = await client.post(
                URL,
                json=body(**choices),
                headers=headers(permissions=PERMISSIONS - {missing}),
            )
            assert refused.status_code == 403, (missing, choices, refused.text)
    assert await listing(client, "parties") == []
    assert await counts(app) == before


async def test_authentication_and_company_scope_still_apply(client: httpx.AsyncClient) -> None:
    await prepare(client)
    assert (await client.post(URL, json=body(ledger={}))).status_code == 401
    # an actor whose grants are for this company, acting under another company's context
    other = uuid7()
    foreign, mine = headers(company=other), headers()
    foreign["X-Actor-Context"], foreign["X-Actor-Signature"] = (
        mine["X-Actor-Context"],
        mine["X-Actor-Signature"],
    )
    refused = await client.post(
        f"/v1/companies/{other}/parties/create-with-details", json=body(ledger={}), headers=foreign
    )
    assert refused.status_code == 403, refused.text
    assert await listing(client, "parties") == []


async def test_another_tenant_cannot_see_the_new_ledger(client: httpx.AsyncClient) -> None:
    await prepare(client)
    created = await client.post(URL, json=body(ledger={}), headers=headers())
    [ledger] = await accounts_of(client, created.json()["id"])
    outsider = headers(tenant=uuid7())
    assert (
        await client.get(BASE + "/accounts/" + ledger["id"], headers=outsider)
    ).status_code == 404
    assert (
        await client.get(
            BASE + "/accounts", headers=outsider, params={"party_id": created.json()["id"]}
        )
    ).json()["items"] == []


async def test_the_response_is_still_the_party_and_nothing_more(client: httpx.AsyncClient) -> None:
    await prepare(client)
    with_ledger = await client.post(URL, json=body(ledger={}), headers=headers())
    without = await client.post(
        URL, json=body(code="QS9", name="Plain", legal_name="Plain"), headers=headers()
    )
    assert with_ledger.status_code == without.status_code == 201
    assert set(with_ledger.json()) == set(without.json())
    assert "ledger" not in with_ledger.json() and "ledger" not in without.json()
    assert with_ledger.headers["Location"].startswith("../parties/")
    # leaving `ledger` out is not leaving the ledger out: each party has its account
    assert len(await accounts_of(client, with_ledger.json()["id"])) == 1
    [plain] = await accounts_of(client, without.json()["id"])
    assert (plain["code"], plain["name"], plain["status"]) == ("QS9", "Plain", "ACTIVE")


async def test_foreign_currency_ledgers_follow_the_company_currency_rules(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    missing = await client.post(
        URL, json=body(ledger={"currency_mode": "FIXED"}), headers=headers()
    )
    assert (
        missing.status_code == 422 and "ledger.currency" in missing.json()["error"]["fields"]
    ), missing.text
    stray = await client.post(URL, json=body(ledger={"currency": "USD"}), headers=headers())
    assert (
        stray.status_code == 422 and "ledger.currency" in stray.json()["error"]["fields"]
    ), stray.text
    disabled = await client.post(
        URL, json=body(ledger={"currency_mode": "FIXED", "currency": "USD"}), headers=headers()
    )
    assert disabled.status_code == 409, disabled.text
    assert await listing(client, "parties") == []
    enabled = headers(features={"multi_currency"}, allowed_currencies={"USD"})
    created = await client.post(
        URL, json=body(ledger={"currency_mode": "FIXED", "currency": "USD"}), headers=enabled
    )
    assert created.status_code == 201, created.text
    [ledger] = await accounts_of(client, created.json()["id"])
    assert (ledger["currency_mode"], ledger["currency"]) == ("FIXED", "USD")


@pytest.mark.parametrize(
    "extra", [{"kind": "BANK"}, {"party_id": str(uuid.uuid4())}, {"posting_policy": "SOURCE_ONLY"}]
)
async def test_a_ledger_cannot_carry_what_the_server_decides(
    client: httpx.AsyncClient, extra: dict[str, Any]
) -> None:
    await prepare(client)
    refused = await client.post(URL, json=body(ledger=extra), headers=headers())
    assert refused.status_code == 422, refused.text
    assert await listing(client, "parties") == []


async def test_the_command_audits_the_party_role_and_ledger_together(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    created = await client.post(URL, json=body(ledger={}), headers=headers())
    assert created.status_code == 201, created.text
    party = created.json()["id"]
    [ledger] = await accounts_of(client, party)
    [role] = (
        await client.get(BASE + "/party-roles", headers=headers(), params={"party_id": party})
    ).json()["items"]
    ours = [uuid.UUID(party), uuid.UUID(role["id"]), uuid.UUID(ledger["id"])]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = (
                await db.execute(
                    select(MasterRevision.entity_type, MasterRevision.action).where(
                        MasterRevision.object_id.in_(ours)
                    )
                )
            ).all()
    after = await counts(app)
    # party, role and ledger each create and activate, in the one transaction
    assert sorted(rows) == [
        ("account", "activate"),
        ("account", "create"),
        ("party", "activate"),
        ("party", "create"),
        ("party_role", "activate"),
        ("party_role", "create"),
    ]
    assert after["revisions"] - before["revisions"] == 6, rows
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = (
                await db.execute(
                    select(Outbox.aggregate_type, Outbox.event_type).where(
                        Outbox.aggregate_id.in_(ours)
                    )
                )
            ).all()
    assert sorted(event for _, event in events) == [
        "accounting.account.activate",
        "accounting.account.create",
        "accounting.party.activate",
        "accounting.party.create",
        "accounting.party_role.activate",
        "accounting.party_role.create",
    ]


async def add_role(client: httpx.AsyncClient, party_id: str, role: str) -> dict[str, Any]:
    return await post(client, "/party-roles", {"party_id": party_id, "role": role})


async def test_activating_a_further_role_creates_its_account_beside_the_first(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    owner = await new_party(client, code="QS5", role="SUPPLIER")
    role = await add_role(client, owner["id"], "CUSTOMER")
    # a draft role has no account yet
    assert [row["party_role"] for row in await accounts_of(client, owner["id"])] == ["SUPPLIER"]
    h = headers()
    path = BASE + "/party-roles/" + role["id"] + "/activate"
    activated = await client.post(path, json={"expected_version": role["row_version"]}, headers=h)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    ledgers = {row["party_role"]: row for row in await accounts_of(client, owner["id"])}
    # the party's own code is taken by its first account, so the newcomer is told apart by role
    assert (ledgers["SUPPLIER"]["code"], ledgers["SUPPLIER"]["name"]) == ("QS5", "QS5 Traders")
    customer = ledgers["CUSTOMER"]
    assert (customer["code"], customer["name"]) == ("QS5-CUST", "QS5 Traders (Customer)")
    assert customer["status"] == "ACTIVE" and customer["group_id"] == groups["DEBTORS"]
    # the same key replays the activation without a third account
    again = await client.post(path, json={"expected_version": role["row_version"]}, headers=h)
    assert again.status_code == 200 and again.json() == activated.json()
    assert len(await accounts_of(client, owner["id"])) == 2


async def test_choices_on_a_role_activation_name_its_account(client: httpx.AsyncClient) -> None:
    await prepare(client)
    owner = await new_party(client, code="QS6", role="CUSTOMER")
    role = await add_role(client, owner["id"], "SUPPLIER")
    await post(
        client,
        "/party-roles/" + role["id"] + "/activate",
        {
            "expected_version": role["row_version"],
            "ledger": {"code": "QS6-PAY", "name": "QS6 payable"},
        },
        status=200,
    )
    ledgers = {row["party_role"]: row for row in await accounts_of(client, owner["id"])}
    assert (ledgers["SUPPLIER"]["code"], ledgers["SUPPLIER"]["name"]) == ("QS6-PAY", "QS6 payable")
    assert ledgers["CUSTOMER"]["code"] == "QS6"


async def test_an_other_role_and_a_broker_role_of_one_party_share_one_account(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    owner = await new_party(client, code="QS7", role="OTHER")
    role = await add_role(client, owner["id"], "BROKER")
    activated = await post(
        client,
        "/party-roles/" + role["id"] + "/activate",
        {"expected_version": role["row_version"]},
        status=200,
    )
    assert activated["status"] == "ACTIVE"
    # both roles map to the OTHER account role, so the one account serves them both
    [ledger] = await accounts_of(client, owner["id"])
    assert (ledger["code"], ledger["party_role"], ledger["status"]) == ("QS7", "OTHER", "ACTIVE")


async def test_activating_a_role_uses_the_draft_account_the_party_already_has(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    owner = await new_party(client, code="QS8", role="SUPPLIER")
    role = await add_role(client, owner["id"], "CUSTOMER")
    draft = await post(
        client,
        "/accounts",
        {
            "code": "QS8-DEBTOR",
            "name": "QS8 receivable",
            "group_id": groups["DEBTORS"],
            "kind": "PARTY",
            "party_id": owner["id"],
            "party_role": "CUSTOMER",
        },
    )
    assert draft["status"] == "DRAFT"
    await post(
        client,
        "/party-roles/" + role["id"] + "/activate",
        {"expected_version": role["row_version"]},
        status=200,
    )
    ledgers = {row["party_role"]: row for row in await accounts_of(client, owner["id"])}
    assert len(ledgers) == 2
    assert (ledgers["CUSTOMER"]["id"], ledgers["CUSTOMER"]["status"]) == (draft["id"], "ACTIVE")


async def test_a_second_account_for_a_role_is_refused_even_as_a_draft(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    owner = await new_party(client, code="QS4", role="SUPPLIER")
    refused = await client.post(
        BASE + "/accounts",
        json={
            "code": "QS4-SECOND",
            "name": "QS4 second",
            "group_id": groups["CREDITORS"],
            "kind": "PARTY",
            "party_id": owner["id"],
            "party_role": "SUPPLIER",
        },
        headers=headers(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"] == "this party already has an account for this role"
    assert len(await accounts_of(client, owner["id"])) == 1
    # retiring the account frees the role for another
    [first] = await accounts_of(client, owner["id"])
    await post(
        client,
        "/accounts/" + first["id"] + "/deactivate",
        {"expected_version": first["row_version"]},
        status=200,
    )
    replacement = await post(
        client,
        "/accounts",
        {
            "code": "QS4-SECOND",
            "name": "QS4 second",
            "group_id": groups["CREDITORS"],
            "kind": "PARTY",
            "party_id": owner["id"],
            "party_role": "SUPPLIER",
        },
    )
    assert (await activate(client, "/accounts", replacement))["status"] == "ACTIVE"


async def test_a_refused_role_activation_leaves_the_role_a_draft(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    owner = await new_party(client, code="QS3", role="SUPPLIER")
    role = await add_role(client, owner["id"], "CUSTOMER")
    before = await counts(app)
    refused = await client.post(
        BASE + "/party-roles/" + role["id"] + "/activate",
        json={
            "expected_version": role["row_version"],
            # a customer account cannot sit under the creditors group
            "ledger": {"group_id": groups["CREDITORS"]},
        },
        headers=headers(),
    )
    assert refused.status_code == 422, refused.text
    assert "ledger.group_id" in refused.json()["error"]["fields"]
    [row] = [
        row
        for row in await listing(client, "party-roles")
        if row["party_id"] == owner["id"] and row["role"] == "CUSTOMER"
    ]
    assert row["status"] == "DRAFT"
    assert len(await accounts_of(client, owner["id"])) == 1
    assert await counts(app) == before


async def test_the_generic_import_refuses_a_party_create_row(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """A bare party can no longer be created through `/imports`: it must arrive with its account."""
    await prepare(client)
    before = await counts(app)
    request = {
        "items": [
            {
                "key": "party",
                "resource": "parties",
                "values": {
                    "code": "GEN1",
                    "name": "Generic",
                    "legal_name": "Generic",
                    "country_code": "IN",
                },
            }
        ]
    }
    preview = await post(client, "/imports/preview", request, status=200)
    assert preview["valid"] is False and preview["preview_token"] is None
    assert preview["issues"] == [{"key": "party", "code": "conflict"}]
    # No token exists for it, and one borrowed from another valid preview does not match.
    other = {
        "items": [
            {
                "key": "term",
                "resource": "payment-terms",
                "values": {"code": "NET15", "name": "Net 15"},
            }
        ]
    }
    token = (await post(client, "/imports/preview", other, status=200))["preview_token"]
    applied = await client.post(
        BASE + "/imports/apply", json=request | {"preview_token": token}, headers=headers()
    )
    assert applied.status_code == 409, applied.text
    assert await listing(client, "parties") == []
    assert await listing(client, "party-roles") == []
    assert await counts(app) == before


async def test_a_party_role_activate_row_in_the_generic_import_creates_the_account(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    owner = await new_party(client, code="GEN2", role="SUPPLIER")
    role = await add_role(client, owner["id"], "CUSTOMER")
    request = {
        "items": [
            {
                "key": "role",
                "resource": "party-roles",
                "action": "activate",
                "object_id": role["id"],
                "values": {"expected_version": role["row_version"]},
            }
        ]
    }
    preview = await post(client, "/imports/preview", request, status=200)
    assert preview["valid"] is True, preview
    # a preview changes nothing: the role is still a draft and the party has its one account
    assert len(await accounts_of(client, owner["id"])) == 1
    applied = await post(
        client,
        "/imports/apply",
        request | {"preview_token": preview["preview_token"]},
        status=200,
    )
    assert applied["records"] == {"role": role["id"]}
    ledgers = {row["party_role"]: row for row in await accounts_of(client, owner["id"])}
    assert set(ledgers) == {"SUPPLIER", "CUSTOMER"}
    customer = ledgers["CUSTOMER"]
    assert (customer["code"], customer["status"]) == ("GEN2-CUST", "ACTIVE")
    assert customer["group_id"] == groups["DEBTORS"]
    [row] = [
        row
        for row in await listing(client, "party-roles")
        if row["party_id"] == owner["id"] and row["role"] == "CUSTOMER"
    ]
    assert row["status"] == "ACTIVE"


@pytest.mark.parametrize("missing", ["accounting.account.manage", "accounting.account.read"])
async def test_the_generic_import_role_activation_needs_account_permissions(
    client: httpx.AsyncClient, missing: str
) -> None:
    await prepare(client)
    owner = await new_party(client, code="GEN3", role="SUPPLIER")
    role = await add_role(client, owner["id"], "CUSTOMER")
    request = {
        "items": [
            {
                "key": "role",
                "resource": "party-roles",
                "action": "activate",
                "object_id": role["id"],
                "values": {"expected_version": role["row_version"]},
            }
        ]
    }
    assert (await post(client, "/imports/preview", request, status=200))["valid"] is True
    # activating the role creates an account, so a caller who may not manage or read accounts
    # gets no acceptable preview (no token to apply), however the refusal is reported
    refused = await client.post(
        BASE + "/imports/preview",
        json=request,
        headers=headers(permissions=PERMISSIONS - {missing}),
    )
    assert refused.status_code in {200, 403}, refused.text
    if refused.status_code == 200:
        assert refused.json()["valid"] is False, refused.text
        assert refused.json()["preview_token"] is None
    assert len(await accounts_of(client, owner["id"])) == 1


async def test_a_broker_role_retires_while_the_other_role_stands_on_the_account(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    owner = await new_party(client, code="QB1", role="OTHER")
    broker = await add_role(client, owner["id"], "BROKER")
    broker = await post(
        client,
        "/party-roles/" + broker["id"] + "/activate",
        {"expected_version": broker["row_version"]},
        status=200,
    )
    retired = await post(
        client,
        "/party-roles/" + broker["id"] + "/deactivate",
        {"expected_version": broker["row_version"]},
        status=200,
    )
    assert retired["status"] == "INACTIVE"
    # the shared account stays active: the "other" role still stands on it
    [ledger] = await accounts_of(client, owner["id"])
    assert (ledger["party_role"], ledger["status"]) == ("OTHER", "ACTIVE")
    # and now that role is the last one on it, so it cannot go while the account is live
    [other] = [
        row
        for row in await listing(client, "party-roles")
        if row["party_id"] == owner["id"] and row["role"] == "OTHER"
    ]
    refused = await client.post(
        BASE + "/party-roles/" + other["id"] + "/deactivate",
        json={"expected_version": other["row_version"]},
        headers=headers(),
    )
    assert refused.status_code == 409, refused.text
    assert (
        refused.json()["error"]["message"] == "dependent masters must be retired or replaced first"
    )


async def test_the_last_broker_role_on_an_account_cannot_retire_while_it_is_live(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    owner = await new_party(client, code="QB2", role="BROKER")
    [role] = [
        row
        for row in await listing(client, "party-roles")
        if row["party_id"] == owner["id"] and row["role"] == "BROKER"
    ]
    refused = await client.post(
        BASE + "/party-roles/" + role["id"] + "/deactivate",
        json={"expected_version": role["row_version"]},
        headers=headers(),
    )
    assert refused.status_code == 409, refused.text
    # retiring the account first frees the role
    [ledger] = await accounts_of(client, owner["id"])
    assert ledger["party_role"] == "OTHER"
    await post(
        client,
        "/accounts/" + ledger["id"] + "/deactivate",
        {"expected_version": ledger["row_version"]},
        status=200,
    )
    retired = await post(
        client,
        "/party-roles/" + role["id"] + "/deactivate",
        {"expected_version": role["row_version"]},
        status=200,
    )
    assert retired["status"] == "INACTIVE"

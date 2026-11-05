"""Every party role has exactly one active party account, created in the transaction that
activates the role (docs/party-ledger-mandatory-plan.md, PL-INV).

These tests cover the rule itself: creating a party, activating a further role, the
one-account-per-role guard on the account routes, and the import routes. The repair command for
data written before the rule held is covered in `test_party_ledger_repair.py`, which reuses the
legacy-state helpers defined here (rows inserted through the app's own session, never through
the routes that now refuse them).
"""

import base64
import json
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest
from billing_platform.bulk import BulkRecord
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from billing_platform.import_contracts import CONTROLS
from billing_platform.import_files import document
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.api.auth import Access
from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from accounting.tasks.master_imports import AccountingImportAdapter
from tests.conftest import COMPANY, PERMISSIONS, SECRET, TENANT, USER, headers
from tests.test_fiscal_api import finance_headers, fiscal_setup
from tests.test_masters import prepare

OTHER_TENANT = uuid7()
OTHER_COMPANY = uuid7()
DUPLICATE = "this party already has an account for this role"
AUDITED = ["accounting.party", "accounting.party_role", "accounting.account"]


def base(company: uuid.UUID = COMPANY) -> str:
    return f"/v1/companies/{company}"


BASE = base()
URL = BASE + "/parties/create-with-details"
# the account role a party role is kept under, and the standard group it defaults to
ACCOUNT_ROLE = {"CUSTOMER": "CUSTOMER", "SUPPLIER": "SUPPLIER", "BROKER": "OTHER", "OTHER": "OTHER"}
STANDARD_GROUP = {
    "CUSTOMER": "group.DEBTORS",
    "SUPPLIER": "group.CREDITORS",
    "BROKER": "group.CREDITORS",
    "OTHER": "group.CREDITORS",
}


def other_headers(**extra: Any) -> dict[str, str]:
    """A second tenant acting in its own company; every call carries a fresh idempotency key."""
    return headers(tenant=OTHER_TENANT, company=OTHER_COMPANY, **extra)


def body(code: str = "ABC", role: str | None = "SUPPLIER", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "name": f"{code} Traders",
        "legal_name": f"{code} Traders Limited",
        "country_code": "IN",
    }
    if role is not None:
        result["role"] = role
    return result | extra


async def create(
    client: httpx.AsyncClient,
    code: str = "ABC",
    role: str = "SUPPLIER",
    *,
    h: dict[str, str] | None = None,
    company: uuid.UUID = COMPANY,
    **extra: Any,
) -> dict[str, Any]:
    """A party created through the only route that creates one."""
    created = await client.post(
        base(company) + "/parties/create-with-details",
        json=body(code, role, **extra),
        headers=h or headers(),
    )
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


async def accounts_of(
    client: httpx.AsyncClient,
    party_id: str,
    *,
    h: dict[str, str] | None = None,
    company: uuid.UUID = COMPANY,
) -> list[dict[str, Any]]:
    """Full detail of every account of the party, in code order (lists are lean projections)."""
    authority = h or headers()
    page = await client.get(
        base(company) + "/accounts",
        headers=authority,
        params={"party_id": party_id, "sort": "code", "limit": 200},
    )
    assert page.status_code == 200, page.text
    details = []
    for item in page.json()["items"]:
        got = await client.get(base(company) + "/accounts/" + item["id"], headers=authority)
        assert got.status_code == 200, got.text
        details.append(got.json())
    return details


async def roles_of(client: httpx.AsyncClient, party_id: str) -> list[dict[str, Any]]:
    page = await client.get(BASE + "/party-roles", headers=headers(), params={"party_id": party_id})
    assert page.status_code == 200, page.text
    items: list[dict[str, Any]] = page.json()["items"]
    return items


async def add_role(
    client: httpx.AsyncClient, party_id: str, role: str, *, h: dict[str, str] | None = None
) -> dict[str, Any]:
    """A further role in DRAFT, the way a user adds one before activating it."""
    added = await client.post(
        BASE + "/party-roles", json={"party_id": party_id, "role": role}, headers=h or headers()
    )
    assert added.status_code == 201, added.text
    assert added.json()["status"] == "DRAFT"
    result: dict[str, Any] = added.json()
    return result


async def activate_role(
    client: httpx.AsyncClient,
    role: dict[str, Any],
    ledger: dict[str, Any] | None = None,
    *,
    h: dict[str, str] | None = None,
) -> httpx.Response:
    request: dict[str, Any] = {"expected_version": role["row_version"]}
    if ledger is not None:
        request["ledger"] = ledger
    return await client.post(
        BASE + "/party-roles/" + role["id"] + "/activate", json=request, headers=h or headers()
    )


async def role_status(client: httpx.AsyncClient, role: dict[str, Any]) -> tuple[str, int]:
    got = await client.get(BASE + "/party-roles/" + role["id"], headers=headers())
    assert got.status_code == 200, got.text
    return got.json()["status"], got.json()["row_version"]


async def counts(app: FastAPI, *, tenant: uuid.UUID = TENANT) -> dict[str, int]:
    """What a refused or replayed command must leave exactly as it found it."""
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            result = {
                "parties": await db.scalar(select(func.count(m.Party.id))) or 0,
                "roles": await db.scalar(select(func.count(m.PartyRole.id))) or 0,
                "accounts": await db.scalar(select(func.count(m.Account.id))) or 0,
                "revisions": await db.scalar(
                    select(func.count(MasterRevision.id)).where(
                        MasterRevision.entity_type.in_(["party", "party_role", "account"])
                    )
                )
                or 0,
            }
            # the party, role and account audit events; other events (reporting captures that
            # follow any account write, import job lifecycle) are noise for these assertions
            result["events"] = (
                await db.scalar(
                    select(func.count())
                    .select_from(Outbox)
                    .where(Outbox.tenant_id == tenant, Outbox.aggregate_type.in_(AUDITED))
                )
                or 0
            )
    return result


async def outbox_total(app: FastAPI, *, tenant: uuid.UUID = TENANT) -> int:
    """Every Accounting outbox event of the tenant, for commands that must leave none at all."""
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            total = await db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.tenant_id == tenant, Outbox.aggregate_type.like("accounting.%"))
            )
    return total or 0


async def standard_groups(
    app: FastAPI, *, tenant: uuid.UUID = TENANT, company: uuid.UUID = COMPANY
) -> dict[str, uuid.UUID]:
    """The company's Sundry Debtors/Creditors groups, by system key."""
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            rows = (
                await db.execute(
                    select(m.AccountGroup.system_key, m.AccountGroup.id).where(
                        m.AccountGroup.company_id == company,
                        m.AccountGroup.system_key.in_(["group.DEBTORS", "group.CREDITORS"]),
                    )
                )
            ).all()
    return {key: group for key, group in rows if key is not None}


async def retire_group(app: FastAPI, group_id: uuid.UUID) -> None:
    """System groups cannot be retired through the API, so make one unavailable directly."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            group = await db.get(m.AccountGroup, group_id)
            assert group is not None
            group.status = "INACTIVE"


async def legacy_party(
    app: FastAPI,
    code: str,
    roles: Sequence[tuple[str, str]] = (("CUSTOMER", "ACTIVE"),),
    *,
    status: str = "ACTIVE",
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """A party and its roles as data written before the rule held them: no account.

    Rows go in through the app's own session, in the order given, so role ids follow it.
    """
    party_id = uuid7()
    role_ids: dict[str, uuid.UUID] = {}
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                m.Party(
                    id=party_id,
                    tenant_id=tenant,
                    company_id=company,
                    code=code,
                    name=f"{code} Traders",
                    legal_name=f"{code} Traders Limited",
                    party_type="ORGANISATION",
                    country_code="IN",
                    status=status,
                    row_version=1,
                )
            )
            await db.flush()
            for role, role_state in roles:
                role_id = uuid7()
                db.add(
                    m.PartyRole(
                        id=role_id,
                        tenant_id=tenant,
                        company_id=company,
                        party_id=party_id,
                        role=role,
                        status=role_state,
                        row_version=1,
                    )
                )
                await db.flush()
                role_ids[role] = role_id
    return party_id, role_ids


async def legacy_account(
    app: FastAPI,
    *,
    code: str,
    group_id: uuid.UUID,
    party_id: uuid.UUID | None = None,
    role: str | None = None,
    status: str = "ACTIVE",
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
) -> uuid.UUID:
    """An account inserted directly: a party account (`party_id`, account `role`) or a plain one."""
    account_id = uuid7()
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                m.Account(
                    id=account_id,
                    tenant_id=tenant,
                    company_id=company,
                    code=code,
                    name=f"Legacy {code}",
                    group_id=group_id,
                    kind="GENERAL" if party_id is None else "PARTY",
                    party_id=party_id,
                    party_role=role,
                    currency_mode="BASE",
                    posting_policy="MANUAL_ALLOWED",
                    status=status,
                    row_version=1,
                )
            )
    return account_id


async def prepare_company(client: httpx.AsyncClient, tenant: uuid.UUID, company: uuid.UUID) -> None:
    """Initialize and install the standard chart for a company other than the default one."""
    for step, request in (
        ("initialize", {}),
        ("install", {"business_accounts": True}),
    ):
        done = await client.post(
            base(company) + "/accounting-setup/" + step,
            json=request,
            headers=headers(tenant=tenant, company=company),
        )
        assert done.status_code == 200, done.text


def actor_access(h: dict[str, str]) -> Access:
    """The `Access` the gateway headers resolve to, for calling the import adapter directly."""
    secret = SECRET.encode()
    actor = decode_actor_context(h["X-Actor-Context"], h["X-Actor-Signature"], secret)
    context = verify_company_context(h["X-Company-Context"], h["X-Company-Signature"], secret)
    return Access(actor, context)


def assert_party_account(
    account: dict[str, Any],
    party: dict[str, Any],
    role: str,
    groups: dict[str, uuid.UUID],
    *,
    code: str | None = None,
    name: str | None = None,
) -> None:
    """The account is an ACTIVE PARTY account of the party, in the role's account role and group."""
    assert account["kind"] == "PARTY" and account["status"] == "ACTIVE"
    assert account["party_id"] == party["id"]
    assert account["party_role"] == ACCOUNT_ROLE[role]
    assert account["group_id"] == str(groups[STANDARD_GROUP[role]])
    assert account["code"] == (code or party["code"])
    assert account["name"] == (name or party["name"])
    assert account["currency_mode"] == "BASE" and account.get("currency") is None
    assert account["posting_policy"] == "MANUAL_ALLOWED"


# --- creating a party ------------------------------------------------------------------------


async def test_a_party_cannot_be_created_without_a_valid_role(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    for role in (None, "", "customer", "VENDOR", "CUSTOMER,SUPPLIER"):
        refused = await client.post(URL, json=body("NOROLE", role), headers=headers())
        assert refused.status_code == 422, (role, refused.text)
        assert refused.json()["error"]["code"] == "validation_failed"
    # a null role is not the same as a missing one
    null = await client.post(URL, json=body("NOROLE", None) | {"role": None}, headers=headers())
    assert null.status_code == 422, null.text
    assert await counts(app) == before
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []


@pytest.mark.parametrize("role", ["CUSTOMER", "SUPPLIER", "BROKER", "OTHER"])
async def test_each_role_creates_exactly_one_active_party_account(
    client: httpx.AsyncClient, app: FastAPI, role: str
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party = await create(client, "ABC", role)
    assert party["status"] == "ACTIVE"
    [only] = await roles_of(client, party["id"])
    assert (only["role"], only["status"]) == (role, "ACTIVE")
    [account] = await accounts_of(client, party["id"])
    assert_party_account(account, party, role, groups)
    # nothing else of this party's is a ledger account: the party alone owns this one
    everything = await client.get(
        BASE + "/accounts", headers=headers(), params={"kind": "PARTY", "limit": 200}
    )
    assert [row["id"] for row in everything.json()["items"]] == [account["id"]]


async def test_ledger_choices_are_honoured(client: httpx.AsyncClient, app: FastAPI) -> None:
    groups = await prepare(client)
    named = await create(client, "N1", "SUPPLIER", ledger={"code": "N1-PAY", "name": "N1 payable"})
    [account] = await accounts_of(client, named["id"])
    assert (account["code"], account["name"]) == ("N1-PAY", "N1 payable")
    assert account["group_id"] == str((await standard_groups(app))["group.CREDITORS"])
    grouped = await create(
        client, "G1", "SUPPLIER", ledger={"group_id": groups["CURRENT_LIABILITIES"]}
    )
    [account] = await accounts_of(client, grouped["id"])
    assert account["group_id"] == groups["CURRENT_LIABILITIES"]

    def enabled() -> dict[str, str]:
        return headers(features={"multi_currency"}, allowed_currencies={"USD"})

    for code, mode, currency in (("F1", "FIXED", "USD"), ("M1", "MULTI", None)):
        choice: dict[str, Any] = {"currency_mode": mode}
        if currency:
            choice["currency"] = currency
        foreign = await create(client, code, "CUSTOMER", h=enabled(), ledger=choice)
        [account] = await accounts_of(client, foreign["id"], h=enabled())
        assert account["currency_mode"] == mode and account.get("currency") == currency
        assert account["party_role"] == "CUSTOMER" and account["status"] == "ACTIVE"


async def test_bad_ledger_choices_are_reported_together_and_create_nothing(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    await create(client, "TAKEN", "CUSTOMER")
    before = await counts(app)
    # three independent mistakes, all named in one answer
    refused = await client.post(
        URL,
        json=body(
            "NEW",
            "CUSTOMER",
            ledger={"code": "TAKEN", "group_id": str(uuid7()), "currency_mode": "FIXED"},
        ),
        headers=headers(),
    )
    assert refused.status_code == 422, refused.text
    assert {"ledger.code", "ledger.group_id", "ledger.currency"} <= set(
        refused.json()["error"]["fields"]
    )
    # one at a time: each names its own `ledger.<field>`
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("NEW2", {"currency": "USD"}, "ledger.currency"),
        ("NEW2", {"currency_mode": "MULTI", "currency": "USD"}, "ledger.currency"),
        ("NEW2", {"group_id": groups["DEBTORS"]}, "ledger.group_id"),  # debtors for a supplier
        ("NEW2", {"group_id": groups["INDIRECT_EXPENSES"]}, "ledger.group_id"),
        ("NEW2", {"code": "TAKEN"}, "ledger.code"),
        # the party's own code is the default, and the first party's account already uses it
        ("TAKEN", {"name": "Other name"}, "ledger.code"),
    ]
    for code, ledger, field in cases:
        sent = await client.post(URL, json=body(code, "SUPPLIER", ledger=ledger), headers=headers())
        assert sent.status_code == 422, (ledger, sent.text)
        assert field in sent.json()["error"]["fields"], (ledger, sent.text)
    # an inactive group is refused by name too
    await retire_group(app, (await standard_groups(app))["group.CREDITORS"])
    inactive = await client.post(URL, json=body("NEW3", "SUPPLIER", ledger={}), headers=headers())
    assert inactive.status_code == 422, inactive.text
    assert "ledger.group_id" in inactive.json()["error"]["fields"]
    # the party, its role and its account are all absent after every refusal
    assert await counts(app) == before
    page = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    assert [item["code"] for item in page] == ["TAKEN"]


@pytest.mark.parametrize(
    "extra",
    [
        {"kind": "BANK"},
        {"party_id": str(uuid.uuid4())},
        {"party_role": "CUSTOMER"},
        {"posting_policy": "SOURCE_ONLY"},
        {"status": "DRAFT"},
    ],
)
async def test_a_ledger_cannot_carry_what_the_server_decides(
    client: httpx.AsyncClient, app: FastAPI, extra: dict[str, Any]
) -> None:
    await prepare(client)
    before = await counts(app)
    refused = await client.post(URL, json=body(ledger=extra), headers=headers())
    assert refused.status_code == 422, refused.text
    assert await counts(app) == before


async def test_a_refused_ledger_rolls_the_whole_command_back(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    outbox_before = await outbox_total(app)

    def refuse_name_write() -> dict[str, str]:
        return headers(
            policies=[
                {
                    "entity_type": "accounting.account",
                    "field_key": "name",
                    "access": "write",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                    "condition": None,
                }
            ]
        )

    invalid_tax = {
        "scheme": "GST_IN",
        "country_code": "IN",
        "state_code": "IN-MH",
        "registration_number": "INVALID",
        "valid_from": "2026-01-01",
    }
    attempts: list[tuple[dict[str, Any], dict[str, str], int]] = [
        # refused by the account rules after the party and its role were created in the transaction
        (
            body("RB1", "SUPPLIER", ledger={"currency_mode": "FIXED", "currency": "USD"}),
            headers(),
            409,
        ),
        # refused by a field policy on the account, after the party and role
        (body("RB2", "CUSTOMER"), refuse_name_write(), 403),
        # refused by a later section, after the account was created
        (body("RB3", "SUPPLIER", tax_registration=invalid_tax), headers(), 422),
    ]
    for request, authority, status in attempts:
        refused = await client.post(URL, json=request, headers=authority)
        assert refused.status_code == status, (request["code"], refused.text)
        # no party, role, account, revision or outbox event of the failed attempt survives
        assert await counts(app) == before, request["code"]
        assert await outbox_total(app) == outbox_before, request["code"]
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    assert (await client.get(BASE + "/party-roles", headers=headers())).json()["items"] == []
    kinds = await client.get(BASE + "/accounts", headers=headers(), params={"kind": "PARTY"})
    assert kinds.json()["items"] == []


async def test_the_command_audits_the_party_role_and_account_together(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    party = await create(client, "AUD", "CUSTOMER")
    [role] = await roles_of(client, party["id"])
    [account] = await accounts_of(client, party["id"])
    ours = [uuid.UUID(party["id"]), uuid.UUID(role["id"]), uuid.UUID(account["id"])]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revisions = (
                await db.execute(
                    select(MasterRevision.entity_type, MasterRevision.action).where(
                        MasterRevision.object_id.in_(ours)
                    )
                )
            ).all()
            events = list(await db.scalars(select(Outbox).where(Outbox.aggregate_id.in_(ours))))
    # party, role and account each create and activate, in the one transaction
    expected = [
        ("account", "activate"),
        ("account", "create"),
        ("party", "activate"),
        ("party", "create"),
        ("party_role", "activate"),
        ("party_role", "create"),
    ]
    assert sorted((entity, action) for entity, action in revisions) == expected
    assert sorted(event.event_type for event in events) == [
        f"accounting.{entity}.{action}" for entity, action in expected
    ]
    after = await counts(app)
    assert after["revisions"] - before["revisions"] == 6
    assert after["events"] - before["events"] == 6
    # the account events name the acting user and the company
    for event in (e for e in events if e.aggregate_type == "accounting.account"):
        assert event.tenant_id == TENANT
        assert event.payload["actor_user_id"] == str(USER)
        assert event.payload["company_id"] == str(COMPANY)
        assert event.payload["entity_id"] == account["id"]


async def test_replay_with_the_same_key_creates_one_party_and_one_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    h = headers()
    first = await client.post(URL, json=body("REP", "SUPPLIER"), headers=h)
    assert first.status_code == 201, first.text
    after_first = await counts(app)
    again = await client.post(URL, json=body("REP", "SUPPLIER"), headers=h)
    assert again.status_code == 201, again.text
    assert again.json() == first.json() and again.headers["Idempotency-Replayed"] == "true"
    # a replay is one effect: no row and no audit event beyond the first call's
    assert await counts(app) == after_first
    assert len(await accounts_of(client, first.json()["id"])) == 1
    # the same key with different content is refused, not a second ledger
    changed = await client.post(
        URL, json=body("REP", "SUPPLIER", ledger={"name": "Other"}), headers=h
    )
    assert changed.status_code == 422, changed.text
    assert await counts(app) == after_first
    # a new key for the same party is a conflict, not a second party or account
    second = await client.post(URL, json=body("REP", "SUPPLIER"), headers=headers())
    assert second.status_code in {409, 422}, second.text
    assert await counts(app) == after_first


async def test_creating_a_party_needs_authentication_and_the_right_permissions(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    before = await counts(app)
    assert (await client.post(URL, json=body("AUTH", "SUPPLIER"))).status_code == 401
    for missing in (
        "accounting.account.manage",
        "accounting.account.read",
        "accounting.party.manage",
        "accounting.party.read",
    ):
        refused = await client.post(
            URL, json=body("AUTH", "SUPPLIER"), headers=headers(permissions=PERMISSIONS - {missing})
        )
        assert refused.status_code == 403, (missing, refused.text)
    # an actor granted this company acting under another company's context
    other = uuid7()
    foreign, mine = headers(company=other), headers()
    foreign["X-Actor-Context"], foreign["X-Actor-Signature"] = (
        mine["X-Actor-Context"],
        mine["X-Actor-Signature"],
    )
    refused = await client.post(
        base(other) + "/parties/create-with-details", json=body("AUTH", "SUPPLIER"), headers=foreign
    )
    assert refused.status_code == 403, refused.text
    # another tenant cannot create into this company
    outsider = await client.post(
        URL, json=body("AUTH", "SUPPLIER"), headers=headers(tenant=uuid7())
    )
    assert outsider.status_code >= 400, outsider.text
    assert await counts(app) == before


async def test_the_plain_party_create_is_gone_while_the_other_party_routes_remain(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    # the route does not exist, and the contract says so too
    plain = await client.post(BASE + "/parties", json=body("PLAIN", None), headers=headers())
    assert plain.status_code in {404, 405}, plain.text
    paths = app.openapi()["paths"]
    assert "post" not in paths["/v1/companies/{company_id}/parties"]
    assert "get" in paths["/v1/companies/{company_id}/parties"]
    assert "post" in paths["/v1/companies/{company_id}/parties/create-with-details"]
    assert "post" in paths["/v1/companies/{company_id}/parties/ledger-repair"]
    schema = app.openapi()["components"]["schemas"]["PartyCreation"]
    assert "role" in schema["required"]
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    # read, edit, activate and deactivate stay: shown on a party written before the rule
    party_id, _ = await legacy_party(app, "OLD", (), status="DRAFT")
    got = await client.get(BASE + f"/parties/{party_id}", headers=headers())
    assert got.status_code == 200 and got.json()["status"] == "DRAFT"
    edited = await client.patch(
        BASE + f"/parties/{party_id}",
        json={"expected_version": got.json()["row_version"], "name": "Old Traders Renamed"},
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    activated = await client.post(
        BASE + f"/parties/{party_id}/activate",
        json={"expected_version": edited.json()["row_version"]},
        headers=headers(),
    )
    assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE", activated.text
    deactivated = await client.post(
        BASE + f"/parties/{party_id}/deactivate",
        json={"expected_version": activated.json()["row_version"]},
        headers=headers(),
    )
    assert deactivated.status_code == 200, deactivated.text
    assert (
        deactivated.json()["status"] == "INACTIVE"
        and deactivated.json()["name"] == "Old Traders Renamed"
    )
    # editing a party that has its role and account works the same
    live = await create(client, "LIVE", "CUSTOMER")
    renamed = await client.patch(
        BASE + f"/parties/{live['id']}",
        json={"expected_version": live["row_version"], "notes": "kept"},
        headers=headers(),
    )
    assert renamed.status_code == 200, renamed.text


# --- activating a further role -----------------------------------------------------------------


async def test_activating_a_role_creates_its_account_and_tells_it_apart_by_role(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party = await create(client, "ABC", "CUSTOMER")
    supplier = await add_role(client, party["id"], "SUPPLIER")
    # a role that is only drafted has no account yet
    assert len(await accounts_of(client, party["id"])) == 1
    before = await counts(app)
    activated = await activate_role(client, supplier)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE" and activated.json()["role"] == "SUPPLIER"
    customer_account, supplier_account = await accounts_of(client, party["id"])
    assert customer_account["code"] == "ABC" and customer_account["party_role"] == "CUSTOMER"
    # the party's own code is taken by its first account: the newcomer is told apart by role
    assert_party_account(
        supplier_account, party, "SUPPLIER", groups, code="ABC-SUPP", name="ABC Traders (Supplier)"
    )
    after = await counts(app)
    # role activation, account create and account activate: three revisions and three events
    assert after["accounts"] == before["accounts"] + 1
    assert after["revisions"] == before["revisions"] + 3
    assert after["events"] == before["events"] + 3
    # a third role, "other", is told apart the same way and lands in the OTHER account role
    plain = await add_role(client, party["id"], "OTHER")
    assert (await activate_role(client, plain)).status_code == 200
    accounts = await accounts_of(client, party["id"])
    assert [a["code"] for a in accounts] == ["ABC", "ABC-OTHR", "ABC-SUPP"]
    assert_party_account(
        accounts[1], party, "OTHER", groups, code="ABC-OTHR", name="ABC Traders (Other)"
    )


async def test_a_broker_role_is_activated_with_its_account_in_the_other_account_role(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party = await create(client, "ABC", "CUSTOMER")
    broker = await add_role(client, party["id"], "BROKER")
    activated = await activate_role(client, broker)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE" and activated.json()["role"] == "BROKER"
    accounts = await accounts_of(client, party["id"])
    assert [a["code"] for a in accounts] == ["ABC", "ABC-OTHR"]
    # the account table has no BROKER role: the account is an OTHER account, labelled as a broker's
    assert_party_account(
        accounts[1], party, "BROKER", groups, code="ABC-OTHR", name="ABC Traders (Broker)"
    )
    # and "other" then shares the broker's account instead of taking a third
    plain = await add_role(client, party["id"], "OTHER")
    assert (await activate_role(client, plain)).status_code == 200
    assert await accounts_of(client, party["id"]) == accounts


async def test_a_free_default_code_is_used_and_choices_are_honoured_on_activation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    party = await create(client, "ABC", "CUSTOMER", ledger={"code": "ABC-DR"})
    supplier = await add_role(client, party["id"], "SUPPLIER")
    assert (await activate_role(client, supplier)).status_code == 200
    accounts = await accounts_of(client, party["id"])
    # the party's own code is free, so no suffix and no role label
    free = next(a for a in accounts if a["party_role"] == "SUPPLIER")
    assert (free["code"], free["name"]) == ("ABC", "ABC Traders")
    plain = await add_role(client, party["id"], "OTHER")
    chosen = await activate_role(
        client,
        plain,
        {
            "code": "ABC-OTH",
            "name": "ABC other account",
            "group_id": groups["CURRENT_LIABILITIES"],
        },
    )
    assert chosen.status_code == 200, chosen.text
    accounts = await accounts_of(client, party["id"])
    picked = next(a for a in accounts if a["code"] == "ABC-OTH")
    assert picked["name"] == "ABC other account" and picked["party_role"] == "OTHER"
    assert picked["group_id"] == groups["CURRENT_LIABILITIES"] and picked["status"] == "ACTIVE"


@pytest.mark.parametrize("first,second", [("BROKER", "OTHER"), ("OTHER", "BROKER")])
async def test_broker_and_other_share_one_account(
    client: httpx.AsyncClient, app: FastAPI, first: str, second: str
) -> None:
    await prepare(client)
    party = await create(client, "BRK", first)
    [account] = await accounts_of(client, party["id"])
    assert account["party_role"] == "OTHER" and account["status"] == "ACTIVE"
    role = await add_role(client, party["id"], second)
    before = await counts(app)
    activated = await activate_role(client, role)
    assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE", activated.text
    assert await accounts_of(client, party["id"]) == [account]
    after = await counts(app)
    # only the role itself changed: no second account, so one revision and one event
    assert after["accounts"] == before["accounts"]
    assert after["revisions"] == before["revisions"] + 1
    assert after["events"] == before["events"] + 1
    assert {r["role"] for r in await roles_of(client, party["id"])} == {first, second}


async def test_activation_reuses_a_live_account_and_activates_a_draft_one(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    creditors = (await standard_groups(app))["group.CREDITORS"]
    # a draft account made by the account route for a role that is still a draft
    party = await create(client, "ABC", "CUSTOMER")
    supplier = await add_role(client, party["id"], "SUPPLIER")
    draft = await client.post(
        BASE + "/accounts",
        json={
            "code": "ABC-PAY",
            "name": "ABC payable",
            "group_id": str(creditors),
            "kind": "PARTY",
            "party_id": party["id"],
            "party_role": "SUPPLIER",
        },
        headers=headers(),
    )
    # the customer account does not stand in the way of a supplier one
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "DRAFT"
    assert (await activate_role(client, supplier)).status_code == 200
    accounts = await accounts_of(client, party["id"])
    assert [(a["code"], a["party_role"], a["status"]) for a in accounts] == [
        ("ABC", "CUSTOMER", "ACTIVE"),
        ("ABC-PAY", "SUPPLIER", "ACTIVE"),
    ]
    assert accounts[1]["id"] == draft.json()["id"]
    # a live account written before the rule is reused as well, whatever its code
    old, _ = await legacy_party(app, "OLD", (("SUPPLIER", "DRAFT"),))
    kept = await legacy_account(
        app, code="OLD-LEDGER", group_id=creditors, party_id=old, role="SUPPLIER"
    )
    [role] = await roles_of(client, str(old))
    before = await counts(app)
    assert (await activate_role(client, role)).status_code == 200
    reused = await accounts_of(client, str(old))
    assert [a["id"] for a in reused] == [str(kept)]
    assert (await counts(app))["accounts"] == before["accounts"]


async def test_a_role_is_never_activated_without_its_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    party = await create(client, "ABC", "CUSTOMER")
    supplier = await add_role(client, party["id"], "SUPPLIER")
    before = await counts(app)
    state = await role_status(client, supplier)
    assert state == ("DRAFT", supplier["row_version"])

    # an explicit code that is taken is refused, even though a suffixed default would be free
    clash = await activate_role(client, supplier, {"code": "ABC"})
    assert clash.status_code == 422, clash.text
    assert "ledger.code" in clash.json()["error"]["fields"]
    assert await role_status(client, supplier) == state and await counts(app) == before

    # refused only after the role itself was activated inside the transaction: it is undone
    foreign = await activate_role(client, supplier, {"currency_mode": "FIXED", "currency": "USD"})
    assert foreign.status_code == 409, foreign.text
    assert await role_status(client, supplier) == state and await counts(app) == before

    # a bad group is named
    bad = await activate_role(client, supplier, {"group_id": groups["DEBTORS"]})
    assert bad.status_code == 422 and "ledger.group_id" in bad.json()["error"]["fields"]
    assert await role_status(client, supplier) == state and await counts(app) == before

    # a stale version is refused, and leaves no account behind
    stale = await activate_role(client, supplier | {"row_version": 99})
    assert stale.status_code == 409, stale.text
    assert await role_status(client, supplier) == state and await counts(app) == before

    # no standard group to put the account under: refused, not guessed
    await retire_group(app, (await standard_groups(app))["group.CREDITORS"])
    missing = await activate_role(client, supplier)
    assert missing.status_code == 422, missing.text
    assert "ledger.group_id" in missing.json()["error"]["fields"]
    assert await role_status(client, supplier) == state and await counts(app) == before

    # choosing a group makes the activation possible, with that group
    chosen = await activate_role(client, supplier, {"group_id": groups["CURRENT_LIABILITIES"]})
    assert chosen.status_code == 200, chosen.text
    [_, account] = await accounts_of(client, party["id"])
    assert account["party_role"] == "SUPPLIER" and account["status"] == "ACTIVE"
    assert account["group_id"] == groups["CURRENT_LIABILITIES"]


async def test_role_activation_authentication_replay_input_and_tenancy(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    party = await create(client, "ABC", "CUSTOMER")
    supplier = await add_role(client, party["id"], "SUPPLIER")
    path = BASE + "/party-roles/" + supplier["id"] + "/activate"
    version = {"expected_version": supplier["row_version"]}
    before = await counts(app)
    assert (await client.post(path, json=version)).status_code == 401
    for missing in (
        "accounting.account.manage",
        "accounting.account.read",
        "accounting.party.manage",
        "accounting.party.read",
    ):
        refused = await client.post(
            path, json=version, headers=headers(permissions=PERMISSIONS - {missing})
        )
        assert refused.status_code == 403, (missing, refused.text)
    for invalid in (
        {},
        version | {"extra": 1},
        version | {"ledger": {"kind": "BANK"}},
        version | {"ledger": {"currency": "usd"}},
        {"expected_version": 0},
    ):
        sent = await client.post(path, json=invalid, headers=headers())
        assert sent.status_code == 422, (invalid, sent.text)
    unknown = await client.post(
        BASE + f"/party-roles/{uuid7()}/activate", json=version, headers=headers()
    )
    assert unknown.status_code == 404, unknown.text
    # another tenant cannot reach this company's role
    outsider = await client.post(path, json=version, headers=headers(tenant=uuid7()))
    assert outsider.status_code >= 400, outsider.text
    other = uuid7()
    foreign, mine = headers(company=other), headers()
    foreign["X-Actor-Context"], foreign["X-Actor-Signature"] = (
        mine["X-Actor-Context"],
        mine["X-Actor-Signature"],
    )
    wrong = await client.post(
        base(other) + "/party-roles/" + supplier["id"] + "/activate", json=version, headers=foreign
    )
    assert wrong.status_code == 403, wrong.text
    assert await role_status(client, supplier) == ("DRAFT", supplier["row_version"])
    assert await counts(app) == before
    # a replay of the successful call is one effect
    h = headers()
    first = await client.post(path, json=version, headers=h)
    assert first.status_code == 200, first.text
    done = await counts(app)
    again = await client.post(path, json=version, headers=h)
    assert again.status_code == 200 and again.json() == first.json()
    assert again.headers["Idempotency-Replayed"] == "true"
    assert await counts(app) == done
    assert len(await accounts_of(client, party["id"])) == 2


# --- one live account per party and account role -------------------------------------------------


async def test_a_second_live_account_for_a_party_role_is_refused(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    creditors = (await standard_groups(app))["group.CREDITORS"]
    party = await create(client, "ABC", "SUPPLIER")
    [live] = await accounts_of(client, party["id"])

    def request(code: str, role: str = "SUPPLIER") -> dict[str, Any]:
        return {
            "code": code,
            "name": code + " ledger",
            "group_id": str(creditors),
            "kind": "PARTY",
            "party_id": party["id"],
            "party_role": role,
        }

    before = await counts(app)
    for route in ("/accounts", "/accounts/create-active"):
        refused = await client.post(BASE + route, json=request("ABC-2"), headers=headers())
        assert refused.status_code == 409, (route, refused.text)
        assert DUPLICATE in refused.json()["error"]["message"]
    assert await counts(app) == before
    # the OTHER account role is held the same way
    other = await create(client, "OTH", "OTHER")
    clash = await client.post(
        BASE + "/accounts",
        json=request("OTH-2", "OTHER") | {"party_id": other["id"]},
        headers=headers(),
    )
    assert clash.status_code == 409 and DUPLICATE in clash.json()["error"]["message"]
    # retiring the live account makes room for exactly one new one
    retired = await client.post(
        BASE + f"/accounts/{live['id']}/deactivate",
        json={"expected_version": live["row_version"]},
        headers=headers(),
    )
    assert retired.status_code == 200, retired.text
    draft = await client.post(BASE + "/accounts", json=request("ABC-3"), headers=headers())
    assert draft.status_code == 201, draft.text
    second = await client.post(BASE + "/accounts", json=request("ABC-4"), headers=headers())
    assert second.status_code == 409 and DUPLICATE in second.json()["error"]["message"]
    # the draft is not blocked by itself when it goes live
    live_again = await client.post(
        BASE + f"/accounts/{draft.json()['id']}/activate",
        json={"expected_version": draft.json()["row_version"]},
        headers=headers(),
    )
    assert live_again.status_code == 200, live_again.text
    third = await client.post(
        BASE + "/accounts/create-active", json=request("ABC-5"), headers=headers()
    )
    assert third.status_code == 409 and DUPLICATE in third.json()["error"]["message"]


async def test_a_draft_duplicate_cannot_go_live(client: httpx.AsyncClient, app: FastAPI) -> None:
    await prepare(client)
    creditors = (await standard_groups(app))["group.CREDITORS"]
    party = await create(client, "ABC", "SUPPLIER")
    [live] = await accounts_of(client, party["id"])
    # a draft written before the rule, next to the party's live account
    draft_id = await legacy_account(
        app,
        code="ABC-OLD",
        group_id=creditors,
        party_id=uuid.UUID(party["id"]),
        role="SUPPLIER",
        status="DRAFT",
    )
    before = await counts(app)
    refused = await client.post(
        BASE + f"/accounts/{draft_id}/activate", json={"expected_version": 1}, headers=headers()
    )
    assert refused.status_code == 409, refused.text
    assert DUPLICATE in refused.json()["error"]["message"]
    assert await counts(app) == before
    # the live account is untouched and the draft is still a draft
    accounts = await accounts_of(client, party["id"])
    assert [(a["code"], a["status"]) for a in accounts] == [("ABC", "ACTIVE"), ("ABC-OLD", "DRAFT")]
    assert accounts[0]["id"] == live["id"]


async def test_a_legacy_duplicate_stays_editable_and_can_be_retired(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    creditors = (await standard_groups(app))["group.CREDITORS"]
    party_id, _ = await legacy_party(app, "DUP", (("SUPPLIER", "ACTIVE"),))
    first = await legacy_account(
        app, code="DUP-1", group_id=creditors, party_id=party_id, role="SUPPLIER"
    )
    second = await legacy_account(
        app, code="DUP-2", group_id=creditors, party_id=party_id, role="SUPPLIER"
    )
    one, two = await accounts_of(client, str(party_id))
    assert (one["id"], two["id"]) == (str(first), str(second))
    # both live accounts stay editable although the rule would refuse the second today
    for item, change in ((one, {"name": "Renamed one"}), (two, {"description": "Kept"})):
        edited = await client.patch(
            BASE + f"/accounts/{item['id']}",
            json={"expected_version": item["row_version"]} | change,
            headers=headers(),
        )
        assert edited.status_code == 200, edited.text
    # ... and either can be retired, which is how the company resolves the duplicate
    retired = await client.post(
        BASE + f"/accounts/{one['id']}/deactivate",
        json={"expected_version": one["row_version"] + 1},
        headers=headers(),
    )
    assert retired.status_code == 200 and retired.json()["status"] == "INACTIVE", retired.text
    request = {
        "code": "DUP-3",
        "name": "Third",
        "group_id": str(creditors),
        "kind": "PARTY",
        "party_id": str(party_id),
        "party_role": "SUPPLIER",
    }
    # one is still live, so no new account yet
    blocked = await client.post(BASE + "/accounts", json=request, headers=headers())
    assert blocked.status_code == 409, blocked.text
    gone = await client.post(
        BASE + f"/accounts/{two['id']}/deactivate",
        json={"expected_version": two["row_version"] + 1},
        headers=headers(),
    )
    assert gone.status_code == 200, gone.text
    assert (
        await client.post(BASE + "/accounts", json=request, headers=headers())
    ).status_code == 201


# --- imports -----------------------------------------------------------------------------------


def row(
    key: str,
    resource: str,
    action: str,
    payload: dict[str, Any],
    *,
    target_id: str = "",
    target_record: str = "",
    depends_on: str = "",
    change_set: str | None = None,
) -> list[str]:
    """One import row: the controls in `CONTROLS` order, then the JSON payload."""
    return [
        key,
        change_set or key,
        resource,
        action,
        target_id,
        "",
        target_record,
        "id" if target_record else "",
        depends_on,
        "",
        json.dumps(payload),
    ]


def import_file(rows: list[list[str]]) -> dict[str, str]:
    raw = document("CSV", [("Records", [*CONTROLS, "_payload"], rows)])
    return {
        "filename": "parties.csv",
        "format": "CSV",
        "content_base64": base64.b64encode(raw).decode(),
    }


async def post_as(
    client: httpx.AsyncClient,
    make: Callable[[], dict[str, str]],
    path: str,
    request: dict[str, Any],
    status: int,
) -> dict[str, Any]:
    """Each import command is its own request, so each carries its own idempotency key."""
    sent = await client.post(BASE + path, json=request, headers=make())
    assert sent.status_code == status, sent.text
    result: dict[str, Any] = sent.json()
    return result


async def run_import(
    client: httpx.AsyncClient,
    rows: list[list[str]],
    *,
    parameters: dict[str, str] | None = None,
    mode: str = "CREATE_ONLY",
    make: Callable[[], dict[str, str]] = headers,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    template = await post_as(
        client,
        make,
        "/import-templates",
        {"definition": "parties", "parameters": parameters or {}},
        201,
    )
    job = await post_as(
        client,
        make,
        "/import-jobs",
        {"template_id": template["id"], "files": [import_file(rows)], "mode": mode},
        201,
    )
    root = "/import-jobs/" + job["id"]
    ready = await post_as(
        client, make, root + "/validate", {"expected_version": job["row_version"]}, 200
    )
    if ready["state"] != "READY" or not commit:
        return ready, None
    done = await post_as(
        client,
        make,
        root + "/commit",
        {"expected_version": ready["row_version"], "review_digest": ready["review_digest"]},
        200,
    )
    return ready, done


async def import_report(
    client: httpx.AsyncClient, job: dict[str, Any], make: Callable[[], dict[str, str]] = headers
) -> str:
    root = "/import-jobs/" + job["id"]
    options = {"kind": "RESULT"}
    ticket = await post_as(client, make, root + "/download-ticket", options, 200)
    got = await client.post(
        BASE + root + "/download", json=options | {"token": ticket["token"]}, headers=make()
    )
    assert got.status_code == 200, got.text
    return got.text


async def party_accounts(
    client: httpx.AsyncClient, make: Callable[[], dict[str, str]] = headers
) -> dict[str, list[dict[str, Any]]]:
    """Every PARTY account in full, by party id."""
    page = await client.get(
        BASE + "/accounts", headers=make(), params={"kind": "PARTY", "limit": 200}
    )
    assert page.status_code == 200, page.text
    found: dict[str, list[dict[str, Any]]] = {}
    for item in page.json()["items"]:
        got = await client.get(BASE + "/accounts/" + item["id"], headers=make())
        assert got.status_code == 200, got.text
        found.setdefault(got.json()["party_id"], []).append(got.json())
    return found


async def parties_by_code(
    client: httpx.AsyncClient, make: Callable[[], dict[str, str]] = headers
) -> dict[str, dict[str, Any]]:
    page = await client.get(BASE + "/parties", headers=make(), params={"limit": 200})
    assert page.status_code == 200, page.text
    return {item["code"]: item for item in page.json()["items"]}


async def test_the_plain_party_import_resource_cannot_create(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    template = await client.post(
        BASE + "/import-templates", json={"definition": "parties"}, headers=headers()
    )
    assert template.status_code == 201, template.text
    schemas = template.json()["snapshot"]["schemas"]
    # a plain party can still be updated, activated and deactivated, but has no create schema
    assert "party:CREATE" not in schemas
    assert {"party:UPDATE", "party:ACTIVATE", "party:DEACTIVATE"} <= set(schemas)
    before = await counts(app)
    request = body("IMP", None)
    staged = await client.post(
        BASE + "/import-jobs",
        json={
            "template_id": template.json()["id"],
            "files": [import_file([row("p", "party", "CREATE", request)])],
        },
        headers=headers(),
    )
    assert staged.status_code == 422, staged.text
    # the adapter refuses it as well, should a row ever reach it: a conflict, nothing created
    adapter = AccountingImportAdapter(actor_access(headers()), app.state.settings)
    record = BulkRecord(key="p", change_set="p", resource="party", action="CREATE", data=request)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            with pytest.raises(ConflictError) as raised:
                await adapter.execute(db, record, "CREATE_ONLY", {}, "k1")
    assert raised.value.status_code == 409
    assert "ledger account" in raised.value.message
    assert await counts(app) == before
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []


async def test_ready_customer_and_supplier_rows_always_get_an_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await fiscal_setup(client)
    groups = await standard_groups(app)
    # one row with no opening columns and one with, for each ready resource
    plans: list[tuple[str, str, list[list[str]]]] = [
        (
            "customer",
            "CUSTOMER",
            [
                row("a", "customer", "CREATE", body("CUS1", None)),
                row(
                    "b",
                    "customer",
                    "CREATE",
                    body(
                        "CUS2",
                        None,
                        opening_balance_type="DR",
                        opening_amount="10.50",
                        opening_account_code="DR-CUS2",
                    ),
                ),
            ],
        ),
        (
            "supplier",
            "SUPPLIER",
            [
                row("a", "supplier", "CREATE", body("SUP1", None)),
                row(
                    "b",
                    "supplier",
                    "CREATE",
                    body("SUP2", None, opening_balance_type="CR", opening_amount="20"),
                ),
            ],
        ),
    ]
    for resource, role, rows in plans:
        ready, done = await run_import(
            client,
            rows,
            parameters={"resource": resource, "role": role},
            make=finance_headers,
        )
        assert ready["state"] == "READY", ready
        assert done is not None and done["state"] == "SUCCEEDED" and done["completed_count"] == 2
    parties = await parties_by_code(client, finance_headers)
    accounts = await party_accounts(client, finance_headers)
    assert set(parties) == {"CUS1", "CUS2", "SUP1", "SUP2"}
    assert set(accounts) == {party["id"] for party in parties.values()}
    for code, role, account_code in (
        ("CUS1", "CUSTOMER", "CUS1"),
        ("CUS2", "CUSTOMER", "DR-CUS2"),
        ("SUP1", "SUPPLIER", "SUP1"),
        ("SUP2", "SUPPLIER", "SUP2"),
    ):
        party = parties[code]
        [account] = accounts[party["id"]]
        assert party["status"] == "ACTIVE"
        assert_party_account(
            account, party, role, groups, code=account_code, name=f"{code} Traders"
        )
    held = await client.get(BASE + "/opening-batches/party-balances", headers=finance_headers())
    assert held.status_code == 200, held.text
    # only the two rows that carried an opening balance hold one; the others just have the account
    assert sorted(item["role"] for item in held.json()["items"]) == ["CUSTOMER", "SUPPLIER"]


async def test_a_ready_row_whose_account_cannot_be_made_creates_no_party(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    existing = (
        await client.get(BASE + "/accounts", headers=headers(), params={"limit": 1})
    ).json()["items"][0]["code"]
    before = await counts(app)
    for resource, role in (("customer", "CUSTOMER"), ("supplier", "SUPPLIER")):
        # the party's own code is the account code, and a ledger account already uses it
        ready, done = await run_import(
            client,
            [row("a", resource, "CREATE", body(existing, None))],
            parameters={"resource": resource, "role": role},
        )
        assert ready["state"] == "INVALID" and done is None, ready
        assert "INVALID" in await import_report(client, ready)
    assert await counts(app) == before
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []


async def test_activating_a_role_through_an_import_creates_its_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party = await create(client, "ABC", "CUSTOMER")
    # staged in one aggregate: the role is created, then activated by a later row
    staged = [
        row(
            "sup",
            "party_role",
            "CREATE",
            {"party_id": party["id"], "role": "SUPPLIER"},
            change_set="s",
        ),
        row("sup_on", "party_role", "ACTIVATE", {}, target_record="sup", change_set="s"),
    ]
    ready, done = await run_import(client, staged)
    assert ready["state"] == "READY", ready
    assert done is not None and done["state"] == "SUCCEEDED" and done["completed_count"] == 2
    customer, supplier = await accounts_of(client, party["id"])
    assert customer["code"] == "ABC"
    assert_party_account(
        supplier, party, "SUPPLIER", groups, code="ABC-SUPP", name="ABC Traders (Supplier)"
    )
    # an existing draft role, activated by id in an update job, is given its account too
    plain = await add_role(client, party["id"], "OTHER")
    ready, done = await run_import(
        client,
        [
            row(
                "oth",
                "party_role",
                "ACTIVATE",
                {"expected_version": plain["row_version"]},
                target_id=plain["id"],
            )
        ],
        mode="UPDATE_ONLY",
    )
    assert done is not None and done["state"] == "SUCCEEDED", ready
    assert (await role_status(client, plain))[0] == "ACTIVE"
    accounts = await accounts_of(client, party["id"])
    assert sorted(a["code"] for a in accounts) == ["ABC", "ABC-OTHR", "ABC-SUPP"]
    other = next(a for a in accounts if a["code"] == "ABC-OTHR")
    assert other["party_role"] == "OTHER" and other["status"] == "ACTIVE"
    # a role whose account cannot be made is not activated by the import either
    await retire_group(app, groups["group.CREDITORS"])
    legacy, _ = await legacy_party(app, "NEW", (("SUPPLIER", "DRAFT"),))
    [new_role] = await roles_of(client, str(legacy))
    before = await counts(app)
    ready, done = await run_import(
        client,
        [
            row(
                "x",
                "party_role",
                "ACTIVATE",
                {"expected_version": new_role["row_version"]},
                target_id=new_role["id"],
            )
        ],
        mode="UPDATE_ONLY",
    )
    assert ready["state"] == "INVALID" and done is None, ready
    assert (await role_status(client, new_role))[0] == "DRAFT"
    assert await counts(app) == before


async def test_activating_a_broker_role_through_an_import_creates_its_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    party = await create(client, "ABC", "CUSTOMER")
    broker = await add_role(client, party["id"], "BROKER")
    ready, done = await run_import(
        client,
        [
            row(
                "brk",
                "party_role",
                "ACTIVATE",
                {"expected_version": broker["row_version"]},
                target_id=broker["id"],
            )
        ],
        mode="UPDATE_ONLY",
    )
    assert done is not None and done["state"] == "SUCCEEDED", ready
    assert (await role_status(client, broker))[0] == "ACTIVE"
    accounts = await accounts_of(client, party["id"])
    assert [(a["code"], a["party_role"], a["status"]) for a in accounts] == [
        ("ABC", "CUSTOMER", "ACTIVE"),
        ("ABC-OTHR", "OTHER", "ACTIVE"),
    ]


# --- tenant isolation ----------------------------------------------------------------------------


async def test_party_accounts_created_this_way_are_isolated_between_tenants(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    await prepare_company(client, OTHER_TENANT, OTHER_COMPANY)
    mine = await create(client, "SAME", "CUSTOMER")
    theirs = await create(client, "SAME", "CUSTOMER", h=other_headers(), company=OTHER_COMPANY)
    # the same code in two tenants is no clash, and each tenant has exactly its own account
    [mine_account] = await accounts_of(client, mine["id"])
    [their_account] = await accounts_of(
        client, theirs["id"], h=other_headers(), company=OTHER_COMPANY
    )
    assert mine_account["id"] != their_account["id"]
    assert mine_account["group_id"] != their_account["group_id"]
    # a further role in one tenant leaves the other tenant's accounts untouched
    role = await add_role(client, mine["id"], "SUPPLIER")
    before_theirs = await counts(app, tenant=OTHER_TENANT)
    assert (await activate_role(client, role)).status_code == 200
    assert await counts(app, tenant=OTHER_TENANT) == before_theirs
    assert len(await accounts_of(client, mine["id"])) == 2
    assert (
        len(await accounts_of(client, theirs["id"], h=other_headers(), company=OTHER_COMPANY)) == 1
    )
    # neither can read the other's account, party or list
    cross = await client.get(BASE + "/accounts/" + their_account["id"], headers=headers())
    assert cross.status_code == 404
    cross = await client.get(
        base(OTHER_COMPANY) + "/accounts/" + mine_account["id"], headers=other_headers()
    )
    assert cross.status_code == 404
    page = await client.get(
        BASE + "/accounts", headers=headers(), params={"party_id": theirs["id"]}
    )
    assert page.json()["items"] == []
    outsider = await client.get(
        BASE + "/accounts", headers=headers(tenant=uuid7()), params={"party_id": mine["id"]}
    )
    assert outsider.json()["items"] == []
    # the rows themselves: under each tenant's scope only its own party accounts exist
    for tenant, expected in ((TENANT, 2), (OTHER_TENANT, 1)):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                accounts = list(
                    await db.scalars(select(m.Account).where(m.Account.kind == "PARTY"))
                )
        assert len(accounts) == expected
        assert {a.tenant_id for a in accounts} == {tenant}

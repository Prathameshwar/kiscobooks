"""The ledger repair: party roles written before the rule held them get their account.

`POST /parties/ledger-repair` gives every ACTIVE party role (of an ACTIVE party) that has no
live account its default ledger, a bounded batch at a time. It reports what it cannot repair and
every party holding several live accounts for one role, and it never merges anything
(docs/party-ledger-mandatory-plan.md, PL-D05).

The legacy states (a role with no account, two live accounts for one role) cannot be made through
the routes any more, so they are inserted through the app's own session by the helpers of
`test_party_ledger_mandatory`.
"""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from accounting.tasks.commands import create_active
from tests.conftest import COMPANY, PERMISSIONS, TENANT, USER, headers
from tests.test_masters import prepare
from tests.test_party_ledger_mandatory import (
    OTHER_COMPANY,
    OTHER_TENANT,
    accounts_of,
    assert_party_account,
    base,
    counts,
    legacy_account,
    legacy_party,
    other_headers,
    prepare_company,
    standard_groups,
)

BASE = base()
REPAIR = BASE + "/parties/ledger-repair"
# the name the repair resolves when it creates a ledger, replaced to simulate failures
PATCHED = "accounting.tasks.party_ledger.create_active"


async def repair(
    client: httpx.AsyncClient,
    *,
    h: dict[str, str] | None = None,
    company: uuid.UUID = COMPANY,
    **request: Any,
) -> httpx.Response:
    return await client.post(
        base(company) + "/parties/ledger-repair", json=request, headers=h or headers()
    )


async def repaired(
    client: httpx.AsyncClient,
    *,
    h: dict[str, str] | None = None,
    company: uuid.UUID = COMPANY,
    **request: Any,
) -> dict[str, Any]:
    done = await repair(client, h=h, company=company, **request)
    assert done.status_code == 200, done.text
    result: dict[str, Any] = done.json()
    return result


async def stored_accounts(
    app: FastAPI, party_id: uuid.UUID, *, tenant: uuid.UUID = TENANT
) -> list[tuple[str, str | None, str]]:
    """(code, account role, status) of every account of the party, straight from the table."""
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            rows = (
                await db.execute(
                    select(m.Account.code, m.Account.party_role, m.Account.status)
                    .where(m.Account.party_id == party_id)
                    .order_by(m.Account.code)
                )
            ).all()
    return [(code, role, status) for code, role, status in rows]


def party_of(party_id: uuid.UUID, code: str) -> dict[str, Any]:
    return {"id": str(party_id), "code": code, "name": f"{code} Traders"}


async def test_a_role_with_no_account_gets_the_default_ledger(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party_id, _ = await legacy_party(app, "OLD", (("CUSTOMER", "ACTIVE"),))
    assert await stored_accounts(app, party_id) == []
    result = await repaired(client)
    # the documented result shape: what was created, what needs attention, where to continue
    assert set(result) == {"created", "attention", "next_after"}
    assert result["attention"] == [] and result["next_after"] is None
    [created] = result["created"]
    assert (created["party_id"], created["role"]) == (str(party_id), "CUSTOMER")
    [account] = await accounts_of(client, str(party_id))
    assert created["account_id"] == account["id"]
    assert_party_account(account, party_of(party_id, "OLD"), "CUSTOMER", groups)
    # the schema the OpenAPI document publishes for it
    schema = app.openapi()["components"]["schemas"]["PartyLedgerRepairResult"]
    assert set(schema["properties"]) == {"created", "attention", "next_after"}
    assert (
        app.openapi()["components"]["schemas"]["PartyLedgerRepair"]["properties"]["limit"][
            "maximum"
        ]
        == 200
    )


async def test_replay_and_rerun_create_nothing_more(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    party_id, _ = await legacy_party(app, "OLD", (("SUPPLIER", "ACTIVE"),))
    h = headers()
    first = await client.post(REPAIR, json={}, headers=h)
    assert first.status_code == 200, first.text
    assert len(first.json()["created"]) == 1
    done = await counts(app)
    again = await client.post(REPAIR, json={}, headers=h)
    assert again.status_code == 200 and again.json() == first.json()
    assert again.headers["Idempotency-Replayed"] == "true"
    assert await counts(app) == done
    # the same key with a different request is refused, not a second repair
    changed = await client.post(REPAIR, json={"limit": 5}, headers=h)
    assert changed.status_code == 422, changed.text
    assert await counts(app) == done
    # a new command finds nothing left to do
    rerun = await repaired(client)
    assert rerun == {"created": [], "attention": [], "next_after": None}
    assert await counts(app) == done
    assert len(await stored_accounts(app, party_id)) == 1


async def test_roles_that_already_have_an_account_are_skipped(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    creditors = (await standard_groups(app))["group.CREDITORS"]
    debtors = (await standard_groups(app))["group.DEBTORS"]
    live, _ = await legacy_party(app, "LIVE", (("CUSTOMER", "ACTIVE"),))
    await legacy_account(app, code="LIVE-A", group_id=debtors, party_id=live, role="CUSTOMER")
    draft, _ = await legacy_party(app, "DRAFTED", (("SUPPLIER", "ACTIVE"),))
    await legacy_account(
        app, code="DRAFTED-A", group_id=creditors, party_id=draft, role="SUPPLIER", status="DRAFT"
    )
    retired, _ = await legacy_party(app, "RETIRED", (("SUPPLIER", "ACTIVE"),))
    await legacy_account(
        app,
        code="RETIRED-A",
        group_id=creditors,
        party_id=retired,
        role="SUPPLIER",
        status="INACTIVE",
    )
    elsewhere, _ = await legacy_party(app, "ELSE", (("CUSTOMER", "ACTIVE"),))
    await legacy_account(
        app, code="ELSE-S", group_id=creditors, party_id=elsewhere, role="SUPPLIER"
    )
    unlaunched, _ = await legacy_party(app, "NOTYET", (("CUSTOMER", "DRAFT"),))
    result = await repaired(client)
    # a live or draft account for the role is enough; a retired one is not; another account
    # role is not; and a role that is not active is left alone and not reported
    assert {item["party_id"] for item in result["created"]} == {str(retired), str(elsewhere)}
    assert result["attention"] == []
    assert await stored_accounts(app, live) == [("LIVE-A", "CUSTOMER", "ACTIVE")]
    assert await stored_accounts(app, draft) == [("DRAFTED-A", "SUPPLIER", "DRAFT")]
    assert await stored_accounts(app, retired) == [
        ("RETIRED", "SUPPLIER", "ACTIVE"),
        ("RETIRED-A", "SUPPLIER", "INACTIVE"),
    ]
    assert await stored_accounts(app, elsewhere) == [
        ("ELSE", "CUSTOMER", "ACTIVE"),
        ("ELSE-S", "SUPPLIER", "ACTIVE"),
    ]
    assert await stored_accounts(app, unlaunched) == []


async def test_roles_of_a_party_that_is_not_active_are_reported_not_repaired(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    retired, _ = await legacy_party(app, "RETIRED", (("CUSTOMER", "ACTIVE"),), status="INACTIVE")
    unlaunched, _ = await legacy_party(app, "UNLAUNCHED", (("SUPPLIER", "ACTIVE"),), status="DRAFT")
    healthy, _ = await legacy_party(app, "HEALTHY", (("CUSTOMER", "ACTIVE"),))
    before = await counts(app)
    result = await repaired(client)
    assert [item["party_id"] for item in result["created"]] == [str(healthy)]
    attention = {item["party_id"]: item for item in result["attention"]}
    assert set(attention) == {str(retired), str(unlaunched)}
    assert attention[str(retired)]["role"] == "CUSTOMER"
    assert attention[str(unlaunched)]["role"] == "SUPPLIER"
    for item in attention.values():
        assert "not active" in item["reason"]
        assert item["account_id"] is None and item["account_ids"] is None
    assert await stored_accounts(app, retired) == []
    assert await stored_accounts(app, unlaunched) == []
    assert len(await stored_accounts(app, healthy)) == 1
    # only the healthy party's account was written: create and activate, each audited
    after = await counts(app)
    assert after["accounts"] == before["accounts"] + 1
    assert after["revisions"] == before["revisions"] + 2
    assert after["events"] == before["events"] + 2
    # the same reports come back until the company fixes the party
    again = await repaired(client)
    assert again["created"] == [] and {i["party_id"] for i in again["attention"]} == set(attention)


async def test_a_code_collision_is_reported_without_failing_the_batch(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    first, _ = await legacy_party(app, "OK1", (("CUSTOMER", "ACTIVE"),))
    clash, _ = await legacy_party(app, "TAKEN", (("SUPPLIER", "ACTIVE"),))
    last, _ = await legacy_party(app, "OK2", (("SUPPLIER", "ACTIVE"),))
    # a plain ledger account already uses the clashing party's own code
    await legacy_account(app, code="TAKEN", group_id=uuid.UUID(groups["INDIRECT_EXPENSES"]))
    before = await counts(app)
    done = await repair(client)
    assert done.status_code == 200, done.text
    result = done.json()
    # the batch around the failure still went through, in order
    assert [item["party_id"] for item in result["created"]] == [str(first), str(last)]
    [problem] = result["attention"]
    assert (problem["party_id"], problem["role"]) == (str(clash), "SUPPLIER")
    assert "code" in problem["reason"] and problem["account_id"] is None
    assert await stored_accounts(app, clash) == []
    assert len(await stored_accounts(app, first)) == len(await stored_accounts(app, last)) == 1
    after = await counts(app)
    # exactly the two accounts that were made: nothing of the refused one was left behind
    assert after["accounts"] == before["accounts"] + 2
    assert after["revisions"] == before["revisions"] + 4
    assert after["events"] == before["events"] + 4


async def test_duplicates_are_reported_on_the_first_call_only_and_never_merged(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    creditors, debtors = groups["group.CREDITORS"], groups["group.DEBTORS"]
    twice, _ = await legacy_party(app, "TWICE", (("SUPPLIER", "ACTIVE"),))
    t1 = await legacy_account(
        app, code="TWICE-1", group_id=creditors, party_id=twice, role="SUPPLIER"
    )
    t2 = await legacy_account(
        app, code="TWICE-2", group_id=creditors, party_id=twice, role="SUPPLIER"
    )
    mixed, _ = await legacy_party(app, "MIXED", (("CUSTOMER", "ACTIVE"),))
    c1 = await legacy_account(
        app, code="MIXED-1", group_id=debtors, party_id=mixed, role="CUSTOMER"
    )
    c2 = await legacy_account(
        app, code="MIXED-2", group_id=debtors, party_id=mixed, role="CUSTOMER", status="DRAFT"
    )
    broker, _ = await legacy_party(app, "BROKERS", (("BROKER", "ACTIVE"),))
    o1 = await legacy_account(app, code="BRK-1", group_id=creditors, party_id=broker, role="OTHER")
    o2 = await legacy_account(app, code="BRK-2", group_id=creditors, party_id=broker, role="OTHER")
    # a retired account next to a live one is not a duplicate
    fine, _ = await legacy_party(app, "FINE", (("SUPPLIER", "ACTIVE"),))
    await legacy_account(
        app, code="FINE-OLD", group_id=creditors, party_id=fine, role="SUPPLIER", status="INACTIVE"
    )
    await legacy_account(app, code="FINE-NEW", group_id=creditors, party_id=fine, role="SUPPLIER")
    snapshot = {p: await stored_accounts(app, p) for p in (twice, mixed, broker, fine)}
    before = await counts(app)

    result = await repaired(client)
    assert result["created"] == [] and result["next_after"] is None
    reported = {item["party_id"]: item for item in result["attention"]}
    assert set(reported) == {str(twice), str(mixed), str(broker)}
    assert (reported[str(twice)]["role"], reported[str(twice)]["account_ids"]) == (
        "SUPPLIER",
        sorted([str(t1), str(t2)]),
    )
    assert (reported[str(mixed)]["role"], reported[str(mixed)]["account_ids"]) == (
        "CUSTOMER",
        sorted([str(c1), str(c2)]),
    )
    # the account role is what is reported: a broker's accounts are OTHER accounts
    assert (reported[str(broker)]["role"], reported[str(broker)]["account_ids"]) == (
        "OTHER",
        sorted([str(o1), str(o2)]),
    )
    assert all("more than one" in item["reason"] for item in reported.values())
    # never merged, retired or added to: every row is exactly as it was
    for party_id, rows in snapshot.items():
        assert await stored_accounts(app, party_id) == rows
    assert await counts(app) == before
    # a later page reports no duplicates: they belong to the data, not to a page
    nil = uuid.UUID(int=0)
    later = await repaired(client, after=str(nil))
    assert later == {"created": [], "attention": [], "next_after": None}
    # ... while a fresh first call reports them again
    again = await repaired(client)
    assert {item["party_id"] for item in again["attention"]} == set(reported)
    assert await counts(app) == before


async def test_paging_visits_every_role_exactly_once(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    cust, _ = await legacy_party(app, "P1", (("CUSTOMER", "ACTIVE"),))
    supp, _ = await legacy_party(app, "P2", (("SUPPLIER", "ACTIVE"),))
    both, _ = await legacy_party(app, "P3", (("CUSTOMER", "ACTIVE"), ("SUPPLIER", "ACTIVE")))
    shared, _ = await legacy_party(app, "P4", (("BROKER", "ACTIVE"), ("OTHER", "ACTIVE")))
    plain, _ = await legacy_party(app, "P5", (("OTHER", "ACTIVE"),))
    retired, _ = await legacy_party(app, "P6", (("CUSTOMER", "ACTIVE"),), status="INACTIVE")
    # eight roles lack an account; the broker and "other" roles of P4 share one account
    pages: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        request: dict[str, Any] = {"limit": 3}
        if after is not None:
            request["after"] = after
        page = await repaired(client, **request)
        pages.append(page)
        assert len(page["created"]) + len(page["attention"]) <= 3
        if page["next_after"] is None:
            break
        # the cursor moves strictly forward
        assert after is None or page["next_after"] > after
        after = page["next_after"]
        assert len(pages) < 10
    assert [(len(p["created"]), len(p["attention"])) for p in pages] == [(3, 0), (2, 0), (1, 1)]
    assert all(p["next_after"] for p in pages[:-1]) and pages[-1]["next_after"] is None
    created = [(item["party_id"], item["role"]) for p in pages for item in p["created"]]
    # every repairable role was handled once, and P4's pair produced a single account
    assert len(created) == len(set(created)) == 6
    assert {party for party, _ in created} == {
        str(cust),
        str(supp),
        str(both),
        str(shared),
        str(plain),
    }
    assert sum(1 for party, _ in created if party == str(shared)) == 1
    [problem] = [item for p in pages for item in p["attention"]]
    assert problem["party_id"] == str(retired) and "not active" in problem["reason"]
    expected = {cust: 1, supp: 1, both: 2, shared: 1, plain: 1, retired: 0}
    for party_id, number in expected.items():
        assert len(await stored_accounts(app, party_id)) == number
    assert await stored_accounts(app, both) == [
        ("P3", "CUSTOMER", "ACTIVE"),
        ("P3-SUPP", "SUPPLIER", "ACTIVE"),
    ]
    # one more pass over everything: nothing to create, the retired party still reported once
    final = await repaired(client, limit=200)
    assert final["created"] == [] and final["next_after"] is None
    assert [item["party_id"] for item in final["attention"]] == [str(retired)]


async def test_broker_and_other_of_one_party_get_one_account(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    first, _ = await legacy_party(app, "BRK", (("BROKER", "ACTIVE"), ("OTHER", "ACTIVE")))
    second, _ = await legacy_party(app, "OTH", (("OTHER", "ACTIVE"), ("BROKER", "ACTIVE")))
    result = await repaired(client)
    assert result["attention"] == []
    # the first role of each pair, in identity order, made the account the second one shares
    assert [(i["party_id"], i["role"]) for i in result["created"]] == [
        (str(first), "BROKER"),
        (str(second), "OTHER"),
    ]
    for party_id, code in ((first, "BRK"), (second, "OTH")):
        [account] = await accounts_of(client, str(party_id))
        assert_party_account(account, party_of(party_id, code), "BROKER", groups)
        assert account["party_role"] == "OTHER"
    assert await repaired(client) == {"created": [], "attention": [], "next_after": None}


async def test_a_party_with_only_a_broker_role_gets_an_account_in_the_other_account_role(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    groups = await standard_groups(app)
    party_id, _ = await legacy_party(app, "BONLY", (("BROKER", "ACTIVE"),))
    result = await repaired(client)
    assert result["attention"] == []
    [created] = result["created"]
    assert (created["party_id"], created["role"]) == (str(party_id), "BROKER")
    [account] = await accounts_of(client, str(party_id))
    assert_party_account(account, party_of(party_id, "BONLY"), "BROKER", groups)
    assert account["party_role"] == "OTHER"
    assert await repaired(client) == {"created": [], "attention": [], "next_after": None}


async def test_a_failing_member_rolls_back_only_its_own_savepoint(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await prepare(client)
    first, _ = await legacy_party(app, "OK1", (("CUSTOMER", "ACTIVE"),))
    boom, _ = await legacy_party(app, "BOOM", (("SUPPLIER", "ACTIVE"),))
    last, _ = await legacy_party(app, "OK2", (("SUPPLIER", "ACTIVE"),))
    real = create_active

    async def refuse_after_writing(*args: Any, **kwargs: Any) -> m.Record:
        # the account and its audit rows really are written, and only then refused
        written = await real(*args, **kwargs)
        incoming: BaseModel = args[3]
        if incoming.model_dump()["code"] == "BOOM":
            raise ConflictError("refused after the account was written")
        return written

    monkeypatch.setattr(PATCHED, refuse_after_writing)
    before = await counts(app)
    done = await repair(client)
    assert done.status_code == 200, done.text
    result = done.json()
    assert [item["party_id"] for item in result["created"]] == [str(first), str(last)]
    [problem] = result["attention"]
    assert problem["party_id"] == str(boom) and "refused after" in problem["reason"]
    assert await stored_accounts(app, boom) == []
    assert len(await stored_accounts(app, first)) == len(await stored_accounts(app, last)) == 1
    after = await counts(app)
    # the refused member's account, revisions and events went with its savepoint; the rest stayed
    assert after["accounts"] == before["accounts"] + 2
    assert after["revisions"] == before["revisions"] + 4
    assert after["events"] == before["events"] + 4


async def test_an_unexpected_failure_rolls_the_whole_batch_back(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await prepare(client)
    first, _ = await legacy_party(app, "OK1", (("CUSTOMER", "ACTIVE"),))
    boom, _ = await legacy_party(app, "BOOM", (("SUPPLIER", "ACTIVE"),))
    real = create_active

    async def crash(*args: Any, **kwargs: Any) -> m.Record:
        written = await real(*args, **kwargs)
        incoming: BaseModel = args[3]
        if incoming.model_dump()["code"] == "BOOM":
            raise RuntimeError("not a refusal the command knows how to report")
        return written

    h = headers()
    before = await counts(app)
    with monkeypatch.context() as patched:
        patched.setattr(PATCHED, crash)
        failed = await client.post(REPAIR, json={}, headers=h)
    assert failed.status_code == 500, failed.text
    # not even the first member's account, its revisions or its events survive
    assert await counts(app) == before
    assert await stored_accounts(app, first) == [] and await stored_accounts(app, boom) == []
    # nothing was recorded as done, so the same command can be retried and now succeeds
    retried = await client.post(REPAIR, json={}, headers=h)
    assert retried.status_code == 200, retried.text
    assert {item["party_id"] for item in retried.json()["created"]} == {str(first), str(boom)}
    assert len(await stored_accounts(app, first)) == len(await stored_accounts(app, boom)) == 1


async def test_repair_authentication_permissions_and_input(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    party_id, _ = await legacy_party(app, "OLD", (("CUSTOMER", "ACTIVE"),))
    before = await counts(app)
    assert (await client.post(REPAIR, json={})).status_code == 401
    keyless = {k: v for k, v in headers().items() if k != "Idempotency-Key"}
    assert (await client.post(REPAIR, json={}, headers=keyless)).status_code == 422
    for missing in (
        "accounting.account.manage",
        "accounting.account.read",
        "accounting.party.read",
    ):
        refused = await repair(client, h=headers(permissions=PERMISSIONS - {missing}))
        assert refused.status_code == 403, (missing, refused.text)
    # an actor granted this company acting under another company's context
    other = uuid7()
    foreign, mine = headers(company=other), headers()
    foreign["X-Actor-Context"], foreign["X-Actor-Signature"] = (
        mine["X-Actor-Context"],
        mine["X-Actor-Signature"],
    )
    assert (await repair(client, h=foreign, company=other)).status_code == 403
    for invalid in (
        {"limit": 0},
        {"limit": -1},
        {"limit": 201},
        {"limit": "many"},
        {"limit": 1.5},
        {"after": "not-a-uuid"},
        {"unknown": True},
    ):
        sent = await repair(client, **invalid)
        assert sent.status_code == 422, (invalid, sent.text)
    # another tenant cannot repair this company
    outsider = await repair(client, h=headers(tenant=uuid7()))
    assert outsider.status_code >= 400, outsider.text
    # every refusal left the role without an account
    assert await counts(app) == before and await stored_accounts(app, party_id) == []
    # the boundary limits are valid, and party management is not needed to repair
    one = await repaired(
        client, h=headers(permissions=PERMISSIONS - {"accounting.party.manage"}), limit=1
    )
    assert [item["party_id"] for item in one["created"]] == [str(party_id)]
    assert (await repair(client, limit=200)).status_code == 200


async def test_repair_is_isolated_between_tenants(client: httpx.AsyncClient, app: FastAPI) -> None:
    await prepare(client)
    await prepare_company(client, OTHER_TENANT, OTHER_COMPANY)
    mine, _ = await legacy_party(app, "MINE", (("CUSTOMER", "ACTIVE"),))
    theirs, _ = await legacy_party(
        app, "THEIRS", (("SUPPLIER", "ACTIVE"),), tenant=OTHER_TENANT, company=OTHER_COMPANY
    )
    crowded, _ = await legacy_party(
        app, "CROWDED", (("SUPPLIER", "ACTIVE"),), tenant=OTHER_TENANT, company=OTHER_COMPANY
    )
    their_group = (await standard_groups(app, tenant=OTHER_TENANT, company=OTHER_COMPANY))[
        "group.CREDITORS"
    ]
    for code in ("CROWDED-1", "CROWDED-2"):
        await legacy_account(
            app,
            code=code,
            group_id=their_group,
            party_id=crowded,
            role="SUPPLIER",
            tenant=OTHER_TENANT,
            company=OTHER_COMPANY,
        )
    their_before = await counts(app, tenant=OTHER_TENANT)
    key = f"shared-{uuid.uuid4()}"

    # the first tenant repairs its own company: nothing of the other tenant is touched or reported
    mine_done = await repaired(client, h=headers(key=key))
    assert [item["party_id"] for item in mine_done["created"]] == [str(mine)]
    assert mine_done["attention"] == [] and mine_done["next_after"] is None
    assert await counts(app, tenant=OTHER_TENANT) == their_before
    assert await stored_accounts(app, theirs, tenant=OTHER_TENANT) == []
    assert len(await stored_accounts(app, crowded, tenant=OTHER_TENANT)) == 2

    # the same idempotency key in the other tenant is its own command, with its own result
    mine_after = await counts(app)
    theirs_done = await repaired(client, h=other_headers(key=key), company=OTHER_COMPANY)
    assert [item["party_id"] for item in theirs_done["created"]] == [str(theirs)]
    [crowd] = theirs_done["attention"]
    assert crowd["party_id"] == str(crowded)
    assert len(crowd["account_ids"]) == 2
    assert theirs_done != mine_done
    assert await counts(app) == mine_after
    assert await stored_accounts(app, mine) == [("MINE", "CUSTOMER", "ACTIVE")]
    assert await stored_accounts(app, theirs, tenant=OTHER_TENANT) == [
        ("THEIRS", "SUPPLIER", "ACTIVE")
    ]
    # every row the repair wrote belongs to the tenant and company that ran it
    for tenant, company, expected in ((TENANT, COMPANY, 1), (OTHER_TENANT, OTHER_COMPANY, 3)):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                rows = list(await db.scalars(select(m.Account).where(m.Account.kind == "PARTY")))
        assert len(rows) == expected
        assert {(row.tenant_id, row.company_id) for row in rows} == {(tenant, company)}


async def test_each_created_account_is_audited_and_skipped_ones_are_not(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    debtors = (await standard_groups(app))["group.DEBTORS"]
    customer, _ = await legacy_party(app, "CUST", (("CUSTOMER", "ACTIVE"),))
    supplier, _ = await legacy_party(app, "SUPP", (("SUPPLIER", "ACTIVE"),))
    kept, _ = await legacy_party(app, "KEPT", (("CUSTOMER", "ACTIVE"),))
    kept_account = await legacy_account(
        app, code="KEPT-A", group_id=debtors, party_id=kept, role="CUSTOMER"
    )
    before = await counts(app)
    result = await repaired(client)
    created = {item["party_id"]: uuid.UUID(item["account_id"]) for item in result["created"]}
    assert set(created) == {str(customer), str(supplier)}
    after = await counts(app)
    assert after["revisions"] == before["revisions"] + 4
    assert after["events"] == before["events"] + 4
    ours = list(created.values())
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revisions = (
                await db.execute(
                    select(
                        MasterRevision.object_id,
                        MasterRevision.entity_type,
                        MasterRevision.action,
                        MasterRevision.created_by,
                    ).where(MasterRevision.object_id.in_([*ours, kept_account]))
                )
            ).all()
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.aggregate_id.in_([*ours, kept_account]))
                )
            )
    # each created account has a create and an activate revision by the acting user
    for account_id in ours:
        mine = [(entity, action, by) for obj, entity, action, by in revisions if obj == account_id]
        assert sorted(mine) == [("account", "activate", USER), ("account", "create", USER)]
        shown = [e for e in events if e.aggregate_id == account_id]
        assert sorted(e.event_type for e in shown) == [
            "accounting.account.activate",
            "accounting.account.create",
        ]
        for event in shown:
            assert event.tenant_id == TENANT and event.aggregate_type == "accounting.account"
            assert event.payload["actor_user_id"] == str(USER)
            assert event.payload["company_id"] == str(COMPANY)
            assert event.payload["entity_type"] == "accounting.account"
            assert event.payload["entity_id"] == str(account_id)
    # the account that was already there is not touched and not audited again
    assert not [obj for obj, *_ in revisions if obj == kept_account]
    assert not [e for e in events if e.aggregate_id == kept_account]

"""Atomic creation, exact held evidence, replay and company/tenant boundaries."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.tenant_context import TenantContextError
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from accounting.models.ledger import Journal
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import Account, Party
from tests.conftest import COMPANY, PERMISSIONS, TENANT
from tests.master_opening_factories import legacy_held
from tests.test_field_policy import policy
from tests.test_fiscal_api import BASE, FINANCE_PERMISSIONS, change
from tests.test_fiscal_api import fiscal_setup as setup_books
from tests.test_ledger_api import Authority
from tests.test_ledger_api import ledger_headers as finance_headers


@pytest.fixture(autouse=True)
def posting_authority(app):
    app.state.posting_client = Authority()


async def fiscal_setup(client):
    periods = await setup_books(client)
    first = min(periods, key=lambda row: row["start_date"])
    opened = await change(client, first, "OPEN")
    assert opened.status_code == 200, opened.text
    return [opened.json() if row["id"] == first["id"] else row for row in periods]


HELD = BASE + "/opening-batches/master-balances"


def opening(**given):
    return {"amount": "100", "side": "CREDIT", "opening_date": "2026-04-01"} | given


def party(code="OPEN-1", **given):
    return {
        "code": code,
        "name": "Opening supplier",
        "legal_name": "Opening supplier",
        "country_code": "IN",
        "role": "SUPPLIER",
    } | given


async def post(client, path, body, h=None, status=201):
    result = await client.post(BASE + path, json=body, headers=h or finance_headers())
    assert result.status_code == status, result.text
    return result.json()


async def held(client, h=None, query=""):
    got = await client.get(HELD + query, headers=h or finance_headers())
    assert got.status_code == 200, got.text
    return got.json()["items"]


async def test_party_opening_is_atomic_exact_and_idempotent(client, app):
    await fiscal_setup(client)
    h = finance_headers()
    body = party(opening=opening(amount="100.0001"))
    first = await post(client, "/parties/create-with-details", body, h)
    second = await post(client, "/parties/create-with-details", body, h)
    assert first == second
    rows = await held(client)
    assert len(rows) == 1 and rows[0]["entry"]["amount"] == "100.0001"
    assert rows[0]["entry"]["documents"][0]["document_kind"] == "ON_ACCOUNT"
    async with app.state.session_factory() as db:
        with tenant_scope(TENANT):
            assert await db.scalar(select(func.count(Journal.id))) == 1
            assert await db.scalar(select(func.count(MasterOpeningBalance.id))) == 1
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "accounting.master_opening_balance.create"
                    )
                )
                == 1
            )


async def test_invalid_opening_rolls_back_party_account_and_audit(client, app):
    await fiscal_setup(client)
    async with app.state.session_factory() as db:
        with tenant_scope(TENANT):
            before = (
                await db.scalar(select(func.count(Party.id))),
                await db.scalar(select(func.count(Account.id))),
                await db.scalar(select(func.count(Outbox.id))),
            )
    await post(
        client,
        "/parties/create-with-details",
        party(opening=opening(opening_date="2026-04-02")),
        status=422,
    )
    async with app.state.session_factory() as db:
        with tenant_scope(TENANT):
            after = (
                await db.scalar(select(func.count(Party.id))),
                await db.scalar(select(func.count(Account.id))),
                await db.scalar(select(func.count(Outbox.id))),
            )
            assert await db.scalar(select(func.count(MasterOpeningBalance.id))) == 0
    assert before == after


async def test_bill_wise_original_and_pending_values_are_retained(client):
    await fiscal_setup(client)
    documents = [
        {
            "reference": "BILL-1",
            "amount": "60",
            "original_amount": "200",
            "document_kind": "BILL",
            "document_date": "2026-03-01",
            "due_date": "2026-03-31",
        },
        {
            "reference": "BILL-2",
            "amount": "40",
            "original_amount": "40",
            "document_kind": "BILL",
            "document_date": "2026-03-10",
            "due_date": "2026-04-15",
        },
    ]
    await post(client, "/parties/create-with-details", party(opening=opening(documents=documents)))
    value = (await held(client))[0]["entry"]
    assert value["amount"] == "100" and len(value["documents"]) == 2
    assert [doc["original_amount"] for doc in value["documents"]] == ["200", "40"]


async def test_account_with_opening_is_activated_and_posted_in_both_creation_routes(client):
    await fiscal_setup(client)
    groups = (await client.get(BASE + "/account-groups", headers=finance_headers())).json()["items"]
    group = next(value for value in groups if value["code"] == "CAPITAL")
    body = {
        "code": "OPEN-CAPITAL",
        "name": "Opening capital",
        "kind": "GENERAL",
        "group_id": group["id"],
        "opening": opening(),
    }
    value = await post(client, "/accounts", body)
    assert value["status"] == "ACTIVE"
    active = await post(client, "/accounts/create-active", body | {"code": "OPEN-CAPITAL-ACTIVE"})
    assert active["status"] == "ACTIVE"
    assert len(await held(client)) == 2


async def test_capture_and_replay_recheck_finance_and_field_authority(client):
    await fiscal_setup(client)
    body = party(opening=opening())
    denied = finance_headers(permissions=FINANCE_PERMISSIONS - {"accounting.finance.manage"})
    await post(client, "/parties/create-with-details", body, denied, status=403)
    h = finance_headers()
    await post(client, "/parties/create-with-details", body, h)
    denied = finance_headers(
        key=h["Idempotency-Key"],
        policies=[policy("amount", access="write", entity="accounting.journal_line")],
    )
    await post(client, "/parties/create-with-details", body, denied, status=403)


async def test_scoped_reads_query_bounds_and_withdrawal(client, app):
    await fiscal_setup(client)
    await legacy_held(client, app)
    value = (await held(client))[0]
    denied = await client.get(HELD, headers=finance_headers(permissions=PERMISSIONS))
    assert denied.status_code == 403
    other = finance_headers(tenant=uuid.uuid4(), company=uuid.uuid4())
    wrong = await client.post(
        HELD + "/" + value["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "wrong scope"},
        headers=other,
    )
    assert wrong.status_code == 401
    for query in ("?limit=51", "?q=anything", "?account_id=" + str(uuid.uuid4())):
        bad = await client.get(HELD + query, headers=finance_headers())
        assert bad.status_code in (403, 404, 422), bad.text
    h = finance_headers()
    result = await client.post(
        HELD + "/" + value["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "wrong amount"},
        headers=h,
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "WITHDRAWN"
    replay = await client.post(
        HELD + "/" + value["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "wrong amount"},
        headers=h,
    )
    assert replay.status_code == 200 and replay.json() == result.json()


async def test_metadata_returns_scoped_native_capture_and_opening_date(client):
    await fiscal_setup(client)
    result = await client.get(HELD + "/capture", headers=finance_headers())
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["company_id"] == str(COMPANY) and value["opening_date"] == "2026-04-01"
    assert value["can_capture"] and value["capture"]["properties"]["documents"]["maxItems"] == 200


async def test_balanced_native_worksheet_includes_held_evidence_and_fences_withdrawal(client, app):
    from tests.test_financial_opening_api import ROOT, body_for
    from tests.test_ledger_api import ledger_headers

    body = await body_for(client, app)
    await legacy_held(client, app)
    value = (await held(client))[0]
    body["entries"] = [body["entries"][0], value["entry"]]
    body["entries"][0]["amount"] = "100"
    body["entries"][0]["base_amount"] = "100"
    response = await client.post(ROOT, json=body, headers=ledger_headers())
    assert response.status_code == 201, response.text
    assert (await held(client))[0]["included"] is True
    withdrawn = await client.post(
        HELD + "/" + value["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "Included already"},
        headers=finance_headers(),
    )
    assert withdrawn.status_code == 409, withdrawn.text
    body["entries"][1]["account_id"] = body["entries"][0]["account_id"]
    rejected = await client.post(ROOT + "/preview", json=body, headers=ledger_headers())
    assert rejected.status_code == 422, rejected.text


async def test_new_held_table_isolates_two_populated_tenants_and_signed_cursors(client, app):
    await fiscal_setup(client)
    await post(client, "/parties/create-with-details", party(opening=opening()))
    other_tenant, other_company = uuid7(), uuid7()
    other_base = "/v1/companies/" + str(other_company)

    class ScopedClient:
        """Reuse fiscal setup through real HTTP requests under a second signed authority."""

        async def post(self, path, **kwargs):
            kwargs["headers"] = finance_headers(tenant=other_tenant, company=other_company)
            return await client.post(path.replace(BASE, other_base, 1), **kwargs)

        async def get(self, path, **kwargs):
            kwargs["headers"] = finance_headers(tenant=other_tenant, company=other_company)
            return await client.get(path.replace(BASE, other_base, 1), **kwargs)

    scoped = ScopedClient()
    await fiscal_setup(scoped)
    created = await scoped.post(
        BASE + "/parties/create-with-details", json=party(opening=opening(amount="200"))
    )
    assert created.status_code == 201, created.text
    original = await held(client)
    others = (await scoped.get(HELD)).json()["items"]
    assert len(original) == len(others) == 1
    assert original[0]["entry"]["amount"] == "100" and others[0]["entry"]["amount"] == "200"
    wrong = await scoped.post(
        HELD + "/" + original[0]["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "Wrong tenant"},
    )
    assert wrong.status_code in (403, 404), wrong.text
    for tenant in (TENANT, other_tenant):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                assert await db.scalar(select(func.count(MasterOpeningBalance.id))) == 1
    await post(client, "/parties/create-with-details", party(code="OPEN-2", opening=opening()))
    first = await client.get(HELD + "?limit=1", headers=finance_headers())
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    crossed = await scoped.get(HELD + "?limit=1&cursor=" + cursor)
    assert crossed.status_code == 422, crossed.text


async def test_closed_books_block_new_capture_but_receipt_replay_is_safe(client):
    periods = await fiscal_setup(client)
    period = min(periods, key=lambda row: row["start_date"])
    h = finance_headers()
    body = party(opening=opening())
    first = await post(client, "/parties/create-with-details", body, h)
    batch = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Explicit zero opening review"},
        headers=finance_headers(),
    )
    assert batch.status_code == 201, batch.text
    finalized = await client.post(
        BASE + "/opening-batches/" + batch.json()["id"] + "/finalize-zero",
        json={"expected_version": batch.json()["row_version"]},
        headers=finance_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    soft = await change(client, period, "SOFT_CLOSED")
    assert soft.status_code == 200, soft.text
    closed = await change(client, soft.json(), "CLOSED")
    assert closed.status_code == 200, closed.text
    assert await post(client, "/parties/create-with-details", body, h) == first
    await post(
        client, "/parties/create-with-details", party(code="CLOSED", opening=opening()), status=422
    )
    metadata = await client.get(HELD + "/capture", headers=finance_headers())
    assert metadata.status_code == 200 and not metadata.json()["can_capture"]


async def test_withdrawn_source_cannot_be_reintroduced_and_reason_is_audited(client, app):
    from tests.test_financial_opening_api import ROOT, body_for
    from tests.test_ledger_api import ledger_headers

    body = await body_for(client, app)
    await legacy_held(client, app)
    value = (await held(client))[0]
    withdrawn = await client.post(
        HELD + "/" + value["id"] + "/withdraw",
        json={"expected_version": 1, "reason": "Amount was incorrect"},
        headers=finance_headers(),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    body["entries"] = [body["entries"][0] | {"amount": "100", "base_amount": "100"}, value["entry"]]
    refused = await client.post(ROOT + "/preview", json=body, headers=ledger_headers())
    assert refused.status_code == 422, refused.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            event = await db.scalar(
                select(Outbox).where(
                    Outbox.event_type == "accounting.master_opening_balance.withdraw"
                )
            )
            assert event and "Amount was incorrect" in str(event.payload)


async def test_master_opening_evidence_is_immutable_and_never_deleted(client, app):
    await fiscal_setup(client)
    await legacy_held(client, app)
    with tenant_scope(TENANT):
        for operation in ("entry", "delete", "scope"):
            async with app.state.session_factory() as db:
                row = await db.scalar(select(MasterOpeningBalance))
                if operation == "entry":
                    row.entry = row.entry | {"amount": "1"}
                if operation == "scope":
                    row.company_id = uuid7()
                if operation == "delete":
                    await db.delete(row)
                with pytest.raises((ConflictError, TenantContextError)):
                    await db.flush()
                await db.rollback()
        async with app.state.session_factory() as db:
            row = await db.scalar(select(MasterOpeningBalance))
            row.status = "WITHDRAWN"
            await db.commit()
        async with app.state.session_factory() as db:
            row = await db.scalar(select(MasterOpeningBalance))
            row.status = "PENDING"
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()

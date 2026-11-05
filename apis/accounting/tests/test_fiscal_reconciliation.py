import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import func, select

from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalYear
from accounting.models.ledger import DocumentSequence
from tests.conftest import COMPANY, TENANT, USER
from tests.test_fiscal_api import (
    BASE,
    FINANCE_PERMISSIONS,
    change,
    facts,
    finance_headers,
    fiscal_setup,
)


async def request(client: httpx.AsyncClient, **kwargs: object) -> httpx.Response:
    current = await client.get(BASE + "/financial-setup", headers=finance_headers())
    return await client.post(
        BASE + "/financial-setup/reconcile",
        json={
            "expected_version": current.json()["row_version"],
            "configuration_hash": "b" * 64,
            "reason": "Correct unused books",
        },
        headers=finance_headers(**kwargs),
    )


def revised(**changes: object):
    return facts().model_copy(update={"configuration_hash": "b" * 64, **changes})


async def test_reconciles_unused_books_preserving_calendar_ids_and_audit(client, app):
    periods = await fiscal_setup(client)
    await change(client, periods[0], "OPEN")
    updated = revised(books_begin_date=dt.date(2026, 10, 22), fiscal_year_start_month=1)
    key = str(uuid.uuid4())
    result = await request(client, finance=updated, key=key)
    assert result.status_code == 200, result.text
    assert result.json()["books_begin_date"] == "2026-10-22"
    assert result.json()["row_version"] == 2
    replay = await client.post(
        BASE + "/financial-setup/reconcile",
        json={
            "expected_version": 1,
            "configuration_hash": "b" * 64,
            "reason": "Correct unused books",
        },
        headers=finance_headers(finance=updated, key=key),
    )
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    revoked = await client.post(
        BASE + "/financial-setup/reconcile",
        json={
            "expected_version": 1,
            "configuration_hash": "b" * 64,
            "reason": "Correct unused books",
        },
        headers=finance_headers(
            finance=updated, key=key, permissions=FINANCE_PERMISSIONS - {"period.manage"}
        ),
    )
    assert revoked.status_code == 403, revoked.text
    refreshed = await client.get(
        BASE + "/fiscal-periods?limit=20", headers=finance_headers(finance=updated)
    )
    assert refreshed.status_code == 200, refreshed.text
    rows = sorted(refreshed.json()["items"], key=lambda row: row["start_date"])
    assert {p["id"] for p in rows} == {p["id"] for p in periods}
    assert rows[0]["start_date"] == "2026-01-01"
    assert rows[-1]["end_date"] == "2026-12-31"
    assert rows[0]["status"] == "OPEN" and rows[0]["row_version"] == 3
    history = await client.get(
        BASE + f"/history/fiscal-periods/{rows[0]['id']}",
        headers=finance_headers(finance=updated),
    )
    assert history.status_code == 200 and len(history.json()["items"]) == 3, history.text
    generated = await client.post(
        BASE + "/fiscal-years/generate",
        json={"start_year": 2027},
        headers=finance_headers(finance=updated),
    )
    assert generated.status_code == 200, generated.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Outbox)
                    .where(Outbox.event_type == "accounting.financial_setup.reconciled")
                )
                == 1
            )


@pytest.mark.parametrize("blocker", ["posted", "closed", "sequence", "opening"])
async def test_reconciliation_rejects_financial_dependencies_and_rolls_back(client, app, blocker):
    periods = await fiscal_setup(client)
    if blocker == "opening":
        created = await client.post(
            BASE + "/opening-batches",
            json={"posting_date": "2026-04-01", "description": "Pending opening"},
            headers=finance_headers(),
        )
        assert created.status_code == 201, created.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            if blocker == "posted":
                row = await db.scalar(select(FinancialSetup))
                row.first_posted_at = dt.datetime.now(dt.UTC)
            if blocker == "closed":
                row = await db.get(FiscalPeriod, uuid.UUID(periods[0]["id"]))
                row.status = "CLOSED"
            if blocker == "sequence":
                year = await db.scalar(select(FiscalYear))
                db.add(
                    DocumentSequence(
                        id=uuid.uuid4(),
                        tenant_id=TENANT,
                        company_id=COMPANY,
                        fiscal_year_id=year.id,
                        series_key="MANUAL",
                        next_value=1,
                        created_by=USER,
                        updated_by=USER,
                    )
                )
            await db.commit()
    result = await request(client, finance=revised(books_begin_date=dt.date(2026, 10, 22)))
    assert result.status_code == 409, result.text
    unchanged = await client.get(BASE + "/financial-setup", headers=finance_headers())
    assert unchanged.json()["books_begin_date"] == "2026-04-01"
    assert unchanged.json()["row_version"] == 1


async def test_reconciliation_requires_authority_current_hash_version_and_writable_fields(client):
    await fiscal_setup(client)
    invalid = await client.post(
        BASE + "/financial-setup/reconcile",
        json={
            "expected_version": 0,
            "configuration_hash": "invalid",
            "reason": "x",
            "books_begin_date": "2026-10-22",
        },
        headers=finance_headers(finance=revised()),
    )
    assert invalid.status_code == 422, invalid.text
    assert (
        await request(
            client,
            finance=revised(),
            permissions={"accounting.finance.read", "accounting.finance.initialize"},
        )
    ).status_code == 403
    assert (await request(client, finance=facts())).status_code == 409
    policy = {
        "entity_type": "accounting.financial_setup",
        "field_key": "books_begin_date",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await request(
            client, finance=revised(books_begin_date=dt.date(2026, 10, 22)), policies=[policy]
        )
    ).status_code == 403
    valid = await request(client, finance=revised())
    assert valid.status_code == 200, valid.text
    stale = await client.post(
        BASE + "/financial-setup/reconcile",
        json={"expected_version": 1, "configuration_hash": "b" * 64, "reason": "Stale correction"},
        headers=finance_headers(finance=revised()),
    )
    assert stale.status_code == 409


async def test_reconciliation_calendar_field_deny_rolls_back_all_records(client, app):
    periods = await fiscal_setup(client)
    policy = {
        "entity_type": "accounting.fiscal_period",
        "field_key": "start_date",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    result = await request(client, finance=revised(fiscal_year_start_month=1), policies=[policy])
    assert result.status_code == 403, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            year = await db.scalar(select(FiscalYear))
            assert year.start_date == dt.date(2026, 4, 1) and year.row_version == 1
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Outbox)
                    .where(
                        Outbox.event_type.in_(
                            [
                                "accounting.fiscal_year.update",
                                "accounting.financial_setup.reconciled",
                            ]
                        )
                    )
                )
                == 0
            )
    unchanged = await client.get(
        BASE + f"/fiscal-periods/{periods[0]['id']}", headers=finance_headers()
    )
    assert unchanged.json()["start_date"] == "2026-04-01"


@pytest.mark.parametrize("access_kind", ["unauthenticated", "tenant", "company", "read_deny"])
async def test_reconciliation_refuses_inaccessible_books(client, access_kind):
    await fiscal_setup(client)
    auth = finance_headers(finance=revised())
    if access_kind == "unauthenticated":
        auth = {}
    if access_kind == "tenant":
        auth = finance_headers(tenant=uuid.uuid4(), finance=revised())
    if access_kind == "company":
        auth = finance_headers(company=uuid.uuid4(), finance=revised())
    if access_kind == "read_deny":
        auth = finance_headers(
            finance=revised(),
            policies=[
                {
                    "entity_type": "accounting.financial_setup",
                    "field_key": "books_begin_date",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ],
        )
    response = await client.post(
        BASE + "/financial-setup/reconcile",
        json={
            "expected_version": 1,
            "configuration_hash": "b" * 64,
            "reason": "Denied correction",
        },
        headers=auth,
    )
    assert response.status_code in {401, 403, 409}, response.text

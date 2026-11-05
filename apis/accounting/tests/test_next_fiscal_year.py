"""Next-year preview is scoped, read-only and derived from frozen calendar facts."""

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from accounting.models.fiscal import FiscalPeriod, FiscalYear
from accounting.models.ledger import Journal
from accounting.models.subledger import OpeningBatch
from tests.conftest import TENANT
from tests.test_fiscal_api import BASE, change, facts, finance_headers, fiscal_setup


async def test_next_year_preview_uses_latest_calendar_and_reuses_existing_target(client):
    rows = await fiscal_setup(client)
    source_id = rows[0]["fiscal_year_id"]
    path = BASE + "/fiscal-years/next-preview"
    response = await client.get(path, headers=finance_headers())
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["source_year"]["id"] == source_id
    assert value["start_year"] == 2027
    assert value["start_date"] == "2027-04-01"
    assert value["end_date"] == "2028-03-31"
    assert value["existing_year_id"] is None
    assert len(value["periods"]) == 12
    assert value["blockers"] == []
    assert value["can_generate"] is True
    target = await client.post(
        BASE + "/fiscal-years/generate", json={"start_year": 2027}, headers=finance_headers()
    )
    assert target.status_code == 200, target.text
    same = await client.get(path + "?source_year_id=" + source_id, headers=finance_headers())
    assert same.status_code == 200, same.text
    assert same.json()["existing_year_id"] == target.json()["id"]
    assert all(period["status"] == "FUTURE" for period in same.json()["periods"])
    assert (await client.get(path, headers=finance_headers())).json()["start_year"] == 2028


@pytest.mark.parametrize("permissions", [set(), {"period.read"}, {"accounting.finance.read"}])
async def test_next_year_preview_requires_calendar_and_books_read(client, permissions):
    await fiscal_setup(client)
    response = await client.get(
        BASE + "/fiscal-years/next-preview", headers=finance_headers(permissions=permissions)
    )
    assert response.status_code == 403


async def test_next_year_preview_read_only_role_cannot_generate(client):
    await fiscal_setup(client)
    response = await client.get(
        BASE + "/fiscal-years/next-preview",
        headers=finance_headers(permissions={"period.read", "accounting.finance.read"}),
    )
    assert response.status_code == 200, response.text
    assert response.json()["can_generate"] is False


async def test_next_year_preview_denies_wrong_company_source_and_unknown_query(client):
    rows = await fiscal_setup(client)
    source = rows[0]["fiscal_year_id"]
    foreign = uuid.uuid4()
    response = await client.get(
        f"/v1/companies/{foreign}/fiscal-years/next-preview?source_year_id={source}",
        headers=finance_headers(company=foreign),
    )
    assert response.status_code == 403, response.text
    assert (await client.get(BASE + "/fiscal-years/next-preview")).status_code == 401
    assert (
        await client.get(
            BASE + "/fiscal-years/next-preview?source_year_id=invalid", headers=finance_headers()
        )
    ).status_code == 422
    assert (
        await client.get(
            BASE + "/fiscal-years/next-preview?unexpected=1", headers=finance_headers()
        )
    ).status_code == 422


@pytest.mark.parametrize(
    "change,blocker",
    [
        ({"company_active": False}, "COMPANY_INACTIVE"),
        ({"fiscal_year_start_month": 1}, "CONFIGURATION_CHANGED"),
    ],
)
async def test_next_year_preview_exposes_configuration_blockers(client, change, blocker):
    await fiscal_setup(client)
    response = await client.get(
        BASE + "/fiscal-years/next-preview",
        headers=finance_headers(finance=facts().model_copy(update=change)),
    )
    assert response.status_code == 200, response.text
    assert blocker in response.json()["blockers"]
    assert response.json()["can_generate"] is False


async def test_next_year_preview_requires_readable_date_fields(client):
    await fiscal_setup(client)
    policy = {
        "entity_type": "accounting.fiscal_year",
        "field_key": "end_date",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": BASE.split("/")[-1],
    }
    response = await client.get(
        BASE + "/fiscal-years/next-preview", headers=finance_headers(policies=[policy])
    )
    assert response.status_code == 403, response.text


async def test_next_year_preview_missing_books_is_actionable(client: httpx.AsyncClient):
    response = await client.get(BASE + "/fiscal-years/next-preview", headers=finance_headers())
    assert response.status_code == 404, response.text


async def test_next_year_preview_blocks_a_noncanonical_source_start(app, client):
    rows = await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            source = await db.get(FiscalYear, uuid.UUID(rows[0]["fiscal_year_id"]))
            source.start_date = dt.date(2026, 4, 2)
    result = await client.get(BASE + "/fiscal-years/next-preview", headers=finance_headers())
    assert result.status_code == 200, result.text
    assert "SOURCE_CALENDAR_MISMATCH" in result.json()["blockers"]
    assert result.json()["can_generate"] is False


async def test_two_year_start_preserves_open_books_and_does_not_create_annual_openings(app, client):
    rows = await fiscal_setup(client)
    assert (await change(client, rows[0], "OPEN")).status_code == 200
    batch = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Original zero opening"},
        headers=finance_headers(),
    )
    assert batch.status_code == 201, batch.text
    finalized = await client.post(
        BASE + f"/opening-batches/{batch.json()['id']}/finalize-zero",
        json={"expected_version": batch.json()["row_version"]},
        headers=finance_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    key = str(uuid.uuid4())
    target = await client.post(
        BASE + "/fiscal-years/generate", json={"start_year": 2027}, headers=finance_headers(key=key)
    )
    assert target.status_code == 200, target.text
    replay = await client.post(
        BASE + "/fiscal-years/generate", json={"start_year": 2027}, headers=finance_headers(key=key)
    )
    assert replay.status_code == 200 and replay.json()["id"] == target.json()["id"]
    periods = (
        await client.get(BASE + "/fiscal-periods?limit=50", headers=finance_headers())
    ).json()["items"]
    next_period = next(
        row
        for row in periods
        if row["fiscal_year_id"] == target.json()["id"] and row["sequence"] == 1
    )
    assert (await change(client, next_period, "OPEN")).status_code == 200
    for year_id in (rows[0]["fiscal_year_id"], target.json()["id"]):
        ready = await client.get(
            BASE + f"/fiscal-years/{year_id}/readiness", headers=finance_headers()
        )
        assert ready.status_code == 200 and ready.json()["ready_for_posting"] is True, ready.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(FiscalYear.id))) == 2
            assert await db.scalar(select(func.count(FiscalPeriod.id))) == 24
            assert await db.scalar(select(func.count(OpeningBatch.id))) == 1
            assert await db.scalar(select(func.count(Journal.id))) == 0

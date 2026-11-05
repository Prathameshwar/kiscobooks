"""Year uniqueness, overlap guards and close-only form permissions."""

import datetime as dt

import httpx
from billing_platform.db import tenant_scope
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.fiscal import FiscalYear
from tests.conftest import TENANT
from tests.test_fiscal_api import BASE, facts, finance_headers, fiscal_setup


async def test_close_only_actor_can_read_transition_fields_but_not_generate(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    headers = finance_headers(permissions={"period.read", "period.close"})
    result = await client.get(BASE + "/finance/field-sets/fiscal-periods", headers=headers)
    assert result.status_code == 200, result.text
    fields = {field["key"]: field for field in result.json()["fields"]}
    assert fields["status"]["writable"] and fields["reason"]["writable"]
    denied = await client.post(
        BASE + "/fiscal-years/generate", headers=headers, json={"start_year": 2027}
    )
    assert denied.status_code == 403


async def test_overlapping_existing_calendar_is_refused_without_duplicates(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await fiscal_setup(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(select(FiscalYear))
            row.end_date = dt.date(2028, 3, 31)
            await db.commit()
    result = await client.post(
        BASE + "/fiscal-years/generate", headers=finance_headers(), json={"start_year": 2027}
    )
    assert result.status_code == 409, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(FiscalYear.id))) == 1


async def test_year_generation_retries_keep_the_same_identity_and_bounds(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    ids = []
    for _ in range(2):
        response = await client.post(
            BASE + "/fiscal-years/generate", headers=finance_headers(), json={"start_year": 2026}
        )
        assert response.status_code == 200, response.text
        ids.append(response.json()["id"])
    assert ids[0] == ids[1]
    for value in [1899, 9998, 2026.5, "2026"]:
        response = await client.post(
            BASE + "/fiscal-years/generate", headers=finance_headers(), json={"start_year": value}
        )
        assert response.status_code == 422, response.text


async def test_fresh_company_bootstrap_is_narrow_and_replay_safe(client: httpx.AsyncClient) -> None:
    headers = finance_headers(
        permissions={
            "accounting.finance.read",
            "accounting.finance.initialize",
            "period.read",
            "period.manage",
        }
    )
    base = await client.post(BASE + "/accounting-setup/initialize", headers=headers, json={})
    assert base.status_code == 200, base.text
    result = await client.post(BASE + "/financial-setup/initialize", headers=headers, json={})
    assert result.status_code == 200, result.text
    year = await client.post(
        BASE + "/fiscal-years/generate", headers=headers, json={"start_year": 2026}
    )
    assert year.status_code == 200, year.text
    assert (
        await client.post(
            BASE + "/accounting-setup/install", headers=headers, json={"business_accounts": True}
        )
    ).status_code == 403
    assert (await client.get(BASE + "/accounting-setup", headers=headers)).status_code == 403


async def test_reconciliation_review_is_current_read_protected_and_does_not_write(
    client: httpx.AsyncClient,
) -> None:
    await fiscal_setup(client)
    changed = facts().model_copy(
        update={"books_begin_date": dt.date(2026, 10, 23), "configuration_hash": "b" * 64}
    )
    result = await client.get(
        BASE + "/financial-setup/reconciliation-review", headers=finance_headers(finance=changed)
    )
    assert result.status_code == 200, result.text
    review = result.json()
    assert review["configuration_hash"] == "b" * 64 and review["expected_version"] == 1
    assert {item["field"] for item in review["changes"]} == {
        "books_begin_date",
        "configuration_hash",
    }
    setup = await client.get(BASE + "/financial-setup", headers=finance_headers())
    assert setup.json()["books_begin_date"] == "2026-04-01"
    assert (
        await client.get(
            BASE + "/financial-setup/reconciliation-review",
            headers=finance_headers(permissions={"accounting.finance.read"}),
        )
    ).status_code == 403
    policy = {
        "entity_type": "accounting.financial_setup",
        "field_key": "books_begin_date",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": BASE.split("/")[3],
    }
    denied = await client.get(
        BASE + "/financial-setup/reconciliation-review", headers=finance_headers(policies=[policy])
    )
    assert denied.status_code == 403

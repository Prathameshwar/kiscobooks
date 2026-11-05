"""Fiscal API evidence, scope, field-policy and idempotency regressions."""

import datetime as dt
import uuid
from typing import Any, cast

import httpx
from billing_platform.company_context import FinancialContext
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalTransition, FiscalYear
from tests.conftest import COMPANY, PERMISSIONS, TENANT, headers
from tests.test_masters import prepare

BASE = f"/v1/companies/{COMPANY}"
FINANCE_PERMISSIONS = PERMISSIONS | {
    "accounting.finance.read",
    "accounting.finance.manage",
    "period.read",
    "period.manage",
    "period.post",
    "period.post_adjustment",
    "period.close",
    "period.reopen",
    "period.lock",
    "ledger.read",
}


def facts() -> FinancialContext:
    return FinancialContext(
        configuration_hash="a" * 64,
        company_active=True,
        books_begin_date=dt.date(2026, 4, 1),
        fiscal_year_start_month=4,
        fiscal_year_start_day=1,
        amount_precision=2,
        rounding_mode=RoundingMode.HALF_UP,
        default_payment_terms_days=30,
        timezone="Asia/Kolkata",
    )


def finance_headers(**kwargs: Any) -> dict[str, str]:
    values: dict[str, Any] = {"permissions": FINANCE_PERMISSIONS, "finance": facts()} | kwargs
    return headers(**values)


async def fiscal_setup(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    await prepare(client)
    initialized = await client.post(
        BASE + "/financial-setup/initialize", json={}, headers=finance_headers()
    )
    assert initialized.status_code == 200, initialized.text
    year = await client.post(
        BASE + "/fiscal-years/generate", json={"start_year": 2026}, headers=finance_headers()
    )
    assert year.status_code == 200, year.text
    result = await client.get(BASE + "/fiscal-periods?limit=20", headers=finance_headers())
    assert result.status_code == 200, result.text
    return cast(list[dict[str, Any]], result.json()["items"])


async def change(
    client: httpx.AsyncClient, row: dict[str, Any], status: str, **kwargs: Any
) -> httpx.Response:
    return await client.post(
        BASE + f"/fiscal-periods/{row['id']}/transition",
        json={
            "expected_version": row["row_version"],
            "status": status,
            "reason": "Reviewed period",
        },
        headers=finance_headers(**kwargs),
    )


async def test_narrow_bootstrap_grant_initializes_but_cannot_restate_openings(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    permissions = frozenset({"accounting.finance.read", "accounting.finance.initialize"})
    key = str(uuid.uuid4())
    path = BASE + "/financial-setup/initialize"
    result = await client.post(
        path, json={}, headers=finance_headers(permissions=permissions, key=key)
    )
    assert result.status_code == 200, result.text
    replay = await client.post(
        path, json={}, headers=finance_headers(permissions=permissions, key=key)
    )
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    revoked = await client.post(
        path, json={}, headers=finance_headers(permissions={"accounting.finance.read"}, key=key)
    )
    assert revoked.status_code == 403
    opening = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Restricted bootstrap"},
        headers=finance_headers(permissions=permissions),
    )
    assert opening.status_code == 403, opening.text


async def test_fiscal_setup_generation_transitions_and_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    rows = await fiscal_setup(client)
    assert len(rows) == 12 and all(row["status"] == "FUTURE" for row in rows)
    assert rows[0]["start_date"] == "2026-04-01" and rows[-1]["end_date"] == "2027-03-31"
    row = rows[0]
    row = (await change(client, row, "OPEN")).json()
    opening = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero opening"},
        headers=finance_headers(),
    )
    assert opening.status_code == 201, opening.text
    finalized = await client.post(
        BASE + f"/opening-batches/{opening.json()['id']}/finalize-zero",
        json={"expected_version": opening.json()["row_version"]},
        headers=finance_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    for status in ("SOFT_CLOSED", "CLOSED", "OPEN", "SOFT_CLOSED", "CLOSED", "LOCKED"):
        result = await change(client, row, status)
        assert result.status_code == 200, result.text
        row = result.json()
    assert (await change(client, row, "OPEN")).status_code == 409
    history = await client.get(
        BASE + f"/history/fiscal-periods/{row['id']}", headers=finance_headers()
    )
    assert history.status_code == 200 and len(history.json()["items"]) == 8, history.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            transitions = list(await db.scalars(select(FiscalTransition)))
            assert len(transitions) == 7
            assert transitions[-1].to_status == "LOCKED"
            assert transitions[-1].created_by is not None
    setup = await client.get(BASE + "/financial-setup", headers=finance_headers())
    assert setup.status_code == 200 and setup.json()["base_currency"] == "INR"
    fields = await client.get(
        BASE + "/finance/field-sets/fiscal-periods", headers=finance_headers()
    )
    assert fields.status_code == 200, fields.text


async def test_period_replay_requires_original_transition_permission(
    client: httpx.AsyncClient,
) -> None:
    rows = await fiscal_setup(client)
    key = str(uuid.uuid4())
    result = await change(client, rows[0], "OPEN", key=key)
    assert result.status_code == 200, result.text
    replay = await change(client, rows[0], "OPEN", key=key)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    revoked = await change(
        client, rows[0], "OPEN", key=key, permissions=frozenset({"period.read", "period.reopen"})
    )
    assert revoked.status_code == 403, revoked.text


async def test_fiscal_authority_validation_and_sequential_close(client: httpx.AsyncClient) -> None:
    rows = await fiscal_setup(client)
    path = BASE + "/fiscal-years/generate"
    assert (await client.post(path, json={"start_year": 2026})).status_code == 401
    assert (
        await client.post(path, json={"start_year": 2026}, headers=headers())
    ).status_code == 409
    assert (
        await client.post(
            path, json={"start_year": 2026}, headers=finance_headers(permissions=set())
        )
    ).status_code == 403
    for body in (
        {"start_year": 1800},
        {"start_year": 2026, "status": "OPEN"},
        {"start_year": 2026.0},
    ):
        assert (await client.post(path, json=body, headers=finance_headers())).status_code == 422
    row2 = await change(client, rows[1], "OPEN")
    assert row2.status_code == 200
    assert (await change(client, row2.json(), "SOFT_CLOSED")).status_code == 409
    assert (await change(client, rows[0], "CLOSED")).status_code == 409
    assert (
        await change(client, rows[0], "OPEN", permissions=frozenset({"period.read"}))
    ).status_code == 403
    stale = dict(rows[0], row_version=50)
    assert (await change(client, stale, "OPEN")).status_code == 409
    assert (
        await client.get(
            BASE + "/fiscal-years?fiscal_year_id=" + rows[0]["fiscal_year_id"],
            headers=finance_headers(),
        )
    ).status_code == 422


async def test_generation_is_unique_and_paginates_with_bound_authority(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    rows = await fiscal_setup(client)
    for _ in range(2):
        result = await client.post(
            BASE + "/fiscal-years/generate", json={"start_year": 2026}, headers=finance_headers()
        )
        assert result.status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(FiscalYear.id))) == 1
            assert await db.scalar(select(func.count(FiscalPeriod.id))) == 12
    first = await client.get(BASE + "/fiscal-periods?limit=5", headers=finance_headers())
    assert first.status_code == 200
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        BASE + "/fiscal-periods", params={"limit": 5, "cursor": cursor}, headers=finance_headers()
    )
    assert second.status_code == 200, second.text
    assert {r["id"] for r in first.json()["items"]}.isdisjoint(
        r["id"] for r in second.json()["items"]
    )
    filtered = await client.get(
        BASE + "/fiscal-periods",
        params={"fiscal_year_id": rows[0]["fiscal_year_id"]},
        headers=finance_headers(),
    )
    assert filtered.status_code == 200 and len(filtered.json()["items"]) == 12


async def test_financial_field_denies_and_rollback(client: httpx.AsyncClient, app: FastAPI) -> None:
    rows = await fiscal_setup(client)
    policy = {
        "entity_type": "accounting.fiscal_period",
        "field_key": "status",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    result = await change(client, rows[0], "OPEN", policies=[policy])
    assert result.status_code == 403, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(FiscalTransition.id))) == 0
    policy["access"] = "read"
    listing = await client.get(BASE + "/fiscal-periods", headers=finance_headers(policies=[policy]))
    assert listing.status_code == 200 and "status" not in listing.json()["items"][0]
    filtered = await client.get(
        BASE + "/fiscal-periods?status=FUTURE", headers=finance_headers(policies=[policy])
    )
    assert filtered.status_code == 403
    detail = await client.get(
        BASE + "/fiscal-periods/" + rows[0]["id"], headers=finance_headers(policies=[policy])
    )
    assert detail.status_code == 200 and "status" not in detail.json()


async def test_fiscal_scope_and_snapshot_drift(client: httpx.AsyncClient) -> None:
    rows = await fiscal_setup(client)
    company = uuid7()
    foreign_path = f"/v1/companies/{company}/fiscal-periods/{rows[0]['id']}"
    assert (
        await client.get(foreign_path, headers=finance_headers(company=company))
    ).status_code == 403
    assert (
        await client.get(
            BASE + "/fiscal-periods/" + rows[0]["id"], headers=finance_headers(tenant=uuid7())
        )
    ).status_code == 404
    drift = facts().model_copy(update={"books_begin_date": dt.date(2026, 5, 1)})
    result = await client.post(
        BASE + "/fiscal-years/generate",
        json={"start_year": 2027},
        headers=finance_headers(finance=drift),
    )
    assert result.status_code == 409
    absent = await client.get(
        f"/v1/companies/{company}/financial-setup", headers=finance_headers(company=company)
    )
    assert absent.status_code == 404


async def test_all_fiscal_models_are_tenant_filtered(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    rows = await fiscal_setup(client)
    assert (await change(client, rows[0], "OPEN")).status_code == 200
    for tenant, expected in ((TENANT, True), (uuid7(), False)):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                for model in (FinancialSetup, FiscalYear, FiscalPeriod, FiscalTransition):
                    assert bool(list(await db.scalars(select(model)))) is expected


async def test_close_requires_initial_opening_and_readiness_uses_frozen_settings(
    client: httpx.AsyncClient,
) -> None:
    rows = await fiscal_setup(client)
    first = (await change(client, rows[0], "OPEN")).json()
    year_id = rows[0]["fiscal_year_id"]
    path = BASE + f"/fiscal-years/{year_id}/readiness"
    before = await client.get(path, headers=finance_headers())
    assert before.status_code == 200, before.text
    assert "OPENING_NOT_FINALIZED" in before.json()["close_blockers"]
    assert (await change(client, first, "SOFT_CLOSED")).status_code == 409

    batch = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero opening"},
        headers=finance_headers(),
    )
    assert batch.status_code == 201, batch.text
    finalized = await client.post(
        BASE + f"/opening-batches/{batch.json()['id']}/finalize-zero",
        json={"expected_version": batch.json()["row_version"]},
        headers=finance_headers(),
    )
    assert finalized.status_code == 200, finalized.text

    # Feature/configuration changes and the current timezone do not change frozen books.
    mutable = facts().model_copy(update={"configuration_hash": "b" * 64, "timezone": "UTC"})
    ready = await client.get(path, headers=finance_headers(finance=mutable))
    assert ready.status_code == 200, ready.text
    assert ready.json()["ready_for_posting"] is True
    assert "CONFIGURATION_CHANGED" not in ready.json()["blockers"]
    assert (await change(client, first, "SOFT_CLOSED", finance=mutable)).status_code == 200

    changed_books = facts().model_copy(update={"books_begin_date": dt.date(2026, 5, 1)})
    drift = await client.get(path, headers=finance_headers(finance=changed_books))
    assert drift.status_code == 200
    assert "CONFIGURATION_CHANGED" in drift.json()["blockers"]
    inactive = facts().model_copy(update={"company_active": False})
    inactive_readiness = await client.get(path, headers=finance_headers(finance=inactive))
    assert inactive_readiness.status_code == 200
    assert "COMPANY_INACTIVE" in inactive_readiness.json()["blockers"]


async def test_opening_cannot_be_reopened_behind_later_closed_books(
    client: httpx.AsyncClient,
) -> None:
    rows = await fiscal_setup(client)
    first = (await change(client, rows[0], "OPEN")).json()
    batch = await client.post(
        BASE + "/opening-batches",
        json={"posting_date": "2026-04-01", "description": "Zero opening"},
        headers=finance_headers(),
    )
    assert batch.status_code == 201, batch.text
    finalized = await client.post(
        BASE + f"/opening-batches/{batch.json()['id']}/finalize-zero",
        json={"expected_version": batch.json()["row_version"]},
        headers=finance_headers(),
    )
    assert finalized.status_code == 200, finalized.text
    for status in ("SOFT_CLOSED", "CLOSED"):
        first = (await change(client, first, status)).json()
    second = (await change(client, rows[1], "OPEN")).json()
    for status in ("SOFT_CLOSED", "CLOSED"):
        second = (await change(client, second, status)).json()
    assert second["status"] == "CLOSED"
    first = (await change(client, first, "OPEN")).json()
    assert first["status"] == "OPEN"
    correction = await client.post(
        BASE + f"/opening-batches/{batch.json()['id']}/reopen-zero",
        json={
            "expected_version": finalized.json()["row_version"],
            "reason": "Recheck opening",
        },
        headers=finance_headers(),
    )
    assert correction.status_code == 409, correction.text

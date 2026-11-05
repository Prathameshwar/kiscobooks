"""Company creation supplies applicable ledgers without duplicating business effects."""

import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models import masters as m
from accounting.models.fiscal import FinancialSetup
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import BASE, finance_headers

COMMON = {
    "DISCOUNT_ALLOWED": "INDIRECT_EXPENSES",
    "DISCOUNT_RECEIVED": "INDIRECT_INCOME",
    "PURCHASE_RETURNS": "PURCHASES",
    "FREIGHT_INWARD": "DIRECT_EXPENSES",
    "FREIGHT_OUTWARD": "INDIRECT_EXPENSES",
    "GATEWAY_CLEARING": "CURRENT_ASSETS",
    "POS_CLEARING": "CURRENT_ASSETS",
    "MERCHANT_FEES": "INDIRECT_EXPENSES",
    "OPENING_BALANCE_OFFSET": "CAPITAL",
    "MIGRATION_CLEARING": "CURRENT_ASSETS",
}


def registration(system: str = "gst_in", regime: str = "regular", **extra: Any) -> dict[str, Any]:
    return {
        "id": str(uuid7()),
        "tax_system": system,
        "regime": regime,
        "jurisdiction_code": "IN-MH" if system == "gst_in" else "GB",
        "valid_from": "2026-04-01",
        "valid_to": None,
    } | extra


async def initialize(client: httpx.AsyncClient, **context: Any) -> None:
    auth = finance_headers(**context)
    for path in ("accounting-setup/initialize", "financial-setup/initialize"):
        result = await client.post(BASE + "/" + path, json={}, headers=auth)
        assert result.status_code == 200, result.text


async def state(app: FastAPI) -> dict[str, tuple[str, str]]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = await db.execute(
                select(m.Account.code, m.Account.id, m.AccountGroup.code)
                .join(m.AccountGroup, m.Account.group_id == m.AccountGroup.id)
                .where(m.Account.company_id == COMPANY)
            )
            return {code: (str(identifier), group) for code, identifier, group in rows}


async def test_new_company_gets_high_priority_accounts_and_repeats_keep_ids(client, app):
    await initialize(client)
    first = await state(app)
    assert {code: first[code][1] for code in COMMON} == COMMON
    assert len(first) == 22
    await initialize(client)
    assert await state(app) == first


async def test_inventory_company_gets_cogs_and_dated_mapping(client, app):
    await initialize(client, features={"inventory"})
    rows = await state(app)
    assert rows["COST_OF_GOODS"][1] == "DIRECT_EXPENSES"
    assert len(rows) == 28
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            mapping = await db.scalar(
                select(m.AccountPostingMapping).where(
                    m.AccountPostingMapping.purpose == "COST_OF_GOODS"
                )
            )
            assert str(mapping.account_id) == rows["COST_OF_GOODS"][0]
            assert mapping.valid_from == dt.date(2026, 4, 1)


async def test_registered_inventory_bootstrap_can_exceed_normal_command_deadline(
    client, app, monkeypatch
):
    from accounting.tasks import default_accounts

    original = default_accounts.provision
    attempts = 0

    async def slower_provision(*args):
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(10.1)
        await original(*args)

    monkeypatch.setattr(default_accounts, "provision", slower_provision)
    auth = finance_headers(registrations=[registration()], features={"inventory"})
    chart = await client.post(BASE + "/accounting-setup/initialize", json={}, headers=auth)
    assert chart.status_code == 200, chart.text
    books = await client.post(BASE + "/financial-setup/initialize", json={}, headers=auth)
    assert books.status_code == 200, books.text
    first = await state(app)
    assert len(first) == 41  # Common, stock, COGS and GST accounts commit together.
    replay = await client.post(BASE + "/financial-setup/initialize", json={}, headers=auth)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert attempts == 1 and await state(app) == first


@pytest.mark.parametrize(
    "system,regime,components",
    [
        ("gst_in", "regular", {"CGST", "SGST", "IGST", "CESS"}),
        ("vat_gb", "standard", {"VAT"}),
    ],
)
async def test_registered_company_gets_tax_profiles_and_replay_safe_accounts(
    client, app, system, regime, components
):
    reg = registration(system, regime)
    await initialize(client, registrations=[reg])
    first = await state(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            profiles = list(await db.scalars(select(m.AccountTaxProfile)))
            assert {p.component for p in profiles} == components
            assert {p.purpose for p in profiles} >= {"INPUT_RECOVERABLE", "OUTPUT_PAYABLE"}
            assert {str(p.company_registration_id) for p in profiles} == {reg["id"]}
            assert all(p.scheme == ("GST_IN" if system == "gst_in" else "VAT") for p in profiles)
    await initialize(client, registrations=[reg])
    assert await state(app) == first


async def test_non_tax_company_has_no_tax_profiles_or_cogs(client, app):
    await initialize(client)
    assert "COST_OF_GOODS" not in await state(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(m.AccountTaxProfile.id)) is None


async def test_later_registration_adds_tax_defaults_without_duplicating_the_chart(client, app):
    await initialize(client)
    first = await state(app)
    reg = registration()
    await initialize(client, registrations=[reg])
    after = await state(app)
    assert all(after[code] == value for code, value in first.items())
    assert len(after) == 35  # 22 common + 12 GST profiles + payment control.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            groups = list(await db.scalars(select(m.AccountGroup)))
            assert len(groups) == 29
            mappings = list(await db.scalars(select(m.AccountPostingMapping)))
            assert len(mappings) == 12
            assert {str(row.company_registration_id) for row in mappings} == {reg["id"]}


async def test_tax_field_denial_rolls_back_books_defaults_and_audit(client, app):
    reg = registration()
    # The first transaction is the independently owned chart step.
    result = await client.post(
        BASE + "/accounting-setup/initialize", json={}, headers=finance_headers()
    )
    assert result.status_code == 200
    baseline = await state(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            original_audit = set(await db.scalars(select(Outbox.id)))
    policies = [
        {
            "entity_type": "accounting.account_tax_profile",
            "field_key": "component",
            "access": "write",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    result = await client.post(
        BASE + "/financial-setup/initialize",
        json={},
        headers=finance_headers(registrations=[reg], policies=policies),
    )
    assert result.status_code == 403, result.text
    assert await state(app) == baseline
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(FinancialSetup.id)) is None
            assert await db.scalar(select(m.AccountTaxProfile.id)) is None
            assert set(await db.scalars(select(Outbox.id))) == original_audit
            assert (
                await db.scalar(
                    select(m.AccountGroup.id).where(m.AccountGroup.code == "TAX_RECOVERABLE")
                )
                is None
            )


async def test_defaults_work_under_only_company_bootstrap_authority(client, app):
    await initialize(
        client,
        registrations=[registration()],
        features={"inventory", "tds"},
        permissions={"accounting.finance.initialize", "accounting.finance.read"},
    )
    assert "COST_OF_GOODS" in await state(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            group = await db.scalar(
                select(m.AccountGroup.id).where(m.AccountGroup.code == "DIRECT_EXPENSES")
            )
    denied = await client.post(
        BASE + "/accounts",
        json={
            "code": "ARBITRARY",
            "name": "Arbitrary account",
            "group_id": str(group),
            "kind": "GENERAL",
        },
        headers=finance_headers(permissions={"accounting.finance.initialize"}),
    )
    assert denied.status_code == 403


async def test_multiple_registrations_keep_distinct_accounts_and_one_group(client, app):
    regs = [registration(), registration(jurisdiction_code="IN-KA")]
    await initialize(client, registrations=regs)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            profiles = list(await db.scalars(select(m.AccountTaxProfile)))
            assert len(profiles) == 24 and len({p.account_id for p in profiles}) == 24
            assert {str(p.company_registration_id) for p in profiles} == {r["id"] for r in regs}
            assert (
                len(
                    list(
                        await db.scalars(
                            select(m.AccountGroup).where(m.AccountGroup.code == "TAX_RECOVERABLE")
                        )
                    )
                )
                == 1
            )


async def test_conflicting_cogs_account_fails_without_partial_books(client, app):
    await client.post(BASE + "/accounting-setup/initialize", json={}, headers=finance_headers())
    before = await state(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            group = await db.scalar(
                select(m.AccountGroup.id).where(m.AccountGroup.code == "INDIRECT_EXPENSES")
            )
            db.add(
                m.Account(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    code="COST_OF_GOODS",
                    name="Authored account",
                    group_id=group,
                    kind="GENERAL",
                    status="ACTIVE",
                    currency_mode="BASE",
                    row_version=1,
                )
            )
    result = await client.post(
        BASE + "/financial-setup/initialize",
        json={},
        headers=finance_headers(features={"inventory"}),
    )
    assert result.status_code == 409, result.text
    after = await state(app)
    assert set(after) == set(before) | {"COST_OF_GOODS"}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(FinancialSetup.id)) is None


async def test_repeated_setup_preserves_operator_mapping_and_does_not_post_money(client, app):
    from accounting.models.ledger import Journal

    await initialize(client, features={"inventory"})
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            mapping = await db.scalar(
                select(m.AccountPostingMapping).where(
                    m.AccountPostingMapping.purpose == "COST_OF_GOODS"
                )
            )
            custom = await db.scalar(
                select(m.Account.id).where(m.Account.code == "NONSTOCK_PURCHASES")
            )
            mapping.account_id = custom
            original_id = mapping.id
    await initialize(client, features={"inventory"})
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            mappings = list(
                await db.scalars(
                    select(m.AccountPostingMapping).where(
                        m.AccountPostingMapping.purpose == "COST_OF_GOODS"
                    )
                )
            )
            assert [(row.id, row.account_id) for row in mappings] == [(original_id, custom)]
            assert await db.scalar(select(Journal.id)) is None


async def test_inventory_utgst_rcm_and_withholding_defaults_work_together(client, app, monkeypatch):
    from accounting.tasks import voucher_tax

    reference = Path(__file__).resolve().parents[3] / "start/win/conf/utgst-states.json"
    configured = json.loads(reference.read_text())["states"]
    # Use the launcher's real configuration; restore the process-global setting afterward.
    monkeypatch.setattr(voucher_tax, "_UTGST", voucher_tax.utgst_states())
    voucher_tax.configure(configured)
    reg = registration(jurisdiction_code="IN-CH")
    features = {"inventory", "reverse_charge", "tds", "tcs"}
    await initialize(client, registrations=[reg], features=features)
    first = await state(app)
    assert len(first) == 49
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            profiles = list(await db.scalars(select(m.AccountTaxProfile)))
            gst = [profile for profile in profiles if profile.scheme == "GST_IN"]
            assert len(gst) == 16
            assert {p.component for p in gst} == {"CGST", "UTGST", "IGST", "CESS"}
            assert {p.purpose for p in gst} == {
                "INPUT_RECOVERABLE",
                "INPUT_PENDING",
                "OUTPUT_PAYABLE",
                "RCM_PAYABLE",
            }
            assert {p.duty_type for p in profiles if p.scheme == "OTHER"} == {"TDS", "TCS"}
            assert len(list(await db.scalars(select(m.AccountPostingMapping)))) == 21
    await initialize(client, registrations=[reg], features=features)
    assert await state(app) == first

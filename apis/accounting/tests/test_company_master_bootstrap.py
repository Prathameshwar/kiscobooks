"""Company-owned default charts: atomic, scoped and safe after later management."""

import base64
import hashlib
import hmac
import json

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.domain.master_metadata import METADATA_VERSION
from accounting.models import masters as m
from accounting.seeds.templates import BUSINESS, CORE, GROUPS
from tests.conftest import COMPANY, SECRET, TENANT, headers
from tests.test_fiscal_api import BASE, finance_headers

BOOTSTRAP = {"accounting.finance.read", "accounting.finance.initialize"}


async def test_initialization_creates_complete_company_chart_with_narrow_authority(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    result = await client.post(
        BASE + "/accounting-setup/initialize",
        headers=finance_headers(permissions=BOOTSTRAP),
        json={},
    )
    assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            heads = list(await db.scalars(select(m.AccountHead)))
            groups = list(await db.scalars(select(m.AccountGroup)))
            accounts = list(await db.scalars(select(m.Account)))
            assert len(heads) == 5
            assert {row.code for row in groups} == {row[0] for row in GROUPS}
            assert {row.code for row in accounts} == {row[0] for row in (*CORE, *BUSINESS)}
            assert all(row.company_id == COMPANY and row.status == "ACTIVE" for row in accounts)
            assert all(row.currency_mode == "BASE" and row.currency is None for row in accounts)
            assert await db.scalar(select(m.AccountTemplateInstallation.id)) is not None

    # Provisioning a fixed chart grants no general master or tax authoring authority.
    denied = await client.post(
        BASE + "/accounting-setup/install",
        headers=finance_headers(permissions=BOOTSTRAP),
        json={"business_accounts": True},
    )
    assert denied.status_code == 403


async def test_retries_preserve_identities_and_later_master_edits(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    auth = finance_headers(permissions=BOOTSTRAP)
    path = BASE + "/accounting-setup/initialize"
    first = await client.post(path, headers=auth, json={})
    assert first.status_code == 200, first.text
    cash = (await client.get(BASE + "/accounts?code=CASH_MAIN", headers=headers())).json()["items"][
        0
    ]
    changed = await client.patch(
        BASE + "/accounts/" + cash["id"],
        headers=headers(),
        json={"name": "Office Cash", "expected_version": cash["row_version"]},
    )
    assert changed.status_code == 200, changed.text
    replay = await client.post(path, headers=auth, json={})
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    another = await client.post(path, headers=finance_headers(permissions=BOOTSTRAP), json={})
    assert another.status_code == 200 and another.json()["id"] == first.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(m.Account)))
            assert len(rows) == 22
            assert next(row for row in rows if row.code == "CASH_MAIN").name == "Office Cash"
            assert len(list(await db.scalars(select(m.AccountTemplateInstallation)))) == 1
    revoked = await client.post(
        path,
        headers=finance_headers(
            permissions={"accounting.finance.read"}, key=auth["Idempotency-Key"]
        ),
        json={},
    )
    assert revoked.status_code == 403


async def test_field_denial_rolls_back_entire_chart_and_audit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    auth = finance_headers(
        permissions=BOOTSTRAP,
        policies=[
            {
                "entity_type": "accounting.account",
                "field_key": "name",
                "access": "write",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ],
    )
    failed = await client.post(BASE + "/accounting-setup/initialize", headers=auth, json={})
    assert failed.status_code == 403, failed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for model in (
                m.AccountingSetup,
                m.AccountHead,
                m.AccountGroup,
                m.Account,
                m.AccountTemplateInstallation,
                Outbox,
            ):
                assert await db.scalar(select(model.id).limit(1)) is None
    repaired = await client.post(
        BASE + "/accounting-setup/initialize",
        headers=finance_headers(permissions=BOOTSTRAP, key=auth["Idempotency-Key"]),
        json={},
    )
    assert repaired.status_code == 200, repaired.text


async def test_default_charts_are_separate_for_each_company_and_tenant(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    other_company, other_tenant = uuid7(), uuid7()
    for company, tenant in ((COMPANY, TENANT), (other_company, TENANT), (uuid7(), other_tenant)):
        result = await client.post(
            f"/v1/companies/{company}/accounting-setup/initialize",
            headers=finance_headers(permissions=BOOTSTRAP, company=company, tenant=tenant),
            json={},
        )
        assert result.status_code == 200, result.text
    wrong = await client.post(
        f"/v1/companies/{other_company}/accounting-setup/initialize",
        headers=finance_headers(permissions=BOOTSTRAP),
        json={},
    )
    assert wrong.status_code == 401  # Signed company context does not match the requested company.
    wrong_scope = finance_headers(permissions=BOOTSTRAP, company=other_company)
    actor = json.loads(base64.urlsafe_b64decode(wrong_scope["X-Actor-Context"] + "=="))
    actor["grants"][0]["scope_id"] = str(COMPANY)
    payload = json.dumps(actor, separators=(",", ":")).encode()
    wrong_scope["X-Actor-Context"] = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    wrong_scope["X-Actor-Signature"] = hmac.new(
        SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    denied = await client.post(
        f"/v1/companies/{other_company}/accounting-setup/initialize",
        headers=wrong_scope,
        json={},
    )
    assert denied.status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            groups = list(await db.scalars(select(m.AccountGroup)))
            accounts = list(await db.scalars(select(m.Account)))
            assert len(groups) == 56 and len(accounts) == 44
            owner = {row.id: row.company_id for row in groups}
            assert all(owner[row.group_id] == row.company_id for row in accounts)
            assert {row.tenant_id for row in groups + accounts} == {TENANT}


async def test_empty_legacy_setup_catches_up_but_authored_chart_is_preserved(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                m.AccountingSetup(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    base_currency="INR",
                    metadata_version=METADATA_VERSION,
                    generation=1,
                    row_version=1,
                )
            )
            for code in ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"):
                db.add(
                    m.AccountHead(
                        id=uuid7(),
                        tenant_id=TENANT,
                        company_id=COMPANY,
                        code=code,
                        name=code.title(),
                        nature=code,
                        row_version=1,
                    )
                )
    result = await client.post(
        BASE + "/accounting-setup/initialize",
        headers=finance_headers(permissions=BOOTSTRAP),
        json={},
    )
    assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            assert len(list(await db.scalars(select(m.AccountGroup)))) == 28
            # Model a pre-existing user-managed chart with no installation receipt.
            for model in (m.AccountTemplateBinding, m.AccountTemplateInstallation):
                for row in list(await db.scalars(select(model))):
                    await db.delete(row)
                await db.flush()
            group = await db.scalar(select(m.AccountGroup).where(m.AccountGroup.code == "CASH"))
            group.name = "Our Cash Group"
    result = await client.post(
        BASE + "/accounting-setup/initialize",
        headers=finance_headers(permissions=BOOTSTRAP),
        json={},
    )
    assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(m.AccountTemplateInstallation.id)) is None
            group = await db.scalar(select(m.AccountGroup).where(m.AccountGroup.code == "CASH"))
            assert group.name == "Our Cash Group"

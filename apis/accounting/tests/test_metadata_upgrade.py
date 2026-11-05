"""Existing identities survive data backfill and the versioned chart correction."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from accounting.seeds.master_metadata import backfill_company
from accounting.tasks.commands import rebuild_hierarchy
from tests.conftest import COMPANY, TENANT, USER, headers
from tests.test_group_completion import installed_groups
from tests.test_masters import BASE, activate, post


async def test_metadata_backfill_refuses_wrong_scope_versions_and_invalid_hierarchy(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = {row["code"]: row for row in await installed_groups(client)}
    factory = app.state.session_factory
    with pytest.raises(ConflictError, match="unavailable"):
        await backfill_company(factory, tenant_id=uuid7(), company_id=COMPANY, actor_id=USER)
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            setup = await db.scalar(select(m.AccountingSetup))
            assert setup is not None
            setup.metadata_version = 2
    with pytest.raises(ConflictError, match="unsupported"):
        await backfill_company(factory, tenant_id=TENANT, company_id=COMPANY, actor_id=USER)
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            setup = await db.scalar(select(m.AccountingSetup))
            assert setup is not None
            setup.metadata_version = 0
            parent = await db.get(m.AccountGroup, uuid.UUID(groups["CURRENT_ASSETS"]["id"]))
            assert parent is not None
            parent.parent_id = uuid.UUID(groups["CASH"]["id"])
    with pytest.raises(ConflictError, match="cycle"):
        await backfill_company(factory, tenant_id=TENANT, company_id=COMPANY, actor_id=USER)
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            setup = await db.scalar(select(m.AccountingSetup))
            assert setup is not None and setup.metadata_version == 0
            assert not list(
                await db.scalars(
                    select(MasterRevision).where(MasterRevision.action == "metadata_upgrade")
                )
            )
            parent = await db.get(m.AccountGroup, uuid.UUID(groups["CURRENT_ASSETS"]["id"]))
            assert parent is not None
            parent.parent_id = None
    # Already-correct groups need no rewrites; the marker still advances exactly once.
    assert await backfill_company(factory, tenant_id=TENANT, company_id=COMPANY, actor_id=USER) == 0


async def test_metadata_backfill_blocks_reads_then_audits_once(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await installed_groups(client)
    factory = app.state.session_factory
    with tenant_scope(TENANT):
        async with factory() as db, db.begin():
            setup = await db.scalar(
                select(m.AccountingSetup).where(m.AccountingSetup.company_id == COMPANY)
            )
            assert setup is not None
            setup.metadata_version = 0
            for row in await db.scalars(
                select(m.AccountGroup).where(m.AccountGroup.company_id == COMPANY)
            ):
                row.is_primary = False
                row.is_reserved = False
                row.affects_gross_profit = False
    result = await client.get(BASE + "/account-groups", headers=headers())
    assert result.status_code == 409, result.text
    assert (
        await backfill_company(factory, tenant_id=TENANT, company_id=COMPANY, actor_id=USER) == 28
    )
    assert await backfill_company(factory, tenant_id=TENANT, company_id=COMPANY, actor_id=USER) == 0
    result = await client.get(BASE + "/account-groups", headers=headers())
    assert result.status_code == 200, result.text
    assert {r["id"] for r in result.json()["items"]} == {r["id"] for r in groups}
    assert sum(r["is_primary"] for r in result.json()["items"]) == 15
    with tenant_scope(TENANT):
        async with factory() as db:
            audits = list(
                await db.scalars(
                    select(MasterRevision).where(
                        MasterRevision.company_id == COMPANY,
                        MasterRevision.action == "metadata_upgrade",
                    )
                )
            )
            assert len(audits) == 1


async def test_pending_metadata_also_blocks_command_replays(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    initialize_headers = headers()
    await post(client, "/accounting-setup/initialize", {}, h=initialize_headers, status=200)
    install_headers = headers()
    await post(
        client,
        "/accounting-setup/install",
        {"business_accounts": False},
        h=install_headers,
        status=200,
    )
    create_headers = headers()
    party_body = {
        "code": "REPLAY",
        "name": "Replay",
        "legal_name": "Replay",
        "country_code": "IN",
        "role": "SUPPLIER",
    }
    await post(client, "/parties/create-with-details", party_body, h=create_headers)
    # The generic import no longer creates parties (they arrive with a role and an account), so
    # the replayed import carries another master.
    import_body = {
        "items": [
            {
                "key": "term",
                "resource": "payment-terms",
                "values": {"code": "IMPORT_REPLAY", "name": "Import replay"},
            }
        ]
    }
    preview = await post(client, "/imports/preview", import_body, status=200)
    apply_body = import_body | {"preview_token": preview["preview_token"]}
    import_headers = headers()
    await post(client, "/imports/apply", apply_body, h=import_headers, status=200)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            setup = await db.scalar(
                select(m.AccountingSetup).where(m.AccountingSetup.company_id == COMPANY)
            )
            assert setup is not None
            setup.metadata_version = 0
    for path, body, original_headers in [
        ("/accounting-setup/initialize", {}, initialize_headers),
        ("/accounting-setup/install", {"business_accounts": False}, install_headers),
        ("/parties/create-with-details", party_body, create_headers),
        ("/imports/apply", apply_body, import_headers),
    ]:
        response = await client.post(BASE + path, json=body, headers=original_headers)
        assert response.status_code == 409, (path, response.text)


@pytest.mark.parametrize("used", [False, True])
async def test_legacy_reserves_upgrade_preview_and_atomic_conflict(
    client: httpx.AsyncClient, app: FastAPI, used: bool
) -> None:
    groups = {r["code"]: r for r in await installed_groups(client)}
    reserves = groups["RESERVES"]
    account = await post(
        client,
        "/accounts",
        {"code": "LEGACY_RESERVE", "name": "Retained reserve", "group_id": reserves["id"]},
    )
    account = await activate(client, "/accounts", account)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.AccountGroup, uuid.UUID(reserves["id"]))
            assert row is not None
            row.parent_id = None
            row.is_primary = True
            row.name = "My reserve name"
            installation = await db.scalar(
                select(m.AccountTemplateInstallation).where(
                    m.AccountTemplateInstallation.company_id == COMPANY
                )
            )
            assert installation is not None
            installation.template_version = "2"
            if used:
                ledger = await db.get(m.Account, uuid.UUID(account["id"]))
                assert ledger is not None
                ledger.used_at = utcnow()
            await db.flush()
            await rebuild_hierarchy(db, COMPANY)
    preview = await post(
        client, "/accounting-setup/preview", {"business_accounts": False}, status=200
    )
    assert bool(preview["conflicts"]) is used
    if not used:
        assert next(c for c in preview["changes"] if c["code"] == "RESERVES")["fields"] == [
            "is_primary",
            "parent_id",
        ]
    result = await client.post(
        BASE + "/accounting-setup/install", json={"business_accounts": False}, headers=headers()
    )
    assert result.status_code == (409 if used else 200), result.text
    row = (await client.get(BASE + "/account-groups/" + reserves["id"], headers=headers())).json()
    assert row["name"] == "My reserve name"
    assert row["parent_id"] == (None if used else groups["CAPITAL"]["id"])
    installations = (await client.get(BASE + "/template-installations", headers=headers())).json()[
        "items"
    ]
    assert len(installations) == (1 if used else 2)
    if not used:
        assert result.json()["groups_updated"] == 1
        repeat = await post(
            client, "/accounting-setup/install", {"business_accounts": False}, status=200
        )
        assert repeat["groups_created"] == repeat["groups_updated"] == 0

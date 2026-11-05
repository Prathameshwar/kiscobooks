"""Verify a real 0037 database upgrade in a disposable local Accounting schema."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine, tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import MetaData, select
from sqlalchemy.engine import make_url

from accounting.config import Settings
from accounting.domain.rules import GroupNode, hierarchy
from accounting.main import create_app
from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from accounting.schemas import masters as s
from accounting.seeds.master_metadata import backfill_company
from accounting.seeds.templates import CORE, GROUPS
from tests.conftest import ENCRYPTION, SECRET, TENANT, USER, headers
from tools.verify_mysql import ROOT, schema


async def seed_0037(url: str) -> list[dict[str, Any]]:
    engine = create_engine(url)
    companies: list[dict[str, Any]] = []
    try:
        async with engine.begin() as connection:
            metadata = MetaData()
            await connection.run_sync(lambda sync: metadata.reflect(bind=sync))
            for used in (False, True):
                company = uuid7()

                async def insert(
                    table: str, values: dict[str, Any], *, company_id: uuid.UUID = company
                ) -> uuid.UUID:
                    identifier = uuid7()
                    native = metadata.tables[table]
                    record = {
                        "id": identifier,
                        "tenant_id": TENANT,
                        "company_id": company_id,
                        "created_at": dt.datetime.now(dt.UTC).replace(tzinfo=None),
                        "updated_at": dt.datetime.now(dt.UTC).replace(tzinfo=None),
                        "created_by": USER,
                        "updated_by": USER,
                        "row_version": 1,
                    } | values
                    await connection.execute(
                        native.insert().values(
                            **{
                                key: value.bytes if isinstance(value, uuid.UUID) else value
                                for key, value in record.items()
                                if key in native.c
                            }
                        )
                    )
                    return identifier

                await insert(
                    "accounting_setup",
                    {
                        "base_currency": "INR",
                        "generation": 1,
                        "template_version": "2" if used else "1",
                    },
                )
                heads = {}
                for nature in ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"):
                    heads[nature] = await insert(
                        "account_head", {"code": nature, "name": nature, "nature": nature}
                    )
                groups: dict[str, uuid.UUID] = {}
                nodes: list[GroupNode] = []
                for code, name, nature, parent in GROUPS:
                    if code in {"BRANCH_DIVISIONS", "SUSPENSE", "MISC_EXPENSES"}:
                        continue
                    parent_id = groups[parent] if parent and code != "RESERVES" else None
                    group = await insert(
                        "account_group",
                        {
                            "code": code,
                            "name": "My retained reserve" if code == "RESERVES" else name,
                            "head_id": heads[nature],
                            "parent_id": parent_id,
                            "system_key": "group." + code,
                            "status": "ACTIVE",
                        },
                    )
                    groups[code] = group
                    nodes.append(GroupNode(group, parent_id, heads[nature]))
                custom = await insert(
                    "account_group",
                    {
                        "code": "CUSTOM",
                        "name": "Custom expenses",
                        "head_id": heads["EXPENSE"],
                        "parent_id": groups["INDIRECT_EXPENSES"],
                        "system_key": None,
                        "status": "ACTIVE",
                    },
                )
                nodes.append(GroupNode(custom, groups["INDIRECT_EXPENSES"], heads["EXPENSE"]))
                for ancestor, descendant, depth in hierarchy(nodes):
                    await insert(
                        "account_group_closure",
                        {"ancestor_id": ancestor, "descendant_id": descendant, "depth": depth},
                    )
                installation = await insert(
                    "account_template_installation",
                    {
                        "template_key": "core",
                        "template_version": "2" if used else "1",
                        "content_hash": "0" * 64,
                    },
                )
                for code, group in groups.items():
                    await insert(
                        "account_template_binding",
                        {
                            "installation_id": installation,
                            "object_type": "GROUP",
                            "object_id": group,
                            "system_key": "group." + code,
                        },
                    )
                for code, name, group_code, kind in CORE:
                    account = await insert(
                        "account",
                        s.AccountCreate.model_validate(
                            {
                                "code": code,
                                "name": name,
                                "group_id": groups[group_code],
                                "kind": kind,
                            }
                        ).model_dump()
                        | {
                            "system_key": "account." + code,
                            "status": "ACTIVE",
                            "used_at": dt.datetime(2026, 1, 1)
                            if used and group_code == "RESERVES"
                            else None,
                        },
                    )
                    await insert(
                        "account_template_binding",
                        {
                            "installation_id": installation,
                            "object_type": "ACCOUNT",
                            "object_id": account,
                            "system_key": "account." + code,
                        },
                    )
                party = await insert(
                    "party",
                    s.PartyCreate.model_validate(
                        {
                            "code": "LEGACY",
                            "name": "Legacy party",
                            "legal_name": "Legacy company",
                            "country_code": "IN",
                        }
                    ).model_dump()
                    | {"status": "ACTIVE"},
                )
                await insert(
                    "party_role", {"party_id": party, "role": "CUSTOMER", "status": "ACTIVE"}
                )
                await insert(
                    "party_credit_policy",
                    s.PartyCreditPolicyCreate.model_validate(
                        {
                            "party_id": party,
                            "currency": "INR",
                            "limit_amount": "100.0000",
                            "valid_from": "2020-01-01",
                        }
                    ).model_dump(),
                )
                history = await insert(
                    "accounting_master_revision",
                    {
                        "entity_type": "party",
                        "object_id": party,
                        "action": "create",
                        "object_version": 1,
                        "changed_fields": ["name"],
                    },
                )
                companies.append(
                    {
                        "id": company,
                        "used": used,
                        "groups": groups,
                        "custom": custom,
                        "history": history,
                        "installation": installation,
                    }
                )
        return companies
    finally:
        await engine.dispose()


async def verify_upgrade(url: str, companies: list[dict[str, Any]]) -> None:
    app = create_app(
        Settings(
            database_url=url,
            actor_signing_secret=SecretStr(SECRET),
            encryption_key=SecretStr(ENCRYPTION),
        )
    )
    factory = app.state.session_factory
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://accounting.test"
        ) as client:
            assert (await client.get("/health/ready")).status_code == 503
            for data in companies:
                company = data["id"]
                base = f"/v1/companies/{company}"
                assert (
                    await client.get(base + "/account-groups", headers=headers(company=company))
                ).status_code == 409
                # Fail halfway through preparation: no marker or revision may commit.
                with tenant_scope(TENANT):
                    async with factory() as db, db.begin():
                        custom = await db.get(m.AccountGroup, data["custom"])
                        assert custom is not None
                        custom.parent_id = custom.id
                try:
                    await backfill_company(
                        factory, tenant_id=TENANT, company_id=company, actor_id=USER
                    )
                except ConflictError:
                    pass
                else:
                    raise AssertionError("cyclic legacy hierarchy was accepted")
                with tenant_scope(TENANT):
                    async with factory() as db, db.begin():
                        setup = await db.scalar(
                            select(m.AccountingSetup).where(m.AccountingSetup.company_id == company)
                        )
                        assert setup is not None and setup.metadata_version == 0
                        revisions = list(
                            await db.scalars(
                                select(MasterRevision).where(MasterRevision.company_id == company)
                            )
                        )
                        assert [row.id for row in revisions] == [data["history"]]
                        custom = await db.get(m.AccountGroup, data["custom"])
                        assert custom is not None
                        custom.parent_id = data["groups"]["INDIRECT_EXPENSES"]
                assert (
                    await backfill_company(
                        factory, tenant_id=TENANT, company_id=company, actor_id=USER
                    )
                    > 0
                )
                assert (
                    await backfill_company(
                        factory, tenant_id=TENANT, company_id=company, actor_id=USER
                    )
                    == 0
                )
                preview = await client.post(
                    base + "/accounting-setup/preview",
                    json={"business_accounts": False},
                    headers=headers(company=company),
                )
                assert preview.status_code == 200, preview.text
                assert bool(preview.json()["conflicts"]) is data["used"]
                request_headers = headers(company=company)
                result = await client.post(
                    base + "/accounting-setup/install",
                    json={"business_accounts": False},
                    headers=request_headers,
                )
                assert result.status_code == (409 if data["used"] else 200), result.text
                if not data["used"]:
                    assert (
                        result.json()["groups_created"] == 3
                        and result.json()["groups_updated"] == 1
                    )
                    replay = await client.post(
                        base + "/accounting-setup/install",
                        json={"business_accounts": False},
                        headers=request_headers,
                    )
                    assert (
                        replay.json() == result.json()
                        and replay.headers["Idempotency-Replayed"] == "true"
                    )
                saved = await client.get(base + "/account-groups", headers=headers(company=company))
                assert saved.status_code == 200, saved.text
                rows = {row["id"]: row for row in saved.json()["items"]}
                assert len(rows) == (26 if data["used"] else 29)
                assert {str(value) for value in data["groups"].values()} <= set(rows)
                reserve = rows[str(data["groups"]["RESERVES"])]
                assert reserve["name"] == "My retained reserve"
                assert reserve["parent_id"] == (
                    None if data["used"] else str(data["groups"]["CAPITAL"])
                )
                with tenant_scope(TENANT):
                    async with factory() as db:
                        assert await db.get(MasterRevision, data["history"]) is not None
                        assert (
                            await db.get(m.AccountTemplateInstallation, data["installation"])
                            is not None
                        )
            assert (await client.get("/health/ready")).status_code == 200
        print(
            "0037 upgrade: backfill rollback/retry, scoped readiness, v1/v2 history, "
            "renamed/custom groups, safe install/replay and used-account atomic conflict passed"
        )
    finally:
        await app.state.engine.dispose()


def main() -> None:
    server = os.environ.get(
        "ACCOUNTING_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396"
    )
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("select a loopback development server without a database")
    name = "accounting_test_" + uuid.uuid4().hex
    url = parsed.set(database=name).render_as_string(hide_password=False)
    config = Config(str(ROOT / "dbs/accounting/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "dbs/accounting"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    asyncio.run(schema(server, name, True))
    previous = os.environ.get("ACCOUNTING_DATABASE_URL")
    os.environ["ACCOUNTING_DATABASE_URL"] = url
    try:
        command.upgrade(config, "0037")
        companies = asyncio.run(seed_0037(url))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        asyncio.run(verify_upgrade(url, companies))
    finally:
        try:
            asyncio.run(schema(server, name, False))
        finally:
            if previous is None:
                os.environ.pop("ACCOUNTING_DATABASE_URL", None)
            else:
                os.environ["ACCOUNTING_DATABASE_URL"] = previous


if __name__ == "__main__":
    main()

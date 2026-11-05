"""Verify a fresh random Accounting schema on an explicitly selected loopback server."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from accounting.config import Settings
from accounting.main import create_app
from accounting.metadata import service_metadata
from tests.conftest import COMPANY, ENCRYPTION, SECRET, TENANT, headers
from tests.test_integrity_regressions import address_and_registration, day

ROOT = Path(__file__).resolve().parents[3]


async def schema(server: str, name: str, create: bool) -> None:
    if re.fullmatch(r"accounting_test_[0-9a-f]{32}", name) is None:
        raise ValueError("invalid isolated schema")
    engine = create_async_engine(server, poolclass=NullPool)
    try:
        async with engine.connect() as db:
            await db.execute(
                text(
                    f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    if create
                    else f"DROP DATABASE `{name}`"
                )
            )
    finally:
        await engine.dispose()


async def verify(url: str) -> None:
    app = create_app(
        Settings(
            database_url=url,
            actor_signing_secret=SecretStr(SECRET),
            encryption_key=SecretStr(ENCRYPTION),
        )
    )
    try:
        async with app.state.engine.connect() as connection:
            if await connection.scalar(text("SELECT DATABASE()")) != make_url(url).database:
                raise AssertionError("verification connected to a different database")
            differences = await connection.run_sync(
                lambda db: compare_metadata(MigrationContext.configure(db), service_metadata())
            )
            if differences:
                raise AssertionError(f"Migration/model drift: {differences}")
            print("MySQL version:", await connection.scalar(text("SELECT VERSION()")))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://accounting.test"
        ) as client:
            base = f"/v1/companies/{COMPANY}"
            assert (await client.get("/health/ready")).status_code == 200
            result = await client.post(
                base + "/accounting-setup/initialize", json={}, headers=headers()
            )
            assert result.status_code == 200, result.text
            result = await client.post(
                base + "/accounting-setup/install",
                json={"business_accounts": True},
                headers=headers(),
            )
            assert result.status_code == 200, result.text
            # Initialization creates the default chart; explicit installation is a no-op.
            assert result.json()["groups_created"] == 0 and result.json()["accounts_created"] == 0
            result = await client.get(base + "/accounts", headers=headers())
            assert result.status_code == 200 and len(result.json()["items"]) == 12, result.text
            h = headers()
            body = {
                "code": "CONCURRENT",
                "name": "Concurrent party",
                "legal_name": "Concurrent party",
                "country_code": "IN",
            }
            results = await asyncio.gather(
                *(client.post(base + "/parties", json=body, headers=h) for _ in range(2))
            )
            assert all(r.status_code == 201 for r in results), [r.text for r in results]
            assert results[0].json()["id"] == results[1].json()["id"]
            group = (await client.get(base + "/account-groups", headers=headers())).json()["items"][
                0
            ]
            alias = await client.post(
                base + "/account-group-aliases",
                headers=headers(),
                json={"group_id": group["id"], "alias": "Query plan alias"},
            )
            assert alias.status_code == 201, alias.text
            party, address, registration = await address_and_registration(client, day(-1), None)
            link = await client.post(
                base + "/party-registration-addresses",
                headers=headers(),
                json={
                    "party_id": party["id"],
                    "address_id": address["id"],
                    "registration_id": registration["id"],
                    "valid_from": day(-1),
                },
            )
            assert link.status_code == 201, link.text
            parameters = {
                "tenant": TENANT.bytes,
                "company": COMPANY.bytes,
                "as_of": dt.date.today(),
                "alias": "Query plan alias",
                "registration": uuid.UUID(registration["id"]).bytes,
                "address": uuid.UUID(address["id"]).bytes,
            }
            plans = [
                (
                    "groups.sort",
                    "SELECT id FROM account_group WHERE tenant_id=:tenant AND company_id=:company "
                    "ORDER BY sort_order,id LIMIT 51",
                    "ix_account_group_sort",
                ),
                (
                    "accounts.sort",
                    "SELECT id FROM account WHERE tenant_id=:tenant AND company_id=:company "
                    "ORDER BY sort_order,id LIMIT 51",
                    "ix_account_sort",
                ),
                (
                    "groups.alias",
                    "SELECT id FROM account_group_alias WHERE tenant_id=:tenant "
                    "AND company_id=:company AND alias=:alias LIMIT 51",
                    "uq_account_group_alias_0",
                ),
                (
                    "registration.address",
                    "SELECT id FROM party_registration_address WHERE tenant_id=:tenant "
                    "AND company_id=:company AND registration_id=:registration "
                    "AND address_id=:address AND valid_from<=:as_of "
                    "AND (valid_to IS NULL OR valid_to>=:as_of) ORDER BY id LIMIT 51",
                    "uq_party_registration_address_0",
                ),
                (
                    "registration.as_of",
                    "SELECT id FROM party_registration_address WHERE tenant_id=:tenant "
                    "AND company_id=:company AND valid_from<=:as_of "
                    "AND (valid_to IS NULL OR valid_to>=:as_of) ORDER BY id LIMIT 51",
                    "ix_party_registration_address_asof",
                ),
            ]
            async with app.state.engine.connect() as connection:
                for label, sql, expected_index in plans:
                    rows = (
                        (
                            await connection.execute(
                                text("EXPLAIN FORMAT=TRADITIONAL " + sql), parameters
                            )
                        )
                        .mappings()
                        .all()
                    )
                    assert any(
                        expected_index in str(row.get("possible_keys")) + str(row.get("key"))
                        for row in rows
                    ), (label, rows)
                    print(
                        "Query plan:",
                        label,
                        [{key: row.get(key) for key in ("key", "rows", "Extra")} for row in rows],
                    )
            print("Native setup, templates, list, and concurrent idempotency passed")
    finally:
        await app.state.engine.dispose()


def main(
    *, regressions: bool = False, full_suite: bool = False, selected_tests: list[str] | None = None
) -> None:
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
        command.upgrade(config, "head")
        asyncio.run(verify(url))
        if regressions or full_suite or selected_tests:
            environment = dict(os.environ, ACCOUNTING_TEST_DATABASE_URL=url)
            tests = (
                ["tests"]
                if full_suite
                else [
                    "tests/test_authorization_regressions.py",
                    "tests/test_integrity_regressions.py",
                    "tests/test_workflow_regressions.py",
                ]
            )
            if selected_tests:
                test_root = (Path(__file__).resolve().parents[1] / "tests").resolve()
                for selected in selected_tests:
                    candidate = (test_root.parent / selected).resolve()
                    if (
                        not candidate.is_relative_to(test_root)
                        or candidate.suffix != ".py"
                        or not candidate.is_file()
                    ):
                        raise ValueError("select existing Accounting test modules")
                tests = selected_tests
            coverage = ["--cov=accounting", "--cov-report=term-missing"] if full_suite else []
            subprocess.run(  # noqa: S603 -- fixed test argv, validated disposable database.
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *tests,
                    *coverage,
                    "-p",
                    "no:cacheprovider",
                    "-q",
                    "--tb=short",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                check=True,
            )
        # Historical narrowing migrations deliberately refuse newer financial facts.
        # Verify structural reversibility separately from the regression fixtures;
        # never weaken those production data guards just to make a test round trip.
        # schema() restricts this to our validated random, loopback-only database.
        asyncio.run(schema(server, name, False))
        asyncio.run(schema(server, name, True))
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        print("Native migration downgrade/upgrade round trip passed")
    finally:
        try:
            asyncio.run(schema(server, name, False))
        finally:
            if previous is None:
                os.environ.pop("ACCOUNTING_DATABASE_URL", None)
            else:
                os.environ["ACCOUNTING_DATABASE_URL"] = previous


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regressions", action="store_true")
    parser.add_argument("--full-suite", action="store_true")
    parser.add_argument("--tests", nargs="+")
    arguments = parser.parse_args()
    main(
        regressions=arguments.regressions,
        full_suite=arguments.full_suite,
        selected_tests=arguments.tests,
    )

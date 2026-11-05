"""Run migrations and report regressions only in a newly created disposable loopback schema."""

import argparse
import asyncio
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, inspect, text
from sqlalchemy.engine import make_url

from reports.metadata import service_metadata

ROOT = Path(__file__).resolve().parents[3]


async def database(server: str, name: str, *, create: bool) -> None:
    if not re.fullmatch(r"reports_test_[0-9a-f]{32}", name):
        raise ValueError("invalid disposable schema")
    engine = create_engine(server)
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
    engine = create_engine(url)
    try:
        async with engine.connect() as db:

            def check(connection):
                inspector = inspect(connection)
                assert set(inspector.get_table_names()) == set(service_metadata().tables) | {
                    "alembic_version"
                }
                for name, table in service_metadata().tables.items():
                    columns = {column["name"]: column for column in inspector.get_columns(name)}
                    assert set(columns) == set(table.columns.keys()), name
                    for column in table.columns:
                        assert columns[column.name]["nullable"] == column.nullable, (
                            name,
                            column.name,
                        )
                        if column.name in {"amount", "base_amount", "debit", "credit"}:
                            assert columns[column.name]["type"].scale == 4, (name, column.name)
                    expected = {tuple(index.columns.keys()) for index in table.indexes}
                    actual = {tuple(index["column_names"]) for index in inspector.get_indexes(name)}
                    assert expected <= actual, (name, expected - actual)
                    unique_expected = {
                        tuple(c.columns.keys())
                        for c in table.constraints
                        if isinstance(c, UniqueConstraint)
                    }
                    unique_actual = {
                        tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)
                    }
                    assert unique_expected <= unique_actual, (name, "unique constraints")
                    foreign_expected = {
                        (tuple(c.column_keys), tuple(e.target_fullname for e in c.elements))
                        for c in table.constraints
                        if isinstance(c, ForeignKeyConstraint)
                    }
                    foreign_actual = {
                        (
                            tuple(c["constrained_columns"]),
                            tuple(c["referred_table"] + "." + key for key in c["referred_columns"]),
                        )
                        for c in inspector.get_foreign_keys(name)
                    }
                    assert foreign_expected == foreign_actual, (name, "foreign keys")

            await db.run_sync(check)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", nargs="+", default=["tests"])
    arguments = parser.parse_args()
    for target in arguments.tests:
        if target != "tests" and not re.fullmatch(r"tests/test_[a-z0-9_]+\.py", target):
            parser.error("test targets must be test files under tests/")
    server = os.environ.get("REPORTS_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("loopback server without schema required")
    name = "reports_test_" + uuid.uuid4().hex
    url = parsed.set(database=name).render_as_string(hide_password=False)
    config = Config(str(ROOT / "dbs/reports/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "dbs/reports"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    asyncio.run(database(server, name, create=True))
    previous = os.environ.get("REPORTS_DATABASE_URL")
    os.environ["REPORTS_DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
        asyncio.run(verify(url))
        subprocess.run(  # noqa: S603 -- fixed test command, validated disposable schema.
            [
                sys.executable,
                "-m",
                "pytest",
                *arguments.tests,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            cwd=ROOT / "apis/reports",
            env=dict(os.environ, REPORTS_TEST_DATABASE_URL=url),
            check=True,
        )
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        asyncio.run(verify(url))
        print("PASS: native migrations, model/index parity, regression suite, downgrade/upgrade")
    finally:
        if previous is None:
            os.environ.pop("REPORTS_DATABASE_URL", None)
        else:
            os.environ["REPORTS_DATABASE_URL"] = previous
        asyncio.run(database(server, name, create=False))


if __name__ == "__main__":
    main()

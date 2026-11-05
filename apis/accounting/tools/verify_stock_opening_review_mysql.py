"""Verify opening corrections in a migrated random schema on a loopback MySQL server."""

import asyncio
import os
import subprocess
import sys
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from tools.verify_mysql import ROOT, schema


def main() -> None:
    server = os.environ["ACCOUNTING_TEST_MYSQL_SERVER_URL"]
    parsed = make_url(server)
    if (
        parsed.drivername != "mysql+asyncmy"
        or parsed.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed.database
    ):
        raise ValueError("select a loopback MySQL server without an existing database")
    name = "accounting_test_" + uuid.uuid4().hex
    url = parsed.set(database=name).render_as_string(hide_password=False)
    config = Config(str(ROOT / "dbs/accounting/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "dbs/accounting"))
    previous = os.environ.get("ACCOUNTING_DATABASE_URL")
    asyncio.run(schema(server, name, True))
    try:
        os.environ["ACCOUNTING_DATABASE_URL"] = url
        command.upgrade(config, "head")
        environment = dict(os.environ, ACCOUNTING_TEST_DATABASE_URL=url)
        subprocess.run(  # noqa: S603 -- fixed test arguments and validated disposable schema.
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_stock_opening_review_fixes.py",
                "tests/test_stock_opening_legacy.py",
                "tests/test_stock_opening_cohorts.py",
                "tests/test_stock_opening_races.py",
                "-q",
                "--tb=short",
                "--junitxml=.test-results-opening-review-fixes-mysql.xml",
            ],
            cwd=ROOT / "apis/accounting",
            env=environment,
            check=True,
        )
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

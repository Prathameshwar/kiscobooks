"""Run existing opening races on a disposable native schema, never an app schema.

Uses Accounting's virtualenv and the dedicated loopback MySQL server on 13396.
Model-created tables verify native locking; this is not migration acceptance.
"""

from __future__ import annotations

import asyncio
import argparse
import importlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[3]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("opening", "reporting", "opening-authority", "overview", "invoice-owner", "money-owner", "stock-owner"), default="opening")
    suite = parser.parse_args().suite
    url = make_url(os.environ["QA_MYSQL_SERVER_URL"])
    if (url.drivername != "mysql+asyncmy" or url.database or url.query
            or url.host not in {"localhost", "127.0.0.1"} or url.port != 13396):
        raise ValueError("Use the dedicated loopback test server on 13396, without a database")
    service = "reports" if suite == "overview" else "accounting"
    service_metadata = importlib.import_module(service + ".metadata").service_metadata
    schema = service + "_test_" + uuid.uuid4().hex
    pattern = service + r"_test_[0-9a-f]{32}"
    if not re.fullmatch(pattern, schema):
        raise ValueError("Invalid disposable schema")
    name = {"opening": "pending-8-native", "reporting": "pending-9-native", "opening-authority": "permanent-opening-native", "overview": "pending-14-native", "invoice-owner": "pending-13-native", "money-owner": "pending-12-native", "stock-owner": "pending-15-native"}[suite]
    output = ROOT / ".test_artifacts/tenant-admin-20261029/live" / name
    output.mkdir(parents=True, exist_ok=True)
    server = create_async_engine(url)
    database = create_async_engine(url.set(database=schema))
    created = False
    try:
        async with server.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{schema}`"))
            created = True
        async with database.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        await database.dispose()
        environment = {
            **os.environ,
            service.upper() + "_TEST_DATABASE_URL": url.set(database=schema).render_as_string(hide_password=False),
        }
        selectors = [
            "tests/test_financial_opening_api.py::test_concurrent_company_openings_have_one_owner",
            "tests/test_stock_opening_races.py"] if suite == "opening" else [
                "tests/test_reporting_feed.py", "tests/test_reporting_snapshot.py"]
        if suite == "opening-authority":
            selectors = ["tests/test_financial_opening_api.py", "tests/test_zero_opening.py"]
        if suite == "overview":
            selectors = ["tests/test_company_overview.py"]
        if suite == "invoice-owner":
            selectors = ["tests/test_invoice_preview.py", "tests/test_invoice_execution.py", "tests/test_invoice_discounts.py", "tests/test_invoice_credit_api.py"]
        if suite == "money-owner":
            selectors = ["tests/test_voucher_money.py", "tests/test_allocations.py", "tests/test_voucher_execution.py"]
        if suite == "stock-owner":
            selectors = ["tests/test_stock_effects.py", "tests/test_stock_concurrency.py", "tests/test_stock_costing.py", "tests/test_stock_gl.py", "tests/test_stock_reconciliation.py", "tests/test_stock_reporting.py"]
        command = [sys.executable, "-m", "pytest", "-q", "--tb=short",
            *selectors, f"--junitxml={output / 'results.xml'}"]
        with (output / "results.log").open("w", encoding="utf-8") as log:
            result = await asyncio.to_thread(subprocess.run, command,
                cwd=ROOT / "apis" / service, env=environment, stdout=log,
                stderr=subprocess.STDOUT, check=False)
        print(f"Native {suite} checks: exit {result.returncode}; evidence {output}", flush=True)
        return result.returncode
    finally:
        await database.dispose()
        if created:
            async with server.begin() as connection:
                if not re.fullmatch(pattern, schema):
                    raise ValueError("Refusing to drop an unvalidated schema")
                await connection.execute(text(f"DROP DATABASE `{schema}`"))
        await server.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

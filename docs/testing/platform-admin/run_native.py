"""Run native checks in fresh MySQL schemas, including both shared-module orders.

Use the Identity virtualenv. QA_MYSQL_SERVER_URL must point at the disposable
MySQL 9.6 test server, without a database name. Never use the application DB URL.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[3]


async def main():
    from billing_platform.db import Base
    from identity import models  # noqa: F401

    url = make_url(os.environ["QA_MYSQL_SERVER_URL"])
    if url.database or url.host not in {"localhost", "127.0.0.1"} or url.port != 13396:
        raise ValueError(
            "Use the dedicated loopback test server on 13396 with no database name"
        )
    output = Path(
        os.environ.get(
            "QA_NATIVE_OUTPUT", str(ROOT / ".test_artifacts/platform-admin-native")
        )
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    server = create_async_engine(url)
    failed = False
    scenarios = {
        "test_platform_setup_mysql": ["test_platform_setup_mysql"],
        "test_account_review_mysql": ["test_account_review_mysql"],
        "shared_setup_then_review": ["test_platform_setup_mysql", "test_account_review_mysql"],
        "shared_review_then_setup": ["test_account_review_mysql", "test_platform_setup_mysql"],
    }
    for scenario, modules in scenarios.items():
        database = "qa_platform_" + uuid.uuid4().hex
        # Name generated here, containing only the fixed prefix and UUID hex.
        async with server.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{database}`"))
        test_url = url.set(database=database)
        engine = create_async_engine(test_url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await engine.dispose()
            environment = {
                **os.environ,
                "IDENTITY_TEST_MYSQL_URL": test_url.render_as_string(
                    hide_password=False
                ),
            }
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *[f"tests/{module}.py" for module in modules],
                f"--junitxml={output / (scenario + '.xml')}",
            ]
            with (output / f"{scenario}.log").open("w", encoding="utf-8") as log:
                result = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    cwd=ROOT / "apis/identity",
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            failed |= result.returncode != 0
            print(f"{scenario}: exit {result.returncode}", flush=True)
        finally:
            await engine.dispose()
            async with server.begin() as connection:
                await connection.execute(text(f"DROP DATABASE `{database}`"))
    await server.dispose()
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

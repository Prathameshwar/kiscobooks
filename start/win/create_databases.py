"""Create the configured local service databases using provisioning credentials."""

from __future__ import annotations

import asyncio
import json
import os
import re

_DATABASE_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required provisioning environment variable {name} is missing.")
    return value


def _database_names() -> list[str]:
    try:
        names = json.loads(_required_environment("BILL_PROVISION_DATABASE_NAMES"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Configured database names are not valid JSON.") from exc
    if not isinstance(names, list) or not names or any(
        not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name) for name in names
    ):
        raise RuntimeError("Configured service database names are invalid.")
    return names


async def _create_databases() -> None:
    try:
        names = _database_names()
        username = _required_environment("BILL_PROVISION_MYSQL_USER")
        password = _required_environment("BILL_PROVISION_MYSQL_PASSWORD")
        host = _required_environment("BILL_PROVISION_MYSQL_HOST")
        port = int(_required_environment("BILL_PROVISION_MYSQL_PORT"))
        if not 1 <= port <= 65535:
            raise RuntimeError("MySQL provisioning port must be between 1 and 65535.")
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import create_async_engine

    url = URL.create(
        "mysql+asyncmy",
        username=username,
        password=password,
        host=host,
        port=port,
    )
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for name in names:
                await connection.exec_driver_sql(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4"
                )
                print(f"Database ready: {name}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_create_databases())

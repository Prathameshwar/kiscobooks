"""A reachable database cannot make undeployed local sign-in appear ready."""

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_readiness_rejects_missing_migration_table(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert "alembic" not in response.text
    assert (await client.get("/health/live")).status_code == 200


async def test_readiness_rejects_old_head_and_missing_local_auth_table(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        await connection.execute(text("INSERT INTO alembic_version VALUES ('0089')"))
    assert (await client.get("/health/ready")).status_code == 503
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE alembic_version SET version_num = '0095'"))
    assert (await client.get("/health/ready")).status_code == 200
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE local_authorization"))
    assert (await client.get("/health/ready")).status_code == 503

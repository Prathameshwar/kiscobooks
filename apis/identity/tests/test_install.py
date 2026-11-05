"""Installation loads defaults atomically and safely on fresh and existing databases."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic import command
from alembic.config import Config
from billing_platform.db import Base, create_session_factory
from billing_platform.db.tenant_context import unfiltered
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from identity import install
from identity.models import (
    BusinessCategory,
    BusinessRole,
    Country,
    PlatformPrice,
    Role,
    StoreFormat,
)
from identity.seeds.business_classifications import seed_business_classifications
from tests.alembic_support import alembic_config


def test_missing_installation_url_fails_before_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDENTITY_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        install.main([])
    assert exc.value.code == 2


def test_migration_failure_never_runs_seeds(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = AsyncMock()
    monkeypatch.setattr(install, "seed_installation_defaults", seed)

    def fail(config: Config, target: str) -> None:
        assert config.get_main_option("sqlalchemy.url") == "mysql+asyncmy://localhost/test_db"
        assert target == "head"
        raise RuntimeError("migration failed")

    monkeypatch.setattr(command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="migration failed"):
        install.install_identity("mysql+asyncmy://localhost/test_db")
    seed.assert_not_called()


async def test_failed_default_seed_rolls_back_all_default_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "sqlite+aiosqlite:///" + str(tmp_path / "install.sqlite")
    engine = create_async_engine(url)
    original = seed_business_classifications

    async def fail(session: AsyncSession) -> None:
        await original(session)
        raise RuntimeError("seed failed")

    monkeypatch.setattr(install, "seed_business_classifications", fail)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        with pytest.raises(RuntimeError, match="seed failed"):
            await install.seed_installation_defaults(url)
        async with create_session_factory(engine)() as session:
            with unfiltered():
                for model in (Country, Role, BusinessCategory, BusinessRole, StoreFormat):
                    assert await session.scalar(select(func.count()).select_from(model)) == 0
        monkeypatch.setattr(install, "seed_business_classifications", original)
        await install.seed_installation_defaults(url)
        async with create_session_factory(engine)() as session:
            assert await session.get(BusinessRole, "online") is not None
            assert await session.get(BusinessRole, "store") is not None
            assert await session.get(StoreFormat, "online") is not None
            assert await session.scalar(select(func.count()).select_from(PlatformPrice)) == 9
    finally:
        await engine.dispose()


@pytest.mark.mysql
def test_installation_loads_defaults_and_can_be_rerun(mysql_url: str) -> None:
    command.downgrade(alembic_config(mysql_url), "base")
    install.install_identity(mysql_url)

    async def snapshot() -> dict[str, object]:
        engine = create_async_engine(mysql_url)
        try:
            async with create_session_factory(engine)() as session:
                with unfiltered():
                    return {
                        "categories": list(
                            await session.scalars(
                                select(BusinessCategory.code).order_by(BusinessCategory.code)
                            )
                        ),
                        "roles": list(
                            await session.scalars(
                                select(BusinessRole.code).order_by(BusinessRole.code)
                            )
                        ),
                        "formats": list(
                            await session.scalars(
                                select(StoreFormat.code).order_by(StoreFormat.code)
                            )
                        ),
                        "system_role_keys": list(
                            await session.scalars(select(Role.key).order_by(Role.key))
                        ),
                        "system_role_ids": list(
                            await session.scalars(select(Role.id).order_by(Role.id))
                        ),
                        "countries": await session.scalar(
                            select(func.count()).select_from(Country)
                        ),
                    }
        finally:
            await engine.dispose()

    first = asyncio.run(snapshot())
    assert first["categories"] == [
        "apparel",
        "fmcg",
        "general",
        "mobile_electronics",
        "other",
        "pharmaceutical",
    ]
    assert first["roles"] == [
        "distributor",
        "manufacturer",
        "online",
        "retailer",
        "stockist",
        "store",
        "wholesaler",
    ]
    assert first["formats"] == ["mart", "online", "other", "shop", "supermarket"]
    assert first["system_role_ids"]
    role_keys = first["system_role_keys"]
    assert isinstance(role_keys, list)
    assert "salesperson" in role_keys
    assert first["countries"]
    install.install_identity(mysql_url)
    assert asyncio.run(snapshot()) == first

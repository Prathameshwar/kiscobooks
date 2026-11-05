"""Deployment seed dry runs and updates exercise real transactions."""

from __future__ import annotations

import json
from pathlib import Path

from billing_platform.db import Base, create_session_factory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from identity.models import BusinessCategory
from identity.seeds.business_classifications import (
    SEED_PATH,
    apply_seed,
    seed_business_classifications,
)


async def test_seed_dry_run_then_commit_and_label_update(tmp_path: Path) -> None:
    url = "sqlite+aiosqlite:///" + str(tmp_path / "classifications.sqlite")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await apply_seed(url, dry_run=True)
        async with create_session_factory(engine)() as session:
            assert list(await session.scalars(select(BusinessCategory))) == []
        await apply_seed(url, dry_run=False)
        async with create_session_factory(engine)() as session:
            row = await session.get(BusinessCategory, "general")
            assert row is not None and row.label == "General"
            data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            data["business_categories"][0]["label"] = "General business"
            await seed_business_classifications(session, data=data)
            await session.commit()
        async with create_session_factory(engine)() as session:
            row = await session.get(BusinessCategory, "general")
            assert row is not None and row.label == "General business"
    finally:
        await engine.dispose()

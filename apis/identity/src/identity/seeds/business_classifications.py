"""Idempotent deployment seed for global business classifications; no HTTP writes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from billing_platform.db import create_engine, create_session_factory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import BusinessCategory, BusinessRole, StoreFormat

SEED_PATH = Path(__file__).resolve().parents[5] / "seeds/business_classifications/data.json"
TABLES = {
    "business_categories": BusinessCategory,
    "business_roles": BusinessRole,
    "store_formats": StoreFormat,
}


async def seed_business_classifications(
    session: AsyncSession,
    *,
    data: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Upsert shipped keys and deactivate withdrawn keys; caller owns commit/rollback."""
    if data is None:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert data is not None
    for key, model in TABLES.items():
        rows = {row.code: row for row in (await session.scalars(select(model))).all()}
        wanted = {entry["code"] for entry in data[key]}
        for entry in data[key]:
            row = rows.get(entry["code"])
            if row is None:
                session.add(model(**entry, is_active=True))
            else:
                row.label = entry["label"]
                row.sort_order = entry["sort_order"]
                row.is_active = True
        for code, row in rows.items():
            if code not in wanted:
                row.is_active = False
    await session.flush()


async def apply_seed(url: str, *, dry_run: bool) -> None:
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as session:
            await seed_business_classifications(session)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("IDENTITY_DATABASE_URL")
    if not url:
        parser.error("set IDENTITY_DATABASE_URL")
    asyncio.run(apply_seed(url, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

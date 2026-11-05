"""Insert shipped commercial defaults once. Never overwrite administrator decisions."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models.platform_price import PlatformPrice
from identity.schemas.platform_price import PlatformPriceInput
from identity.services.platform_pricing import snapshot

SEED_PATH = Path(__file__).resolve().parents[5] / "seeds/pricing/data.json"


async def seed_pricing(db: AsyncSession) -> None:
    existing = set(await db.scalars(select(PlatformPrice.code)))
    for value in json.loads(SEED_PATH.read_text(encoding="utf-8")):
        body = PlatformPriceInput.model_validate(value)
        if body.code in existing:
            continue
        row = PlatformPrice(**body.model_dump(), version=1)
        db.add(row)
        await db.flush()
        snapshot(db, row)
        existing.add(body.code)
    await db.flush()

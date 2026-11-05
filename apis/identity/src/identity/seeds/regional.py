"""Re-runnable language/IANA defaults; never run during API startup or requests."""

from importlib.resources import files
from zoneinfo import ZoneInfo

from billing_platform.reference import register_language
from billing_platform.reference.seed import seed_reference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Timezone


async def seed_regional_defaults(db: AsyncSession) -> None:
    register_language()
    await seed_reference(db, datasets=("language",), managed=True)
    # Use the committed dependency pin, independent of host OS timezone availability.
    codes = set(files("tzdata").joinpath("zones").read_text(encoding="utf-8").splitlines())
    codes.add("UTC")
    existing = {row.code: row for row in await db.scalars(select(Timezone))}
    for code in sorted(codes):
        ZoneInfo(code)
        if len(code) > 64:
            raise ValueError("IANA timezone exceeds the supported code length")
        name = code.replace("_", " ")
        row = existing.get(code)
        if row is None:
            db.add(Timezone(code=code, name=name, is_active=True))
        else:
            row.name, row.is_active = name, True
    for code, row in existing.items():
        if code not in codes:
            row.is_active = False
    await db.flush()

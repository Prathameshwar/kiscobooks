from billing_platform.reference import DATASETS, load, register_language
from billing_platform.reference.seed import seed_reference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Country, Currency, Language, State


async def test_catalog_uses_shared_reference_seed_without_duplicate_rows(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    register_language()
    async with factory.begin() as db:
        first = await seed_reference(db, datasets=(*DATASETS, "language"))
        assert len(first) == len(DATASETS) + 1
        assert all(outcome.changed for outcome in first)
    async with factory.begin() as db:
        second = await seed_reference(db, datasets=(*DATASETS, "language"))
        assert all(not outcome.changed for outcome in second)
        for model, dataset in [
            (Currency, "currency"),
            (Country, "country"),
            (State, "state"),
            (Language, "language"),
        ]:
            assert len((await db.scalars(select(model))).all()) == len(load(dataset))

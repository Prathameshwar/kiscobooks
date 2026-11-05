from billing_platform.db.language import Language
from billing_platform.reference import load, register_language
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_language_dataset_is_bounded_and_seed_preserves_history(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    from billing_platform.reference.seed import seed_reference

    register_language()
    rows = load("language")
    assert 180 <= len(rows) <= 200
    assert len({row["code"] for row in rows}) == len(rows)
    assert len({row["iso3"] for row in rows}) == len(rows)
    assert next(row for row in rows if row["code"] == "en")["name"] == "English"
    for row in rows:
        assert len(row["code"]) == 2 and len(row["iso3"]) == 3
        assert len(row["name"]) <= 128
        assert row["native_name"] is None or len(row["native_name"]) <= 128
    async with factory.begin() as db:
        await seed_reference(db, datasets=("language",))
        db.add(Language(code="zz", iso3="zzz", name="withdrawn", is_active=True))
    async with factory.begin() as db:
        outcomes = await seed_reference(db, datasets=("language",))
        assert outcomes[0].deactivated == 1
        withdrawn = await db.scalar(select(Language).where(Language.code == "zz"))
        assert withdrawn is not None and not withdrawn.is_active

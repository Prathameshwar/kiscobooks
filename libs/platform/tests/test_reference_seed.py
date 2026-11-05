"""The reference seed: idempotent, ordered, and never destructive.

The properties that matter, in order:

* **Re-runnable.** It runs on every deploy, so the second run must change nothing.
  This is the whole reason reference content is a seed and not a migration.
* **Never deletes.** A code ISO withdraws is deactivated, because posted documents
  reference it by code (invariant 12).
* **Foreign-key ordered.** `currency`, then `country`, then `state`. The SQLite
  fixture enforces foreign keys, so a wrong order fails here rather than in
  production.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.db.session import database_url
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.reference import DATASETS, countries, currencies, states
from billing_platform.reference.seed import (
    SeedOutcome,
    apply_reference_seed,
    main,
    seed_reference,
)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_a_first_seed_inserts_every_row(session: AsyncSession) -> None:
    outcomes = await seed_reference(session)

    assert [outcome.table for outcome in outcomes] == list(DATASETS)
    assert [outcome.inserted for outcome in outcomes] == [
        len(currencies()),
        len(countries()),
        len(states()),
    ]
    assert all(outcome.updated == 0 and outcome.deactivated == 0 for outcome in outcomes)
    assert await _count(session, Currency) == len(currencies())
    assert await _count(session, Country) == len(countries())
    assert await _count(session, State) == len(states())


async def test_a_second_seed_changes_nothing(session: AsyncSession) -> None:
    """Idempotence, which is what makes running this on every deploy safe."""
    await seed_reference(session)
    await session.commit()

    outcomes = await seed_reference(session)

    assert all(not outcome.changed for outcome in outcomes)
    assert [outcome.unchanged for outcome in outcomes] == [
        len(currencies()),
        len(countries()),
        len(states()),
    ]


async def test_a_changed_value_is_updated_in_place(session: AsyncSession) -> None:
    """A corrected country name reaches every environment on the next deploy — the
    thing a migration carrying content cannot do."""
    await seed_reference(session)
    await session.commit()

    india = await session.get(Country, "IN")
    assert india is not None
    india.name = "Stale Name"
    await session.commit()

    outcomes = {outcome.table: outcome for outcome in await seed_reference(session)}

    assert outcomes["country"].updated == 1
    assert outcomes["country"].inserted == 0
    refreshed = await session.get(Country, "IN")
    assert refreshed is not None
    assert refreshed.name == "India"


async def test_a_row_the_dataset_no_longer_carries_is_deactivated_not_deleted(
    session: AsyncSession,
) -> None:
    """Invariant 12. A posted invoice references a currency by code; deleting the row
    would leave the document unprintable and the audit trail unresolvable."""
    session.add(
        Currency(
            code="ZZZ",
            numeric_code="999",
            name="Withdrawn",
            symbol="Z",
            minor_unit=2,
            major_unit_name="Zeds",
            minor_unit_name=None,
            minor_unit_name_plural=None,
            is_active=True,
        )
    )
    await session.commit()

    outcomes = {outcome.table: outcome for outcome in await seed_reference(session)}
    await session.commit()

    assert outcomes["currency"].deactivated == 1
    withdrawn = await session.get(Currency, "ZZZ")
    assert withdrawn is not None, "a withdrawn code must never be deleted"
    assert withdrawn.is_active is False


async def test_deactivation_is_not_repeated_on_the_next_run(session: AsyncSession) -> None:
    """An already-deactivated row is not counted again, so a clean re-run reports
    nothing changed and a real change stays visible in the output."""
    session.add(
        Currency(
            code="ZZZ",
            numeric_code="999",
            name="Withdrawn",
            symbol="Z",
            minor_unit=2,
            major_unit_name="Zeds",
            minor_unit_name=None,
            minor_unit_name_plural=None,
            is_active=False,
        )
    )
    await session.commit()

    outcomes = {outcome.table: outcome for outcome in await seed_reference(session)}

    assert outcomes["currency"].deactivated == 0


async def test_the_seed_flushes_but_does_not_commit(session: AsyncSession) -> None:
    """The caller owns the transaction, so a seed can be one step of a larger
    provisioning transaction — and a dry run can roll the whole thing back."""
    await seed_reference(session)
    await session.rollback()

    assert await _count(session, Currency) == 0


async def test_seeding_state_alone_fails_without_its_countries(session: AsyncSession) -> None:
    """Proves the order in ``DATASETS`` is load-bearing rather than cosmetic, and
    that the fixture really does enforce foreign keys."""
    with pytest.raises(IntegrityError):
        await seed_reference(session, datasets=("state",))
    await session.rollback()


async def test_seeded_rows_are_readable_with_no_tenant_in_context(
    session: AsyncSession,
) -> None:
    """The §0.3 exemption, asserted rather than assumed: these three tables carry no
    ``TenantMixin``, so the session-level filter must not touch them. If it did, the
    seed itself could not run — it has no tenant — and every company form would need
    one to populate a country dropdown."""
    await seed_reference(session)
    await session.commit()

    assert (await session.execute(select(Country).where(Country.code == "IN"))).scalar_one()
    assert (await session.execute(select(State).where(State.code == "IN-MH"))).scalar_one()
    assert (await session.execute(select(Currency).where(Currency.code == "INR"))).scalar_one()


async def test_reference_rows_look_the_same_to_every_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The inverse of the isolation test every tenant-scoped table gets: shared data
    must be *identically* visible, not invisible. A filter accidentally applied here
    would hide every country from every user."""
    await seed_reference(session)
    await session.commit()

    with tenant_scope(tenant_a):
        first = (await session.execute(select(func.count()).select_from(Country))).scalar_one()
    with tenant_scope(tenant_b):
        second = (await session.execute(select(func.count()).select_from(Country))).scalar_one()

    assert first == second == len(countries())


def test_database_url_names_the_variable_it_wants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDENTITY_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="IDENTITY_DATABASE_URL is not set"):
        database_url("identity")


def test_database_url_never_echoes_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database URL carries a password (CLAUDE.md §5.11), so an empty-but-set
    variable must still not appear in the message."""
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "")

    with pytest.raises(SystemExit) as raised:
        database_url("identity")
    assert "://" not in str(raised.value)


def test_database_url_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    assert database_url("catalog") == "sqlite+aiosqlite:///:memory:"


def test_outcome_renders_one_line_per_table() -> None:
    rendered = str(SeedOutcome("currency", inserted=1, updated=2, unchanged=3, deactivated=4))

    assert rendered.startswith("currency")
    assert "inserted=1" in rendered
    assert "deactivated=4" in rendered


def test_outcome_reports_no_change_when_everything_matched() -> None:
    assert not SeedOutcome("currency", unchanged=168).changed
    assert SeedOutcome("currency", updated=1).changed


async def test_apply_reference_seed_commits(tmp_path: Path) -> None:
    """Against a file-backed SQLite database, because an in-memory one would not
    outlive the engine and so could not prove the commit happened."""
    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine

    path = tmp_path.joinpath("seed.db").as_posix()
    url = f"sqlite+aiosqlite:///{path}"

    engine = create_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    outcomes = await apply_reference_seed(url)
    assert sum(outcome.inserted for outcome in outcomes) > 0

    verify = create_engine(url)
    try:
        async with verify.connect() as connection:
            total = (
                await connection.execute(select(func.count()).select_from(Country.__table__))
            ).scalar_one()
    finally:
        await verify.dispose()
    assert total == len(countries())


async def test_apply_reference_seed_dry_run_rolls_back(tmp_path: Path) -> None:
    """``--dry-run`` reports what would change and leaves the database untouched,
    which is what makes it worth running before a production seed."""
    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine

    path = tmp_path.joinpath("dry.db").as_posix()
    url = f"sqlite+aiosqlite:///{path}"

    engine = create_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    outcomes = await apply_reference_seed(url, dry_run=True)
    assert sum(outcome.inserted for outcome in outcomes) > 0

    verify = create_engine(url)
    try:
        async with verify.connect() as connection:
            total = (
                await connection.execute(select(func.count()).select_from(Country.__table__))
            ).scalar_one()
    finally:
        await verify.dispose()
    assert total == 0


def test_the_cli_seeds_the_database_named_by_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through ``main``, the entry point ``seeds/reference/__main__.py``
    calls. Run synchronously because ``main`` owns its own event loop."""
    import asyncio

    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine

    path = tmp_path.joinpath("cli.db").as_posix()
    url = f"sqlite+aiosqlite:///{path}"

    async def create() -> None:
        engine = create_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)

    assert main(["identity"]) == 0

    output = capsys.readouterr().out
    for name in DATASETS:
        assert name in output
    assert "dry run" not in output


def test_the_cli_says_when_it_rolled_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import asyncio

    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine

    path = tmp_path.joinpath("clidry.db").as_posix()
    url = f"sqlite+aiosqlite:///{path}"

    async def create() -> None:
        engine = create_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)

    assert main(["identity", "--dry-run"]) == 0
    assert "dry run: rolled back" in capsys.readouterr().out

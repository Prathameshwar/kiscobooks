"""Materialize the committed ISO datasets into a service database.

Idempotent and re-runnable, which is the whole reason reference content is a seed
and not a migration (CLAUDE.md §2). Running it twice against the same database
changes nothing the second time; running it after a regeneration applies exactly
the rows that changed.

**Nothing is ever deleted.** A code withdrawn from ISO is deactivated, because
posted documents reference it by code (invariant 12). That is also why codes are
never renamed: a rename would be a delete and an insert wearing a disguise.

The upsert is a read-then-write rather than MariaDB's
``INSERT ... ON DUPLICATE KEY UPDATE``. Two reasons, in order of weight: it is the
same code path on every dialect, so it is tested here against SQLite rather than
only under Docker; and it can report what actually changed, which is what makes a
``--dry-run`` before a production seed worth running. The concurrency argument for a
native upsert does not apply — a seed is a single deploy step over at most a few
thousand rows, not a request path.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.reference_management import ReferenceRevision

# `database_url` moved to `db.session` when the roles seed needed the same helper; it
# stays importable from here, because that is where the CLI's tests reach for it.
from billing_platform.db.session import create_engine, create_session_factory, database_url
from billing_platform.reference import DATASETS, MODELS, load, primary_key_column


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """What one table's seed did. Printed by the CLI and asserted by the tests."""

    table: str
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.deactivated)

    def __str__(self) -> str:
        return (
            f"{self.table:<9} inserted={self.inserted:<5} updated={self.updated:<5} "
            f"unchanged={self.unchanged:<5} deactivated={self.deactivated}"
        )


async def _seed_table(
    session: AsyncSession, table_name: str, *, managed: bool = False
) -> SeedOutcome:
    model = MODELS[table_name]
    pk = primary_key_column(table_name)
    columns = [column.name for column in model.__table__.columns]

    # No tenant filter applies: these models carry no `TenantMixin`, so the
    # session-level filter does not touch them and this runs with no tenant in
    # context. That is asserted by the Phase 1 exit test rather than assumed.
    existing = {
        getattr(row, pk): row for row in (await session.execute(select(model))).scalars().all()
    }
    revisions = (
        {
            row.code: row
            for row in await session.scalars(
                select(ReferenceRevision).where(ReferenceRevision.kind == table_name)
            )
        }
        if managed
        else {}
    )

    inserted = updated = unchanged = 0
    for values in load(table_name):
        provenance = revisions.get(values[pk])
        if provenance is not None and provenance.source == "operator":
            unchanged += 1
            continue
        current = existing.get(values[pk])
        if current is None:
            # Keyword construction from a validated dataset, never `**request`:
            # `load()` has already checked the key set against these columns
            # (CLAUDE.md §5.6 — no mass assignment).
            session.add(model(**values))
            inserted += 1
            continue

        changes = {
            column: values[column]
            for column in columns
            if getattr(current, column) != values[column]
        }
        if not changes:
            unchanged += 1
            continue
        for column, value in changes.items():
            setattr(current, column, value)
        updated += 1

    protected = {code for code, row in revisions.items() if row.source == "operator"}
    deactivated = _deactivate_withdrawn(
        {code: row for code, row in existing.items() if code not in protected}, load(table_name), pk
    )
    await session.flush()
    if managed:
        for row in await session.scalars(select(model)):
            code = getattr(row, pk)
            provenance = revisions.get(code)
            if provenance is not None and provenance.source == "operator":
                continue
            data = {column: getattr(row, column) for column in columns}
            if provenance is None:
                provenance = ReferenceRevision(kind=table_name, code=code, source="seed", version=0)
                session.add(provenance)
            provenance.name, provenance.is_active = data["name"], data["is_active"]
            provenance.parent_code = data.get("country_code", data.get("default_currency_code"))
            provenance.payload = data
        await session.flush()
    return SeedOutcome(table_name, inserted, updated, unchanged, deactivated)


def _deactivate_withdrawn(existing: dict[Any, Any], rows: list[dict[str, Any]], pk: str) -> int:
    """Deactivate rows the dataset no longer carries. Never delete them."""
    seeded = {row[pk] for row in rows}
    count = 0
    for key, row in existing.items():
        if key not in seeded and row.is_active:
            row.is_active = False
            count += 1
    return count


async def seed_reference(
    session: AsyncSession, *, datasets: Sequence[str] = DATASETS, managed: bool | None = None
) -> list[SeedOutcome]:
    """Apply every dataset in foreign-key order.

    Flushes but does **not** commit: the caller owns the transaction, so a seed can
    be part of a larger provisioning step or rolled back for a dry run.
    """
    if managed is None:
        connection = await session.connection()
        managed = await connection.run_sync(
            lambda conn: inspect(conn).has_table("reference_revision")
        )
    return [await _seed_table(session, name, managed=managed) for name in datasets]


async def apply_reference_seed(
    url: str, *, dry_run: bool = False, datasets: Sequence[str] = DATASETS
) -> list[SeedOutcome]:
    """Seed one database, committing unless ``dry_run``."""
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as session:
            outcomes = await seed_reference(session, datasets=datasets)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        return outcomes
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seeds.reference",
        description="Seed country, state and currency into one service database.",
    )
    parser.add_argument("service", help="service name, e.g. identity — selects the env var")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change, then roll back",
    )
    args = parser.parse_args(argv)

    datasets = DATASETS
    if args.service == "catalog":
        from billing_platform.reference import register_language

        register_language()
        datasets = (*DATASETS, "language")
    outcomes = asyncio.run(
        apply_reference_seed(database_url(args.service), dry_run=args.dry_run, datasets=datasets)
    )
    for outcome in outcomes:
        print(outcome)  # noqa: T201  a CLI's only output channel
    if args.dry_run:
        print("dry run: rolled back")  # noqa: T201
    return 0

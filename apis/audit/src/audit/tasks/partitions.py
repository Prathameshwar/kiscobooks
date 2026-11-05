"""Partition lifecycle jobs: create months ahead, drop expired ones (docs/audit.md §6).

**These run under a privileged maintenance credential, never the service's own DB user.**
The runtime grant is INSERT and SELECT only (§4.1) — deliberately unable to ``ALTER`` or
``DROP`` — so partition management is a separate, audited job on its own connection, the
same split the migration grant uses. Hence these take an :class:`AsyncConnection`, not a
tenant-scoped session.

The *decisions* (which months are missing, which partitions are expired) are pure and
tested in ``domain/partitions``; the code here is the thin DDL executor and is exercised
against MySQL (the ``mysql`` marker / smoke tool), since RANGE partitioning does not exist
on SQLite.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from audit.config import Settings
from audit.domain import partitions, retention

_TABLE = "audit_event"


async def existing_partitions(  # pragma: no cover - information_schema, MySQL-only
    connection: AsyncConnection,
) -> set[str]:
    """The partition names currently defined on ``audit_event`` in this schema."""
    result = await connection.execute(
        text(
            "SELECT PARTITION_NAME FROM information_schema.PARTITIONS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
            "AND PARTITION_NAME IS NOT NULL"
        ),
        {"t": _TABLE},
    )
    return {row[0] for row in result}


async def provision_ahead(  # pragma: no cover - DDL over the tested pure planner, MySQL-only
    connection: AsyncConnection, *, today: dt.date, ahead: int
) -> list[str]:
    """Split ``pmax`` into any missing near-future months. Returns the names created.

    One ``REORGANIZE`` per month, in ascending order, each carrying the tail forward as a
    fresh ``pmax`` so an insert never falls into the catch-all for want of a partition.
    Partition names and bounds are built from validated integers (``domain/partitions``),
    never string-formatted user input.
    """
    existing = await existing_partitions(connection)
    created: list[str] = []
    for year, month in partitions.missing_months(existing, today=today, ahead=ahead):
        name = partitions.partition_name(year, month)
        bound = partitions.upper_bound_literal(year, month)
        await connection.exec_driver_sql(
            f"ALTER TABLE {_TABLE} REORGANIZE PARTITION {partitions.MAX_PARTITION} INTO ("
            f"PARTITION {name} VALUES LESS THAN ('{bound}'), "
            f"PARTITION {partitions.MAX_PARTITION} VALUES LESS THAN (MAXVALUE))"
        )
        created.append(name)
    return created


async def drop_expired(  # pragma: no cover - DDL over the tested pure planner, MySQL-only
    connection: AsyncConnection, *, today: dt.date, settings: Settings
) -> list[str]:
    """Drop whole partitions past the longest retention floor. Returns the names dropped.

    Uses :func:`retention.max_retention_days` — a partition mixes categories, so it is kept
    until even the longest-lived (``security``/``money``, 7y) has expired (§6). Archival to
    object storage, if the policy requires recoverability, happens before this runs.
    """
    days = retention.max_retention_days(settings)
    existing = await existing_partitions(connection)
    dropped: list[str] = []
    for name in partitions.droppable(existing, today=today, retention_days=days):
        await connection.exec_driver_sql(f"ALTER TABLE {_TABLE} DROP PARTITION {name}")
        dropped.append(name)
    return dropped

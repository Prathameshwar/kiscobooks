"""Ties the scheduled jobs into one pass and the interval loop (docs/audit.md §6).

Two cadences, deliberately separate by privilege:

* **Chain verification** is read-only and runs under the service session — exposed as
  :func:`run_chain_verification`, which is unit-tested.
* **Partition provisioning and expiry** are DDL and run under the privileged maintenance
  credential on its own connection (``tasks/partitions``); :func:`run_partition_maintenance`
  is thin transport over the tested pure planners and is not unit-tested (no partitions on
  SQLite).

:func:`run_scheduler` is the Celery-Beat-style interval loop, live-only.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from audit.domain.hash_chain import ChainBreak
from audit.tasks import verify


async def run_chain_verification(db: AsyncSession) -> dict[uuid.UUID, list[ChainBreak]]:
    """Verify every tenant's hash chain; returns the tenants with breaks (empty = clean)."""
    return await verify.verify_all_chains(db)


async def run_partition_maintenance(  # pragma: no cover - DDL, MySQL-only, privileged
    connection: Any, *, settings: Any, today: dt.date
) -> dict[str, list[str]]:
    """Provision months ahead and drop expired partitions on a privileged connection."""
    from audit.tasks import partitions

    created = await partitions.provision_ahead(
        connection, today=today, ahead=settings.partition_months_ahead
    )
    dropped = await partitions.drop_expired(connection, today=today, settings=settings)
    return {"created": created, "dropped": dropped}


async def run_scheduler(  # pragma: no cover - live interval loop
    settings: Any, session_factory: Any
) -> None:
    """Run maintenance on an interval. Live-only; the work it calls is tested elsewhere."""
    raise NotImplementedError("wired to Celery Beat at deployment (docs/audit.md §6)")

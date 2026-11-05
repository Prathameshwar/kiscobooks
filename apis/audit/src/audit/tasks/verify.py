"""Scheduled hash-chain verification (docs/audit.md §4.2).

Recomputes each tenant's chain and reports breaks — a retroactive edit or a deleted row
shows up as a ``prev_hash`` mismatch or a ``sequence`` gap. Whether a break pages someone
or files a report is an ops decision on the alert, not a code toggle (§7 decision).

Read-only, so it runs comfortably under the service's SELECT grant. Iterating every
tenant is a deliberate cross-tenant read and uses ``unfiltered()`` — the one greppable,
audited escape hatch (CLAUDE.md §5.3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.tenant_context import tenant_scope, unfiltered
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from audit.domain import hash_chain
from audit.domain.hash_chain import ChainBreak
from audit.models import AuditEvent


def _row_fields(event: AuditEvent) -> dict[str, Any]:
    """An event row as the dict :func:`hash_chain.verify_chain` expects."""
    fields: dict[str, Any] = {name: getattr(event, name) for name in hash_chain.HASHED_FIELDS}
    fields["prev_hash"] = event.prev_hash
    fields["row_hash"] = event.row_hash
    return fields


async def verify_tenant_chain(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    page_size: int = 1000,
) -> list[ChainBreak]:
    """Verify the complete chain with bounded pages and at most 1000 diagnostics."""
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    breaks: list[ChainBreak] = []
    previous: bytes | None = None
    sequence: int | None = None
    pivot: tuple[int, dt.datetime, uuid.UUID] | None = None
    with tenant_scope(tenant_id):
        while True:
            # Sequence is untrusted evidence: a duplicate must not disappear at a boundary.
            statement = (
                select(AuditEvent)
                .order_by(AuditEvent.sequence, AuditEvent.occurred_at, AuditEvent.id)
                .limit(page_size)
            )
            if pivot is not None:
                statement = statement.where(
                    tuple_(AuditEvent.sequence, AuditEvent.occurred_at, AuditEvent.id) > pivot
                )
            rows = list(await db.scalars(statement))
            if not rows:
                return breaks
            breaks.extend(
                hash_chain.verify_chain(
                    [_row_fields(row) for row in rows],
                    initial_prev=previous,
                    initial_sequence=sequence,
                )
            )
            if len(breaks) >= 1000:
                return breaks[:999] + [
                    ChainBreak(rows[-1].sequence, "diagnostic limit reached; verification stopped")
                ]
            last = rows[-1]
            previous, sequence = last.row_hash, last.sequence
            pivot = (last.sequence, last.occurred_at, last.id)


async def verify_all_chains(db: AsyncSession) -> dict[uuid.UUID, list[ChainBreak]]:
    """Page tenant identifiers; each chain walk also uses bounded pages."""
    broken: dict[uuid.UUID, list[ChainBreak]] = {}
    pivot: uuid.UUID | None = None
    while True:
        with unfiltered():
            statement = (
                select(AuditEvent.tenant_id).distinct().order_by(AuditEvent.tenant_id).limit(100)
            )
            if pivot is not None:
                statement = statement.where(AuditEvent.tenant_id > pivot)
            tenants = list(await db.scalars(statement))
        if not tenants:
            return broken
        for tenant_id in tenants:
            breaks = await verify_tenant_chain(db, tenant_id)
            if breaks:
                broken[tenant_id] = breaks
        pivot = tenants[-1]

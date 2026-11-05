"""Bounded keyset source scans; every query pins epoch, company and sequence."""

import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.errors import ConflictError
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from reports.models.source_versions import ReportFactVersion

PAGE_BYTES = 1024 * 1024
COMPONENT_BYTES = 16 * 1024 * 1024


def fact_bytes(row: ReportFactVersion) -> int:
    return row.wire_bytes


async def fact_pages(
    db: AsyncSession,
    query: Select[tuple[ReportFactVersion]],
    *,
    key: Literal["source_id", "ordinal"] = "source_id",
) -> AsyncIterator[list[ReportFactVersion]]:
    """Two bounded buffered reads per page, with immutable byte evidence read first."""
    order = getattr(ReportFactVersion, key)
    after = None
    while True:
        page = query if after is None else query.where(order > after)
        candidates = (
            await db.execute(
                page.with_only_columns(ReportFactVersion.id, ReportFactVersion.wire_bytes)
                .order_by(order)
                .limit(200)
            )
        ).tuples()
        identities: list[uuid.UUID] = []
        size = 0
        for identity, width in candidates:
            if width <= 0 or width > PAGE_BYTES:
                raise ConflictError("source row exceeds its supported memory bound")
            if identities and size + width > PAGE_BYTES:
                break
            identities.append(identity)
            size += width
        if not identities:
            return
        rows = list(
            await db.scalars(page.where(ReportFactVersion.id.in_(identities)).order_by(order))
        )
        if len(rows) != len(identities):
            raise ConflictError("immutable source page changed during retrieval")
        after = getattr(rows[-1], key)
        yield rows


async def bounded_rows(
    db: AsyncSession,
    query: Select[tuple[ReportFactVersion]],
    *,
    maximum: int = 20000,
    byte_limit: int = COMPONENT_BYTES,
) -> list[ReportFactVersion]:
    """Inspect bounded immutable byte evidence before requesting buffered JSON payloads."""
    candidates = list(
        (
            await db.execute(
                query.with_only_columns(ReportFactVersion.id, ReportFactVersion.wire_bytes).limit(
                    maximum + 1
                )
            )
        ).tuples()
    )
    if len(candidates) > maximum or sum(size for _, size in candidates) > byte_limit:
        raise ConflictError("source component exceeds its supported memory bound")
    if not candidates:
        return []
    return list(
        await db.scalars(
            query.where(ReportFactVersion.id.in_([identity for identity, _ in candidates])).limit(
                maximum
            )
        )
    )


@dataclass(frozen=True)
class SourceView:
    company: uuid.UUID
    epoch: uuid.UUID
    sequence: int

    def predicate(
        self, model: Any = ReportFactVersion, *, live: bool = True
    ) -> ColumnElement[bool]:
        return and_(
            model.company_id == self.company,
            model.epoch_id == self.epoch,
            model.valid_from_sequence <= self.sequence,
            or_(model.valid_to_sequence.is_(None), model.valid_to_sequence > self.sequence),
            *([model.data.is_not(None)] if live else []),
        )

    def rows(self, entity: str) -> Select[tuple[ReportFactVersion]]:
        return select(ReportFactVersion).where(self.predicate(), ReportFactVersion.entity == entity)

    async def lookup(
        self,
        db: AsyncSession,
        entity: str,
        identities: Iterable[uuid.UUID],
    ) -> dict[uuid.UUID, ReportFactVersion]:
        ids = set(identities)
        if len(ids) > 1000:
            raise ValueError("source lookup exceeds the batch bound")
        if not ids:
            return {}
        return {
            row.source_id: row
            for row in await bounded_rows(
                db, self.rows(entity).where(ReportFactVersion.source_id.in_(ids)), maximum=1000
            )
        }

    async def pages(
        self,
        db: AsyncSession,
        entity: str,
        *,
        since: int | None = None,
        after_source: uuid.UUID | None = None,
    ) -> AsyncIterator[list[ReportFactVersion]]:
        query = self.rows(entity)
        if since is not None:
            query = query.where(ReportFactVersion.valid_from_sequence > since)
        if after_source is not None:
            query = query.where(ReportFactVersion.source_id > after_source)
        async for rows in fact_pages(db, query):
            yield rows

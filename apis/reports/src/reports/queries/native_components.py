"""Bounded source components shared by detail-query families; all reads retain scope guards."""

import itertools
import uuid
from collections import defaultdict
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.statements import Facts
from reports.models.source_versions import ReportFactVersion
from reports.queries.source_versions import COMPONENT_BYTES, SourceView, bounded_rows
from reports.schemas.requests import RunRequest
from reports.tasks.source_verification import closure


class ComponentLoader:
    def __init__(self, db: AsyncSession, view: SourceView):
        self.db, self.view = db, view
        self.records: dict[tuple[str, uuid.UUID], ReportFactVersion] = {}
        self.size = 0

    def add(self, rows: list[ReportFactVersion]) -> None:
        for row in rows:
            key = row.entity, row.source_id
            if key not in self.records:
                self.size += row.wire_bytes
                if len(self.records) >= 20000 or self.size > COMPONENT_BYTES:
                    raise ConflictError("native detail component exceeds its supported bound")
                self.records[key] = row

    async def matching(self, entity: str, *conditions: Any) -> None:
        self.add(await bounded_rows(self.db, self.view.rows(entity).where(*conditions)))

    async def identities(self, entity: str, identities: list[uuid.UUID]) -> None:
        for batch in itertools.batched(identities, 200):
            found = await self.view.lookup(self.db, entity, batch)
            if len(found) != len(set(batch)):
                raise ConflictError("native detail source reference is missing")
            self.add(list(found.values()))

    async def finish(self) -> dict[tuple[str, str], dict[str, Any]]:
        return await closure(self.db, self.view, self.records.values())


class ComponentFacts(Facts):
    def __init__(
        self,
        dimensions: Facts,
        component: dict[tuple[str, str], dict[str, Any]],
        lineage: dict[str, dict[str, Any]],
        *,
        selected_journals: set[str] | None = None,
        grouped_lines: list[dict[str, Any]] | None = None,
    ):
        self.rows = defaultdict(
            dict, {entity: dict(values) for entity, values in dimensions.rows.items()}
        )
        for (entity, identity), value in sorted(component.items()):
            self.rows[entity][identity] = value
        self.accounts, self.groups, self.journals = (
            self.rows["account"],
            self.rows["account_group"],
            self.rows["journal"],
        )
        self.finance, self.currency = dimensions.finance, dimensions.currency
        self.links, self.selected_journals, self.grouped_lines = (
            lineage,
            selected_journals,
            grouped_lines,
        )

    def lineage(self) -> dict[str, dict[str, Any]]:
        return self.links

    def lines(self, query: RunRequest) -> list[dict[str, Any]]:
        if self.grouped_lines is not None:
            return self.grouped_lines
        values = super().lines(query)
        return (
            values
            if self.selected_journals is None
            else [row for row in values if row["journal_id"] in self.selected_journals]
        )

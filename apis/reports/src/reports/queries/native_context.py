"""Bounded frozen dimensions shared by native financial query families."""

import datetime as dt
import uuid
from dataclasses import dataclass

from billing_platform.errors import ConflictError, ValidationFailedError
from reporting_contract.contract import Fact, Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.statements import Facts
from reports.models.source_versions import ReportSourceCut, ReportSourceEpoch
from reports.queries.projection import QUERY_VERSION
from reports.queries.source_versions import COMPONENT_BYTES, SourceView, bounded_rows
from reports.schemas.requests import RunRequest
from reports.tasks.source_versions import fact


@dataclass
class NativeContext:
    view: SourceView
    data: Facts
    coverage: dt.date

    @classmethod
    async def load(
        cls,
        db: AsyncSession,
        company: uuid.UUID,
        generation: uuid.UUID,
    ) -> "NativeContext":
        cut = await db.scalar(
            select(ReportSourceCut).where(
                ReportSourceCut.company_id == company,
                ReportSourceCut.generation_id == generation,
            )
        )
        if cut is None or cut.verification is None:
            raise ConflictError("native queries require a verified source cut")
        epoch = await db.scalar(
            select(ReportSourceEpoch).where(
                ReportSourceEpoch.company_id == company,
                ReportSourceEpoch.id == cut.epoch_id,
            )
        )
        if epoch is None or epoch.query_version != QUERY_VERSION:
            raise ConflictError("source query projection requires a fresh generation or compaction")
        manifest = Manifest.model_validate(cut.manifest)
        if manifest.control.coverage_start is None:
            raise ConflictError("native queries require retained history coverage")
        view = SourceView(company, cut.epoch_id, cut.sequence)
        facts: list[Fact] = []
        size = 0
        for entity in (
            "financial_setup",
            "account_head",
            "account_group",
            "account",
            "fiscal_year",
            "opening_batch",
        ):
            rows = await bounded_rows(db, view.rows(entity), byte_limit=COMPONENT_BYTES - size)
            size += sum(row.wire_bytes for row in rows)
            facts.extend(fact(row) for row in rows)
        return cls(view, Facts(facts), manifest.control.coverage_start)

    async def validate(self, db: AsyncSession, query: RunRequest) -> None:
        from reports.domain.reporting.opening_coverage import includes_ytd

        if (
            query.date_from is None
            or query.date_to is None
            or (query.date_from < self.coverage and not includes_ytd(self.data.rows, query))
        ):
            from reports.domain.reporting.history_coverage import InsufficientHistoryError

            raise InsufficientHistoryError("requested history precedes retained owner coverage")
        if query.basis == "BASE" and query.currency not in {None, self.data.currency}:
            raise ValidationFailedError("base reporting currency differs from the company")
        for name, entity in (
            ("account_id", "account"),
            ("tax_ledger_id", "account"),
            ("group_id", "account_group"),
            ("party_id", "party"),
            ("invoice_id", "invoice_record"),
            ("journal_id", "journal"),
        ):
            value = getattr(query, name)
            if value is not None:
                selected = await self.view.lookup(db, entity, [value])
                if not selected:
                    raise ValidationFailedError(
                        "report filter is outside the frozen company source"
                    )
                # Financial aggregates revalidate the party against their dimensions.
                # Invoice detail components own their header selection; never seed a
                # header here that could escape a later date/batch selection.
                if entity == "party":
                    data = selected[value].data
                    if data is None:
                        raise ValidationFailedError(
                            "report filter is outside the frozen company source"
                        )
                    self.data.rows[entity][str(value)] = data

    def accounts(self, query: RunRequest) -> list[uuid.UUID]:
        return [
            uuid.UUID(key)
            for key, row in sorted(self.data.accounts.items())
            if self.data.selected(row, key, query)
        ]

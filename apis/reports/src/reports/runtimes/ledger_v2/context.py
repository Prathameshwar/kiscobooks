"""Frozen v2 ledger dimensions and projection contract; preserve this package for retained runs."""

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.source_versions import ReportSourceCut, ReportSourceEpoch
from reports.runtimes.ledger_v2.parameters import RunRequest
from reports.runtimes.ledger_v2.source import COMPONENT_BYTES, SourceView, bounded_rows


class Dimensions:
    def __init__(self, rows: dict[str, dict[str, dict[str, Any]]]):
        self.rows = rows
        self.accounts, self.groups = rows["account"], rows["account_group"]
        finance = list(rows["financial_setup"].values())
        if len(finance) != 1:
            raise ConflictError("one authoritative financial setup is required")
        self.currency = str(finance[0]["base_currency"])

    def ancestry(self, group: str) -> list[str]:
        result, seen = [], set()
        while group:
            if group in seen or group not in self.groups:
                raise ConflictError("invalid frozen classification hierarchy")
            seen.add(group)
            result.append(group)
            group = self.groups[group]["parent_id"]
        return result

    def selected(self, account: dict[str, Any], identity: str, query: RunRequest) -> bool:
        return not (
            (query.account_id and identity != str(query.account_id))
            or (query.group_id and str(query.group_id) not in self.ancestry(account["group_id"]))
            or (query.party_id and account["party_id"] != str(query.party_id))
            or (query.role and account["party_role"] != query.role)
            or (query.code == "CASH_BOOK" and account["kind"] != "CASH")
            or (query.code == "BANK_BOOK" and account["kind"] != "BANK")
            or (query.code == "PARTY_LEDGER" and account["kind"] != "PARTY")
        )


@dataclass
class NativeContext:
    view: SourceView
    data: Dimensions
    coverage: dt.date

    @classmethod
    async def load(
        cls, db: AsyncSession, company: uuid.UUID, generation: uuid.UUID
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
        if epoch is None or epoch.query_version != 4:
            raise ConflictError("retained ledger v2 requires query projection version 4")
        try:
            coverage = dt.date.fromisoformat(cut.verification["coverage_start"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ConflictError("retained ledger coverage is unavailable") from exc
        view = SourceView(company, cut.epoch_id, cut.sequence)
        rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        size = 0
        for entity in (
            "financial_setup",
            "account_head",
            "account_group",
            "account",
            "fiscal_year",
        ):
            records = await bounded_rows(db, view.rows(entity), byte_limit=COMPONENT_BYTES - size)
            size += sum(row.wire_bytes for row in records)
            for row in records:
                if row.data is not None:
                    rows[entity][str(row.source_id)] = row.data
        return cls(view, Dimensions(rows), coverage)

    async def validate(self, db: AsyncSession, query: RunRequest) -> None:
        if query.date_from < self.coverage:
            raise ConflictError("requested history precedes retained owner coverage")
        if query.basis == "BASE" and query.currency not in {None, self.data.currency}:
            raise ValidationFailedError("base reporting currency differs from the company")
        for name, entity in (
            ("account_id", "account"),
            ("group_id", "account_group"),
            ("party_id", "party"),
            ("journal_id", "journal"),
        ):
            value = getattr(query, name)
            if value is not None and not await self.view.lookup(db, entity, [value]):
                raise ValidationFailedError("report filter is outside the frozen company source")

    def accounts(self, query: RunRequest) -> list[uuid.UUID]:
        return [
            uuid.UUID(key)
            for key, row in sorted(self.data.accounts.items())
            if self.data.selected(row, key, query)
        ]

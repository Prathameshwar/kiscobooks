"""Exact ledger keysets with bounded native aggregates and lineage lookups."""

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.exact import exact_decimal as money
from billing_platform.idempotency import canonical_json
from billing_platform.listing import SortColumn, SortKind, SortTerm, seek_after
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.daily_balances import ReportDailyBalance
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_links import ReportJournalLink
from reports.models.source_versions import ReportFactVersion
from reports.runtimes.ledger_v1.context import NativeContext
from reports.runtimes.ledger_v1.parameters import RunRequest
from reports.runtimes.ledger_v1.source import PAGE_BYTES

CODES = frozenset({"ACCOUNT_LEDGER", "DAY_BOOK", "PARTY_LEDGER", "CASH_BOOK", "BANK_BOOK"})
LINEAGE_KEYS = (
    "voucher_id",
    "revision_id",
    "execution_id",
    "kind",
    "profile",
    "type_revision_id",
    "class_id",
    "configuration_hash",
)


def fixed(value: Decimal) -> str:
    return format(money(format(value, "f")), ".4f")


class LedgerQuery:
    def __init__(self, context: NativeContext, query: RunRequest):
        if query.code not in CODES:
            raise ValueError("unsupported native ledger definition")
        self.context, self.query = context, query
        self.accounts = context.accounts(query)
        self.filtered = bool(
            query.account_id
            or query.group_id
            or query.party_id
            or query.role
            or query.code not in {"ACCOUNT_LEDGER", "DAY_BOOK"}
        )
        self.line = ReportPostedLine

    def source(self, *columns: Any) -> Any:
        return self.source_for(self.line, *columns)

    def source_for(self, line: Any, *columns: Any) -> Any:
        return select(*columns).where(
            line.company_id == self.context.view.company,
            line.epoch_id == self.context.view.epoch,
            line.valid_from_sequence <= self.context.view.sequence,
            *([line.account_id.in_(self.accounts)] if self.filtered else []),
            *([line.currency == self.query.currency] if self.query.basis == "TRANSACTION" else []),
        )

    def order(self) -> tuple[Any, ...]:
        return (
            self.line.posting_date,
            self.line.journal_id,
            self.line.line_sequence,
            self.line.line_id,
        )

    @staticmethod
    def boundary(value: list[Any]) -> tuple[dt.date, uuid.UUID, int, uuid.UUID]:
        try:
            if len(value) != 4 or type(value[2]) is not int or value[2] < 1:
                raise ValueError("invalid key")
            return (
                dt.date.fromisoformat(value[0]),
                uuid.UUID(value[1]),
                value[2],
                uuid.UUID(value[3]),
            )
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationFailedError("invalid native ledger cursor") from exc

    def seek(self, value: list[Any], *, before: bool = False) -> Any:
        kinds: tuple[SortKind, ...] = ("date", "uuid", "integer", "uuid")
        terms = [
            SortTerm(str(index), before, SortColumn(column, kind))
            for index, (column, kind) in enumerate(zip(self.order(), kinds, strict=True))
        ]
        return seek_after(terms, self.boundary(value))

    async def balances(
        self,
        db: AsyncSession,
        accounts: list[uuid.UUID],
        before: list[Any] | None = None,
    ) -> dict[str, Decimal]:
        if not accounts:
            return {}
        boundary = self.boundary(before)[0] if before is not None else self.query.date_from
        day = ReportDailyBalance
        amount = day.base_amount if self.query.basis == "BASE" else day.amount
        signed = case((day.side == "DEBIT", amount), else_=-amount)
        statement = (
            self.source_for(day, day.account_id, func.sum(signed))
            .where(day.account_id.in_(accounts), day.posting_date < boundary)
            .group_by(day.account_id)
        )
        balances = {
            str(identity): money(value) for identity, value in (await db.execute(statement)).all()
        }
        if before is not None:
            line = self.line
            amount = line.base_amount if self.query.basis == "BASE" else line.amount
            signed = case((line.side == "DEBIT", amount), else_=-amount)
            statement = (
                self.source(line.account_id, func.sum(signed))
                .where(
                    line.account_id.in_(accounts),
                    line.posting_date == boundary,
                    self.seek(before, before=True),
                )
                .group_by(line.account_id)
            )
            with localcontext() as arithmetic:
                arithmetic.prec = 48
                for identity, value in (await db.execute(statement)).all():
                    key = str(identity)
                    balances[key] = balances.get(key, Decimal(0)) + money(value)
        return balances

    async def lineage(
        self, db: AsyncSession, journals: list[uuid.UUID]
    ) -> dict[str, dict[str, Any]]:
        version = ReportFactVersion
        statement = (
            select(version.id, version.source_id, version.wire_bytes, ReportJournalLink.journal_id)
            .join(
                ReportJournalLink,
                and_(
                    ReportJournalLink.version_id == version.id,
                    ReportJournalLink.company_id == self.context.view.company,
                    ReportJournalLink.epoch_id == self.context.view.epoch,
                ),
            )
            .where(
                self.context.view.predicate(),
                version.entity == "voucher_execution",
                ReportJournalLink.journal_id.in_(journals),
            )
            .order_by(version.source_id)
            .limit(1001)
        )
        metadata = (await db.execute(statement)).all()
        if len(metadata) > 1000 or sum(row.wire_bytes for row in metadata) > PAGE_BYTES:
            raise ConflictError("journal lineage exceeds its supported page bound")
        sources = await self.context.view.lookup(
            db, "voucher_execution", [row.source_id for row in metadata]
        )
        result = {}
        for row in metadata:
            data = sources[row.source_id].data
            if data is None:
                raise ConflictError("journal lineage source is unavailable")
            result[str(row.journal_id)] = {key: data.get(key) for key in LINEAGE_KEYS}
        return result

    async def entries(
        self,
        db: AsyncSession,
        after: list[Any] | None,
        limit: int,
        carry: dict[str, Decimal] | None = None,
    ) -> list[tuple[list[Any], dict[str, Any]]]:
        if not 1 <= limit <= 201:
            raise ValueError("invalid entry page bound")
        statement = self.entry_selection(after, limit)
        candidates = (await db.execute(statement)).all()
        selected: list[Any] = []
        width = 0
        for row in candidates:
            size = row.wire_bytes
            if size > PAGE_BYTES:
                raise ConflictError("ledger row exceeds its supported page bound")
            if selected and width + size > PAGE_BYTES:
                break
            selected.append(row)
            width += size
        if not selected:
            return []
        return await self.entry_values(db, selected, carry)

    def entry_selection(self, after: list[Any] | None, limit: int) -> Any:
        line = self.line
        statement = self.source(
            line.line_id.label("source_id"),
            line.source_bytes.label("wire_bytes"),
            line.journal_id,
            line.posting_date,
            line.line_sequence,
        ).where(line.posting_date >= self.query.date_from, line.posting_date <= self.query.date_to)
        if after is not None:
            statement = statement.where(self.seek(after))
        return statement.order_by(*self.order()).limit(limit)

    async def entry_values(
        self, db: AsyncSession, selected: list[Any], carry: dict[str, Decimal] | None
    ) -> list[tuple[list[Any], dict[str, Any]]]:
        lines = await self.context.view.lookup(
            db, "journal_line", [row.source_id for row in selected]
        )
        journals = await self.context.view.lookup(
            db, "journal", [row.journal_id for row in selected]
        )
        lineage = await self.lineage(db, list(journals))
        first = selected[0]
        start = [
            first.posting_date.isoformat(),
            str(first.journal_id),
            first.line_sequence,
            str(first.source_id),
        ]
        balances = {} if carry is None else carry
        missing = {
            row.account_id
            for row in lines.values()
            if row.account_id is not None and str(row.account_id) not in balances
        }
        balances.update(await self.balances(db, list(missing), start))
        result = []
        with localcontext() as decimal_context:
            decimal_context.prec = 48
            for metadata in selected:
                data = lines[metadata.source_id].data
                header = journals[metadata.journal_id].data
                if data is None or header is None:
                    raise ConflictError("ledger source is unavailable")
                account = self.context.data.accounts[data["account_id"]]
                value = money(data["base_amount"] if self.query.basis == "BASE" else data["amount"])
                balance = balances.get(data["account_id"], Decimal(0)) + (
                    value if data["side"] == "DEBIT" else -value
                )
                balances[data["account_id"]] = balance
                value_row = {
                    "row_kind": "ENTRY",
                    "line_id": str(metadata.source_id),
                    "journal_id": str(metadata.journal_id),
                    "number": header["number"],
                    "date": metadata.posting_date.isoformat(),
                    "account_id": data["account_id"],
                    "account_code": account["code"],
                    "account_name": account["name"],
                    "party_id": data["party_id"],
                    "role": data["role"],
                    "currency": self.query.currency or self.context.data.currency,
                    "transaction_currency": data["currency"],
                    "transaction_amount": data["amount"],
                    "base_amount": data["base_amount"],
                    "balance": fixed(balance),
                    "debit": fixed(value if data["side"] == "DEBIT" else Decimal(0)),
                    "credit": fixed(value if data["side"] == "CREDIT" else Decimal(0)),
                    **lineage.get(str(metadata.journal_id), {}),
                }
                key = [
                    value_row["date"],
                    str(metadata.journal_id),
                    metadata.line_sequence,
                    str(metadata.source_id),
                ]
                result.append((key, value_row))
        return result

    async def openings(
        self,
        db: AsyncSession,
        after: str | None,
        limit: int,
        carry: dict[str, Decimal] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        if not 1 <= limit <= 201:
            raise ValueError("invalid opening page bound")
        if self.query.code == "DAY_BOOK":
            return []
        selected = [key for key in self.accounts if after is None or str(key) > after][:limit]
        balances = await self.balances(db, selected)
        result = []
        assert self.query.date_from is not None
        for identity in selected:
            key = str(identity)
            value = balances.get(key, Decimal(0))
            if carry is not None:
                carry[key] = value
            result.append(
                (
                    key,
                    {
                        "row_kind": "OPENING",
                        "account_id": key,
                        "account_code": self.context.data.accounts[key]["code"],
                        "date": self.query.date_from.isoformat(),
                        "balance": fixed(value),
                    },
                )
            )
        return result


async def page(
    db: AsyncSession,
    context: NativeContext,
    query: RunRequest,
    limit: int,
    cursor: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Unsigned internal state; HTTP binds/signs it to run and current authority."""
    if not 1 <= limit <= 200:
        raise ValueError("invalid ledger page bound")
    state = dict(cursor or {"period": 0, "phase": "opening", "after": None, "ordinal": 0})
    if (
        set(state) != {"period", "phase", "after", "ordinal"}
        or type(state["period"]) is not int
        or state["period"] not in {0, 1}
        or state["phase"] not in {"opening", "entry"}
        or type(state["ordinal"]) is not int
        or state["ordinal"] < 0
    ):
        raise ValidationFailedError("invalid native ledger cursor")
    if state["after"] is not None:
        if state["phase"] == "opening":
            try:
                uuid.UUID(state["after"])
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationFailedError("invalid native opening cursor") from exc
        else:
            LedgerQuery.boundary(state["after"])
    queries = [query]
    if query.comparative_from and query.comparative_to:
        queries.append(
            query.model_copy(
                update={"date_from": query.comparative_from, "date_to": query.comparative_to}
            )
        )
    if state["period"] >= len(queries):
        raise ValidationFailedError("invalid native ledger period")
    rows: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    output_bytes = 0
    batch: list[tuple[Any, dict[str, Any]]]
    while len(rows) <= limit and state["period"] < len(queries):
        current = queries[state["period"]]
        await context.validate(db, current)
        ledger = LedgerQuery(context, current)
        if state["phase"] == "opening":
            batch = await ledger.openings(db, state["after"], limit + 1 - len(rows))
        else:
            batch = await ledger.entries(db, state["after"], limit + 1 - len(rows))
        if not batch:
            if state["phase"] == "opening":
                state.update(phase="entry", after=None)
            else:
                state.update(period=state["period"] + 1, phase="opening", after=None)
            continue
        for key, row in batch:
            size = len(canonical_json(row))
            if size > PAGE_BYTES:
                raise ConflictError("ledger output exceeds its supported page bound")
            if rows and output_bytes + size > PAGE_BYTES:
                return rows, positions[-1]
            output_bytes += size
            state.update(after=key, ordinal=state["ordinal"] + 1)
            rows.append(row | {"period": "CURRENT" if state["period"] == 0 else "COMPARATIVE"})
            positions.append(dict(state))
    return rows[:limit], positions[limit - 1] if len(rows) > limit else None


async def batches(
    db: AsyncSession, context: NativeContext, query: RunRequest
) -> AsyncIterator[list[dict[str, Any]]]:
    """Sequential export retains a bounded account balance map across source pages."""
    queries = [query]
    if query.comparative_from and query.comparative_to:
        queries.append(
            query.model_copy(
                update={
                    "date_from": query.comparative_from,
                    "date_to": query.comparative_to,
                }
            )
        )
    for index, current in enumerate(queries):
        await context.validate(db, current)
        ledger = LedgerQuery(context, current)
        carry: dict[str, Decimal] = {}
        opening_after = None
        while True:
            openings = await ledger.openings(db, opening_after, 200, carry)
            if not openings:
                break
            opening_after = openings[-1][0]
            yield [
                row | {"period": "CURRENT" if index == 0 else "COMPARATIVE"} for _, row in openings
            ]
        entry_after = None
        while True:
            entries = await ledger.entries(db, entry_after, 200, carry)
            if not entries:
                break
            entry_after = entries[-1][0]
            yield [
                row | {"period": "CURRENT" if index == 0 else "COMPARATIVE"} for _, row in entries
            ]

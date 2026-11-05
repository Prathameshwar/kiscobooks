"""Bounded two-sided print projection; source row counts remain auditable."""

import json
from collections.abc import Iterable
from itertools import zip_longest
from typing import Any

from reports.domain.reporting.contracts import Column
from reports.rendering.tabular import Budget, Writer, exact_number

PRINT_COLUMNS = (
    Column("left_label", "Liabilities and equity"),
    Column("left_code", "Code", "IDENTIFIER"),
    Column("left_amount", "Amount", "MONEY", "currency"),
    Column("right_label", "Assets"),
    Column("right_code", "Code", "IDENTIFIER"),
    Column("right_amount", "Amount", "MONEY", "currency"),
)


class BalanceSheetWriter:
    def __init__(self, target: Writer, budget: Budget) -> None:
        self.target, self.budget = target, budget
        self.rows: list[dict[str, Any]] = []
        self.count = 0
        self.bytes = 0
        self.currency: str | None = None

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            if row.get("side") not in {"ASSETS", "LIABILITIES_EQUITY"}:
                raise ValueError("Balance Sheet print row has an unknown side")
            currency = row.get("currency")
            if (
                not isinstance(currency, str)
                or not currency
                or (self.currency is not None and self.currency != currency)
            ):
                raise ValueError("Balance Sheet print currencies differ")
            self.currency = currency
            exact_number(row.get("amount"))
            self.count += 1
            self.bytes += len(json.dumps(row, ensure_ascii=False).encode())
            if (
                self.count > self.budget.rows
                or self.count * len(PRINT_COLUMNS) > self.budget.cells
                or self.bytes > min(self.budget.bytes, 64 * 1024 * 1024)
            ):
                raise ValueError("Balance Sheet print exceeds its bounded capacity")
            self.rows.append(row)

    def finish(self) -> None:
        left = [r for r in self.rows if r["side"] == "LIABILITIES_EQUITY"]
        right = [r for r in self.rows if r["side"] == "ASSETS"]
        for side, section in ((left, "LIABILITIES_EQUITY"), (right, "ASSET")):
            totals = [
                r for r in side if r.get("row_kind") == "TOTAL" and r.get("section") == section
            ]
            if len(totals) != 1 or not side or side[-1] is not totals[0]:
                raise ValueError("Balance Sheet print grand total is missing or duplicated")
        if exact_number(left[-1]["amount"]) != exact_number(right[-1]["amount"]):
            raise ValueError("Balance Sheet print grand totals do not reconcile")
        # Grand totals share the last printed line, independent of each side's detail length.
        final = (left.pop(), right.pop())
        for a, b in [*zip_longest(left, right), final]:
            result: dict[str, Any] = {"currency": (a or b or {})["currency"]}
            for prefix, row in (("left", a), ("right", b)):
                if row:
                    result.update(
                        {prefix + "_" + key: row.get(key) for key in ("label", "code", "amount")}
                    )
            if (a, b) == final:
                result["row_kind"] = "TOTAL"
            self.target.append([result])
        self.target.finish()
        self.rows.clear()

    def abort(self) -> None:
        self.rows.clear()
        self.target.abort()

"""Disclosed aggregate migration coverage never invents historical transactions."""

import datetime as dt
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.exact import exact_decimal


def migration(rows: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any] | None:
    available = [
        row["coverage"]
        for row in rows.get("opening_batch", {}).values()
        if row.get("status") == "FINALIZED" and row.get("coverage")
    ]
    if len(available) > 1:
        raise ConflictError("multiple finalized migration coverages require owner reconciliation")
    return available[0] if available else None


def includes_ytd(rows: dict[str, dict[str, dict[str, Any]]], query: Any) -> bool:
    coverage = migration(rows)
    return bool(
        coverage
        and coverage["mode"] == "YTD_SUMMARY"
        and query.code in {"PROFIT_LOSS", "INCOME_EXPENSE"}
        and query.date_from
        and query.date_to
        and query.date_from.isoformat() == coverage["originating_year_start"]
        and query.date_to.isoformat() >= coverage["covered_through"]
    )


def opening_earnings_bucket(rows: dict[str, dict[str, dict[str, Any]]], year_start: dt.date) -> str:
    coverage = migration(rows)
    if coverage and coverage["mode"] == "YTD_SUMMARY":
        return (
            "CURRENT_YEAR_EARNINGS"
            if coverage["originating_year_start"] == year_start.isoformat()
            else "PRIOR_UNTRANSFERRED_EARNINGS"
        )
    return "OPENING_EARNINGS"


class OpeningControls:
    """A bounded accumulator verifies summary evidence against its native GL facts."""

    def __init__(self) -> None:
        self.journals: set[str] = set()
        self.expected: dict[tuple[str, str], list[Decimal]] = defaultdict(
            lambda: [Decimal(0), Decimal(0)]
        )
        self.actual: dict[tuple[str, str], list[Decimal]] = defaultdict(
            lambda: [Decimal(0), Decimal(0)]
        )
        self.registered = False

    def register(self, row: dict[str, Any], require: Callable[[str, Any], dict[str, Any]]) -> None:
        coverage = row.get("coverage")
        if row["status"] != "FINALIZED" or not coverage or coverage["mode"] != "YTD_SUMMARY":
            return
        if self.registered:
            raise ConflictError("multiple finalized YTD openings require reconciliation")
        self.registered = True
        self.journals = set(row.get("journal_ids") or [row["journal_id"]])
        for identity in self.journals:
            journal = require("journal", identity)
            if (
                journal["kind"] != "OPENING"
                or journal["status"] != "POSTED"
                or journal["posting_date"] != coverage["posting_date"]
            ):
                raise ConflictError(
                    "YTD provenance does not identify complete native opening journals"
                )
        for entry in coverage["ytd_summary"] or []:
            account = require("account", entry["account_id"])
            group = require("account_group", account["group_id"])
            if require("account_head", group["head_id"])["nature"] not in {"INCOME", "EXPENSE"}:
                raise ConflictError("YTD source includes a non-nominal account")
            key = (entry["account_id"], entry["currency"])
            sign = 1 if entry["side"] == "DEBIT" else -1
            self.expected[key][0] += sign * exact_decimal(entry["amount"])
            self.expected[key][1] += sign * exact_decimal(entry["base_amount"])

    def add(self, line: dict[str, Any], require: Callable[[str, Any], dict[str, Any]]) -> None:
        if line["journal_id"] not in self.journals:
            return
        account = require("account", line["account_id"])
        group = require("account_group", account["group_id"])
        if require("account_head", group["head_id"])["nature"] not in {"INCOME", "EXPENSE"}:
            return
        key = (line["account_id"], line["currency"])
        sign = 1 if line["side"] == "DEBIT" else -1
        self.actual[key][0] += sign * exact_decimal(line["amount"])
        self.actual[key][1] += sign * exact_decimal(line["base_amount"])

    def finish(self) -> None:
        if {key: value for key, value in self.actual.items() if any(value)} != {
            key: value for key, value in self.expected.items() if any(value)
        }:
            raise ConflictError(
                "imported YTD source summary differs from native nominal opening GL"
            )

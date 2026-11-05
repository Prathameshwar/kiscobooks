"""Report-owned allowlists over bounded frozen output; no financial recalculation."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from functools import cmp_to_key
from typing import TYPE_CHECKING, Any

from billing_platform.errors import ValidationFailedError

from reports.domain.reporting.contracts import ReportDefinition
from reports.domain.reporting.report_specs import INVOICES, LEDGERS, STATEMENTS

if TYPE_CHECKING:
    from reports.schemas.framework import ResultQuery

TEXT_KEYS = frozenset(
    {
        "category",
        "label",
        "customer_name",
        "cost_status",
        "segment",
        "exception",
        "explanation",
        "source_entity",
        "item_code",
        "serial",
        "item_name",
        "location_code",
        "location_name",
        "lot_code",
        "unit",
        "voucher_number",
        "owner",
        "custody",
        "age_bucket",
        "provenance",
        "row_kind",
        "period",
        "kind",
        "source",
        "number",
        "account_code",
        "account_name",
        "group_code",
        "group_name",
        "reference",
        "bill_reference",
        "role",
        "direction",
        "currency",
        "report_currency",
        "nature",
        "invoice_kind",
        "tax_code",
        "tax_purpose",
        "mode",
        "state",
        "status",
        "action",
        "aging_bucket",
        "grain",
        "tracking",
        "purpose",
        "scope",
        "effect",
        "input_kind",
        "treatment",
        "credit_state",
    }
)
IDENTITY_KEYS = frozenset(
    {
        "location_id",
        "lot_id",
        "position_id",
        "origin_id",
        "movement_id",
        "layer_id",
        "pool_id",
        "transfer_id",
        "voucher_id",
        "account_id",
        "party_id",
        "group_id",
        "invoice_id",
        "item_id",
        "component_id",
        "allocation_id",
        "instrument_id",
        "statement_entry_id",
        "event_id",
        "journal_id",
        "line_id",
        "party_account_id",
        "bill_item_id",
        "source_id",
    }
)


def fields(definition: ReportDefinition) -> dict[str, str]:
    result: dict[str, str] = {
        column.key: column.kind for view in definition.views for column in view.columns
    }
    result.update({"ordinal": "INTEGER", "row_kind": "TEXT", "period": "TEXT"})
    if definition.code in LEDGERS:
        result.update(
            {key: "IDENTIFIER" for key in ("account_id", "party_id", "journal_id", "line_id")}
        )
    if definition.code in STATEMENTS | {"ACCOUNT_SUMMARY"}:
        result.update({key: "IDENTIFIER" for key in ("account_id", "group_id")})
    if definition.code in INVOICES:
        result.update(
            {key: "IDENTIFIER" for key in ("invoice_id", "party_account_id", "journal_id")}
        )
    for view in definition.views:
        for column in view.columns:
            if column.kind == "IDENTIFIER" and column.key in IDENTITY_KEYS:
                result[column.key] = "IDENTIFIER"
    if "kind" in result:
        result["row_kind"] = "TEXT"
    return result


def capabilities(definition: ReportDefinition) -> dict[str, Any]:
    if definition.code in {"PROFIT_LOSS", "BALANCE_SHEET"} and definition.version >= 6:
        return {"method": "NONE", "balance_semantics": "FULL_STATEMENT"}
    declared = fields(definition)
    search = [
        key
        for key in declared
        if key in TEXT_KEYS and key not in {"period", "currency", "report_currency"}
    ]
    return {
        "method": "POST",
        "path": "/report-runs/{id}/queries",
        "search_mode": "PREFIX",
        "search_fields": search,
        "filters": filter_fields(declared),
        "sort_fields": list(declared),
        "max_sort_fields": 3,
        "nulls": "LAST",
        "balance_semantics": "ORIGINAL_RESULT",
        "execution": "BOUNDED_WORKER",
    }


def filter_fields(declared: dict[str, str]) -> dict[str, str]:
    result = {key: kind for key, kind in declared.items() if key != "ordinal"}
    for key, kind in declared.items():
        if kind == "DATE":
            result.update({key + suffix: kind for suffix in ("_from", "_to")})
        if kind in {"MONEY", "DECIMAL", "INTEGER"} and key != "ordinal":
            result.update({key + suffix: kind for suffix in ("_min", "_max")})
    return result


def filter_target(name: str, declared: dict[str, str]) -> tuple[str, str]:
    if name in declared:
        return name, "eq"
    for suffix, operation in (("_from", "gte"), ("_to", "lte"), ("_min", "gte"), ("_max", "lte")):
        if name.endswith(suffix):
            return name.removesuffix(suffix), operation
    return name, "eq"


def scalar(value: Any, kind: str) -> Any:
    if value is None:
        return None
    try:
        if kind in {"MONEY", "DECIMAL"}:
            if len(str(value)) > 128:
                raise ValueError
            number = Decimal(str(value))
            if not number.is_finite() or number.adjusted() >= 34:
                raise ValueError
            return number
        if kind == "INTEGER":
            if isinstance(value, bool) or not re.fullmatch(r"-?\d{1,19}", str(value)):
                raise ValueError
            return int(value)
        if kind == "DATE":
            return dt.date.fromisoformat(str(value))
        if kind == "BOOLEAN":
            if value not in {True, False, "true", "false"}:
                raise ValueError
            return value in {True, "true"}
        return str(value).casefold()
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise ValidationFailedError("invalid typed result query value") from exc


def normalize(definition: ReportDefinition, query: ResultQuery) -> ResultQuery:
    declared = fields(definition)
    terms = query.sort.split(",")
    keys = [term.removeprefix("-") for term in terms]
    if (
        not 1 <= len(terms) <= 3
        or len(keys) != len(set(keys))
        or any(
            not re.fullmatch(r"-?[A-Za-z][A-Za-z0-9_]*", term) or key not in declared
            for term, key in zip(terms, keys, strict=True)
        )
    ):
        raise ValidationFailedError("unsupported result sort")
    filters = dict(query.filters)
    for name, value in query.filters.items():
        if name not in filter_fields(declared) or len(value) > 200:
            raise ValidationFailedError("unsupported result filter")
        key, _operation = filter_target(name, declared)
        if key in IDENTITY_KEYS:
            try:
                filters[name] = str(uuid.UUID(value))
            except ValueError as exc:
                raise ValidationFailedError("invalid result identity filter") from exc
        scalar(value, declared[key])
    for key, kind in declared.items():
        lower, upper = ("_from", "_to") if kind == "DATE" else ("_min", "_max")
        if key + lower in query.filters and key + upper in query.filters:
            if scalar(query.filters[key + lower], kind) > scalar(query.filters[key + upper], kind):
                raise ValidationFailedError("result filter range is reversed")
    normalized = " ".join((query.q or "").split()) or None
    if normalized is not None and len(normalized) < 2:
        raise ValidationFailedError("result search requires at least two characters")
    return query.model_copy(update={"q": normalized, "filters": filters})


def predicate(definition: ReportDefinition, query: ResultQuery) -> Callable[[dict[str, Any]], bool]:
    """Compile report allowlists and typed constants once per bounded scan."""
    declared = fields(definition)
    filters = []
    for name, value in query.filters.items():
        key, operation = filter_target(name, declared)
        filters.append((key, operation, declared[key], scalar(value, declared[key])))
    search_fields = capabilities(definition)["search_fields"]
    search = query.q.casefold() if query.q else None

    def accept(row: dict[str, Any]) -> bool:
        for key, operation, kind, expected in filters:
            raw = row.get(key, row.get("kind") if key == "row_kind" else None)
            actual = scalar(raw, kind)
            if (
                actual is None
                or (operation == "eq" and actual != expected)
                or (operation == "gte" and actual < expected)
                or (operation == "lte" and actual > expected)
            ):
                return False
        return search is None or any(
            str(row.get(key, "")).casefold().startswith(search) for key in search_fields
        )

    return accept


def select_rows(
    definition: ReportDefinition,
    query: ResultQuery,
    values: list[tuple[int, dict[str, Any]]],
) -> list[tuple[int, dict[str, Any]]]:
    query = normalize(definition, query)
    declared = fields(definition)
    accept = predicate(definition, query)
    selected = [(ordinal, row) for ordinal, row in values if accept(row)]

    def compare(left: tuple[int, dict[str, Any]], right: tuple[int, dict[str, Any]]) -> int:
        for term in query.sort.split(","):
            key = term.removeprefix("-")
            a = left[0] if key == "ordinal" else scalar(left[1].get(key), declared[key])
            b = right[0] if key == "ordinal" else scalar(right[1].get(key), declared[key])
            if a == b:
                continue
            if a is None or b is None:
                return 1 if a is None else -1
            result = (a > b) - (a < b)
            return -result if term.startswith("-") else result
        return (left[0] > right[0]) - (left[0] < right[0])

    return sorted(selected, key=cmp_to_key(compare))

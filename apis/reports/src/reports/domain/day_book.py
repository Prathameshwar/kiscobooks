"""Whole-journal Day Book selection over verified frozen owner facts."""

import uuid
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from billing_platform.display import DisplayConfiguration
from billing_platform.errors import ConflictError
from pydantic import Field, model_validator
from reporting_contract.contract import Contract, Control, Fact

from reports.domain.reconcile import fixed, money
from reports.domain.statements import Facts, calculate
from reports.schemas.report_parameters import CurrencyBasis, DateRange
from reports.schemas.requests import RunRequest


class Condition(Contract):
    field: Literal["number", "narration", "particulars", "kind"]
    operator: Literal["contains", "equals", "not_contains"] = "contains"
    value: str = Field(min_length=1, max_length=120)


class Parameters(DateRange, CurrencyBasis):
    kinds: list[str] = Field(default_factory=list, max_length=30)
    type_revision_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)
    party_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    q: str = Field(default="", max_length=120)
    amount_min: str | None = Field(default=None, pattern=r"^\d{1,15}(\.\d{1,4})?$")
    amount_max: str | None = Field(default=None, pattern=r"^\d{1,15}(\.\d{1,4})?$")
    conditions: list[Condition] = Field(default_factory=list, max_length=8)
    match: Literal["ALL", "ANY"] = "ALL"
    mode: Literal["VOUCHERS", "ACCOUNTING"] = "VOUCHERS"
    group_by: Literal["date", "kind", "particulars", "none"] = "date"
    sort: Literal["date", "-date", "number", "-amount"] = "date"

    @model_validator(mode="after")
    def ranges(self) -> Self:
        if (self.date_to - self.date_from).days > 3660:
            raise ValueError("choose a period of at most ten years")
        if self.amount_min is not None and self.amount_max is not None:
            if Decimal(self.amount_min) > Decimal(self.amount_max):
                raise ValueError("minimum amount must not exceed maximum")
        if any(not value or len(value) > 40 for value in self.kinds):
            raise ValueError("invalid voucher kind")
        return self


def matches(row: dict[str, Any], parameters: Parameters) -> bool:
    """Amount explicitly means gross journal debit, not turnover or document payable."""
    if parameters.kinds and row["kind"] not in parameters.kinds:
        return False
    if parameters.type_revision_ids and row.get("type_revision_id") not in {
        str(value) for value in parameters.type_revision_ids
    }:
        return False
    if parameters.q.strip():
        text = " ".join(
            [str(row.get(key) or "") for key in ("number", "narration", "particulars")]
            + [
                str(entry[key])
                for entry in row["entries"]
                for key in ("account_code", "account_name")
            ]
        )
        if parameters.q.strip().casefold() not in text.casefold():
            return False
    amount = Decimal(row["debit"])
    if parameters.amount_min is not None and amount < Decimal(parameters.amount_min):
        return False
    if parameters.amount_max is not None and amount > Decimal(parameters.amount_max):
        return False
    values = []
    for condition in parameters.conditions:
        value, target = str(row.get(condition.field) or "").casefold(), condition.value.casefold()
        values.append(
            value == target
            if condition.operator == "equals"
            else target not in value
            if condition.operator == "not_contains"
            else target in value
        )
    return not values or (all(values) if parameters.match == "ALL" else any(values))


def execute(
    facts: list[Fact], generation: uuid.UUID, parameters: Parameters, control: Control
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if control.coverage_start is None:
        raise ConflictError("complete source coverage is required")
    # Reuse reconciliation/calendar validation, but never pre-filter contributing lines.
    query = RunRequest(
        code="DAY_BOOK",
        generation_id=generation,
        date_from=parameters.date_from,
        date_to=parameters.date_to,
        basis=parameters.basis,
        currency=parameters.currency,
    )
    lines, evidence = calculate(facts, query, control.coverage_start)
    data = Facts(facts)
    lineage = data.lineage()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        groups[line["journal_id"]].append(line)
    selected = []
    for journal_id, entries in groups.items():
        journal = data.journals[journal_id]
        if parameters.account_id and not any(
            row["account_id"] == str(parameters.account_id) for row in entries
        ):
            continue
        if parameters.party_id and not any(
            row.get("party_id") == str(parameters.party_id)
            or data.accounts[row["account_id"]].get("party_id") == str(parameters.party_id)
            for row in entries
        ):
            continue
        debit = sum((money(row["debit"]) for row in entries), Decimal(0))
        credit = sum((money(row["credit"]) for row in entries), Decimal(0))
        if parameters.basis == "BASE" and debit != credit:
            raise ConflictError("complete journal entries do not reconcile")
        origin = lineage.get(journal_id, {})
        names = []
        for entry in entries:
            party = data.rows["party"].get(str(entry.get("party_id")), {})
            name = party.get("name")
            if name and name not in names:
                names.append(name)
        if not names:
            names = list(dict.fromkeys(entry["account_name"] for entry in entries))
        row = {
            "id": origin.get("voucher_id") or journal_id,
            "voucher_id": origin.get("voucher_id"),
            "journal_id": journal_id,
            "type_revision_id": origin.get("type_revision_id"),
            "date": journal["posting_date"],
            "number": journal.get("number") or "Unnumbered",
            "kind": origin.get("kind") or journal["kind"],
            "profile": origin.get("profile"),
            "particulars": ", ".join(names),
            "narration": journal.get("description") or "",
            "currency": parameters.currency or data.currency,
            "debit": fixed(debit),
            "credit": fixed(credit),
            "status": "POSTED",
            "reversal_of_id": journal.get("reversal_of_id"),
            "entries": entries,
            "journal_count": 1,
            "line_count": len(entries),
        }
        if matches(row, parameters):
            selected.append(row)
    # A source voucher can post on several days (including later reversals).
    # Keep daily activity separate so later effects never move to its first date.
    documents: dict[str, dict[str, Any]] = {}
    for row in selected:
        key = row["id"] + ":" + row["date"]
        if key not in documents:
            documents[key] = row | {"id": key, "journals": [row]}
        else:
            target = documents[key]
            target["journals"].append(row)
            target["date"] = min(target["date"], row["date"])
            target["debit"] = fixed(money(target["debit"]) + money(row["debit"]))
            target["credit"] = fixed(money(target["credit"]) + money(row["credit"]))
            target["journal_count"] += 1
            target["line_count"] += row["line_count"]
    values = list(documents.values())
    # Gross debit is explicitly labelled as posting value in the UI, never document total.
    if parameters.sort == "number":
        values.sort(key=lambda row: (row["number"], row["id"]))
    elif parameters.sort == "-amount":
        values.sort(key=lambda row: (-money(row["debit"]), row["id"]))
    else:
        values.sort(key=lambda row: (row["date"], row["id"]), reverse=parameters.sort == "-date")
    if parameters.group_by != "none":
        values.sort(
            key=lambda row: str(row[parameters.group_by]).casefold(),
            reverse=parameters.group_by == "date" and parameters.sort == "-date",
        )
    summary = {
        "voucher_count": len({row["id"] for row in selected}),
        "activity_count": len(documents),
        "journal_count": len(selected),
        "line_count": sum(row["line_count"] for row in selected),
        "debit": fixed(sum((money(row["debit"]) for row in selected), Decimal(0))),
        "credit": fixed(sum((money(row["credit"]) for row in selected), Decimal(0))),
        "currency": parameters.currency or data.currency,
        "basis": parameters.basis,
        "scope": "COMPLETE_MATCHING_JOURNALS"
        if parameters.basis == "BASE"
        else "SELECTED_CURRENCY_LINES",
        "by_kind": {},
        "groups": {},
    }
    for row in values:
        for collection, key in (
            (summary["by_kind"], row["kind"]),
            (
                summary["groups"],
                row[parameters.group_by] if parameters.group_by != "none" else "All",
            ),
        ):
            item = collection.setdefault(key, {"count": 0, "debit": "0.0000", "credit": "0.0000"})
            item["count"] += 1
            for field in ("debit", "credit"):
                item[field] = fixed(money(item[field]) + money(row[field]))
    for kind, item in summary["by_kind"].items():
        item["count"] = len({row["id"] for row in selected if row["kind"] == kind})
    output = values
    if parameters.mode == "ACCOUNTING":
        output = []
        for document in values:
            for journal in document["journals"]:
                for entry in journal["entries"]:
                    output.append(
                        {
                            **{key: value for key, value in journal.items() if key != "entries"},
                            **entry,
                            "particulars": document["particulars"],
                            "narration": journal["narration"],
                            "kind": document["kind"],
                        }
                    )
    return output, {**evidence, "row_count": len(output), "day_book": summary}


def calculate_activity(
    facts: list[Fact], generation: uuid.UUID, values: dict[str, Any], control: Control
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        return execute(facts, generation, Parameters.model_validate(values), control)


def export_metadata(
    parameters: dict[str, Any], summary: dict[str, Any], display: DisplayConfiguration
) -> tuple[tuple[str, str], ...]:
    """Human report context and frozen whole-result totals for printed/workbook output."""
    from billing_platform.display import number

    currency = str(summary["currency"])
    values = [
        ("Date basis", "Posting date"),
        (
            "Currency basis",
            "Company currency" if parameters["basis"] == "BASE" else "Transaction currency",
        ),
        ("Currency", currency),
        ("Vouchers", str(summary["voucher_count"])),
        ("Journal postings", str(summary["journal_count"])),
        ("Accounting lines", str(summary["line_count"])),
        (f"Total debit ({currency})", number(Decimal(summary["debit"]), display)),
        (f"Total credit ({currency})", number(Decimal(summary["credit"]), display)),
        (
            "Totals scope",
            "All complete matching journals"
            if parameters["basis"] == "BASE"
            else "All matching selected-currency entries",
        ),
    ]
    for key, label in (
        ("kinds", "Voucher kinds"),
        ("q", "Search"),
        ("amount_min", "Minimum posting value"),
        ("amount_max", "Maximum posting value"),
    ):
        value = parameters.get(key)
        if value:
            values.append((label, ", ".join(value) if isinstance(value, list) else str(value)))
    if parameters.get("party_id"):
        values.append(("Party", "Selected party"))
    if parameters.get("account_id"):
        values.append(("Ledger", "Complete journals containing the selected ledger"))
    if parameters.get("type_revision_ids"):
        values.append(("Voucher type", "All selected type revisions"))
    conditions = parameters.get("conditions", [])
    if conditions:
        values.append(
            (
                "Conditions",
                (" OR " if parameters.get("match") == "ANY" else " AND ").join(
                    f"{item['field'].replace('_', ' ').title()} "
                    f"{item['operator'].replace('_', ' ')} {item['value']}"
                    for item in conditions
                ),
            )
        )
    return tuple(values)

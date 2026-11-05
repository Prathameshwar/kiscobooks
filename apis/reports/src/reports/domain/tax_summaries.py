"""Full-result tax totals preserve supply grain, direction and document currency."""

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.reconcile import fixed, money

CODES = frozenset({"INVOICE_TAX_REGISTER", "INVOICE_CREDIT_REGISTER", "TAX_GL_BRIDGE"})


def summarize(code: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if code not in CODES:
        raise ValueError("unsupported tax summary")
    amounts: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    supplies: set[tuple[str, str]] = set()
    invoices: set[str] = set()
    event_amounts: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    positions = events = ledger_entries = 0
    count = 0
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for row in rows:
            if row.get("period", "CURRENT") != "CURRENT":
                continue
            if code == "TAX_GL_BRIDGE":
                if row["row_kind"] == "GL_ENTRY":
                    ledger_entries += 1
                    invoices.add(str(row["invoice_id"]))
                    currency = row["currency"]
                    debit = money(row["amount"]) if row["side"] == "DEBIT" else Decimal(0)
                    credit = money(row["amount"]) if row["side"] == "CREDIT" else Decimal(0)
                    amounts[currency]["debit"] += debit
                    amounts[currency]["credit"] += credit
                    amounts[currency]["net"] += debit - credit
                continue
            if code == "INVOICE_CREDIT_REGISTER":
                currency = row["currency"]
                invoices.add(str(row["invoice_id"]))
                if row["row_kind"] == "CREDIT_POSITION":
                    positions += 1
                    for key in (
                        "recorded_tax",
                        "pending",
                        "eligible_unclaimed",
                        "claimed",
                        "suspended",
                        "blocked",
                        "rcm_discharged",
                    ):
                        amounts[currency][key] += money(row[key])
                elif row["row_kind"] == "CREDIT_EVENT":
                    events += 1
                    event_amounts[currency][row["action"]] += money(row["event_amount"])
                continue
            if row["row_kind"] != "TAX_COMPONENT":
                continue
            count += 1
            invoices.add(str(row["invoice_id"]))
            currency = row["currency"]
            sign = Decimal(-1 if row["invoice_kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"} else 1)
            amounts[currency]["tax_amount"] += sign * money(row["tax_amount"])
            direction = (
                "outward_tax" if row["invoice_kind"] in {"SALES", "CREDIT_NOTE"} else "inward_tax"
            )
            amounts[currency][direction] += sign * money(row["tax_amount"])
            supply = (currency, str(row["supply_id"]))
            if supply not in supplies:
                supplies.add(supply)
                amounts[currency]["taxable_value"] += sign * money(row["taxable_value"])
    return {
        "code": code,
        "comparison_present": any(row.get("period") == "COMPARATIVE" for row in rows),
        "row_count": len(rows),
        "invoice_count": len(invoices),
        "component_count": count,
        "supply_count": len(supplies),
        "position_count": positions,
        "event_count": events,
        "ledger_count": ledger_entries,
        "event_amounts": {
            currency: {key: fixed(value) for key, value in values.items()}
            for currency, values in sorted(event_amounts.items())
        },
        "amounts": {
            currency: {key: fixed(value) for key, value in values.items()}
            for currency, values in sorted(amounts.items())
        },
        "verification": "VERIFIED_SOURCE_LINEAGE",
    }


def credit_view(rows: list[dict[str, Any]], calculation: str) -> list[dict[str, Any]]:
    kind = {"credit_positions": "CREDIT_POSITION", "credit_events": "CREDIT_EVENT"}.get(calculation)
    return [row for row in rows if row["row_kind"] == kind] if kind else rows


def selected(row: dict[str, Any], query: Any) -> bool:
    if query.tax_code and row.get("tax_code") != query.tax_code:
        return False
    term = query.search.strip().casefold()
    return not term or any(
        term in str(row.get(key) or "").casefold()
        for key in (
            "bill_reference",
            "account_code",
            "account_name",
            "tax_code",
            "invoice_kind",
            "treatment",
            "classification_code",
            "reference",
            "action",
            "tax_purpose",
        )
    )

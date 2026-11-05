"""Versioned GSTR-3B preparation over committed return allocations."""

import calendar
import datetime as dt
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from reporting_contract.gst import COVERAGE_AREAS

RULE_VERSION = "GSTR3B_2025_10"
CALCULATION_VERSION = 1
HEADS = ("igst", "cgst", "sgst", "cess")
FIELDS = ("taxable", *HEADS)
ELIGIBLE_REGIMES = frozenset({"regular", "sez_unit", "sez_developer", "casual_taxable_person"})
FORM_ROWS = {
    "3.1a": "Outward taxable supplies (other than zero rated, nil rated and exempted)",
    "3.1b": "Outward taxable supplies (zero rated)",
    "3.1c": "Other outward supplies (nil rated, exempted)",
    "3.1d": "Inward supplies (liable to reverse charge)",
    "3.1e": "Non-GST outward supplies",
    "3.1.1i": "Supplies on which electronic commerce operator pays tax under section 9(5)",
    "3.1.1ii": "Supplies made through electronic commerce operator under section 9(5)",
    "4A": "ITC available (whether in full or part)",
    "4A1": "Import of goods",
    "4A2": "Import of services",
    "4A3": "Inward supplies liable to reverse charge (other than imports)",
    "4A4": "Inward supplies from ISD",
    "4A5": "All other ITC",
    "4B": "ITC reversed",
    "4B1": "Reversals under rules 38, 42 and 43 and section 17(5)",
    "4B2": "Other reversals",
    "4C": "Net ITC available (A minus B)",
    "4D1": "ITC reclaimed which was reversed under 4(B)(2) in an earlier period",
    "4D2": "Ineligible ITC under section 16(4) and restricted by place of supply",
    "5_EXEMPT_INTER": "Exempt, nil rated and composition inward supplies — interstate",
    "5_EXEMPT_INTRA": "Exempt, nil rated and composition inward supplies — intrastate",
    "5_NONGST_INTER": "Non-GST inward supplies — interstate",
    "5_NONGST_INTRA": "Non-GST inward supplies — intrastate",
    "INTEREST": "Interest payable",
    "LATE_FEE": "Late fee payable",
}
TAXABLE_ONLY = frozenset(
    {
        "3.1c",
        "3.1e",
        "3.1.1ii",
        "5_EXEMPT_INTER",
        "5_EXEMPT_INTRA",
        "5_NONGST_INTER",
        "5_NONGST_INTRA",
    }
)
OUTWARD = frozenset({"3.1a", "3.1b", "3.1c", "3.1e", "3.1.1i", "3.1.1ii", "3.2"})
INWARD = frozenset(
    {
        "3.1d",
        "INWARD_TAXABLE",
        "INWARD_INELIGIBLE",
        "5_EXEMPT_INTER",
        "5_EXEMPT_INTRA",
        "5_NONGST_INTER",
        "5_NONGST_INTRA",
    }
)
ITC = frozenset({"4A1", "4A2", "4A3", "4A4", "4A5", "4B1", "4B2", "4D1", "4D2"})
PORTAL_ITC = frozenset(
    {"4A1", "4A3", "4A4", "4A5", "4B1", "4B2", "4D1", "4D2", "INWARD_TAXABLE", "INWARD_INELIGIBLE"}
)


def period_bounds(period: str, frequency: str) -> tuple[dt.date, dt.date]:
    if frequency == "MONTHLY" and re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", period):
        year, month = map(int, period.split("-"))
        start = dt.date(year, month, 1)
        end = dt.date(year, month, calendar.monthrange(year, month)[1])
    elif frequency == "QRMP" and re.fullmatch(r"20[0-9]{2}-Q[1-4]", period):
        year_text, quarter = period.split("-Q")
        month = int(quarter) * 3
        start = dt.date(int(year_text), month - 2, 1)
        end = dt.date(int(year_text), month, calendar.monthrange(int(year_text), month)[1])
    else:
        raise ValueError("choose a complete statutory month or QRMP quarter")
    if start < dt.date(2025, 10, 1):
        raise ValueError("this rule version supports periods from October 2025")
    return start, end


def amounts(row: dict[str, Any]) -> dict[str, Decimal]:
    result = {}
    for key in FIELDS:
        raw = row.get(key, "0")
        if not isinstance(raw, str):
            raise ValueError("statutory money requires exact strings")
        value = Decimal(raw)
        if (
            not value.is_finite()
            or abs(value) >= Decimal("1000000000000000")
            or value.quantize(Decimal("0.0001")) != value
        ):
            raise ValueError("statutory money exceeds DECIMAL(19,4)")
        result[key] = value
    return result


def formatted(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, ".2f")


def applicable(registration: dict[str, Any]) -> bool:
    return (
        registration.get("tax_system") == "gst_in"
        and registration.get("regime") in ELIGIBLE_REGIMES
        and registration.get("country_code", "IN") == "IN"
    )


def calculate(
    records: list[dict[str, Any]],
    registration: dict[str, Any],
    start: dt.date,
    end: dt.date,
    *,
    sequence: int | None = None,
    unresolved_sources: list[str] | None = None,
) -> dict[str, Any]:
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: dict.fromkeys(FIELDS, Decimal(0)))
    issues: list[dict[str, str]] = []
    selected: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    coverage_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pos: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
        lambda: {"taxable": Decimal(0), "igst": Decimal(0)}
    )
    offsets: dict[tuple[str, str], Decimal] = defaultdict(Decimal)

    def issue(code: str, message: str, source: str = "") -> None:
        issues.append({"code": code, "message": message, "source_id": source})

    for row in sorted(records, key=lambda r: (r["return_date"], str(r.get("id", "")))):
        if (
            str(row["registration_id"]) != str(registration["id"])
            or not start.isoformat() <= row["return_date"] <= end.isoformat()
        ):
            continue
        category = row["category"]
        value = amounts(row)
        selected.append(row)
        if category == "COVERAGE":
            coverage_candidates[row["coverage_area"]].append(row)
            continue
        if category == "3.2":
            state = row.get("place_of_supply", "")
            own_state = str(registration.get("number", ""))[:2]
            if state == own_state or state not in {f"{code:02d}" for code in range(1, 39)} | {"97"}:
                issue(
                    "PLACE_OF_SUPPLY",
                    "Table 3.2 requires a different valid Indian state/UT.",
                    str(row.get("id", "")),
                )
                continue
            if row.get("is_advance"):
                continue
            key = (str(row.get("recipient", "")), state)
            for head in ("taxable", "igst"):
                pos[key][head] += value[head]
        if category == "OFFSET_NORMAL_ITC":
            credit = str(row.get("credit_head", "")).lower()
            for head in HEADS:
                offsets[credit, head] += value[head]
        if category in {"OFFSET_RCM_ITC", "OFFSET_ECO_ITC"}:
            issue(
                "CASH_ONLY", "Reverse charge and section 9(5) ECO liability must be offset in cash."
            )
            continue
        for head in FIELDS:
            totals[category][head] += value[head]
        if category in TAXABLE_ONLY and any(value[head] for head in HEADS):
            issue(
                "INAPPLICABLE_TAX", f"{category} allows taxable value only.", str(row.get("id", ""))
            )
        if category == "LATE_FEE" and (value["igst"] or value["cess"]):
            issue("LATE_FEE_HEAD", "Late fee is reported under central and state/UT heads only.")
        if category in {"4A1", "4A2", "3.1b"} and (value["cgst"] or value["sgst"]):
            issue("INAPPLICABLE_TAX", f"{category} does not permit central or state/UT tax.")
    for area, candidates in coverage_candidates.items():
        latest = max(row.get("covered_sequence") or 0 for row in candidates)
        current = [row for row in candidates if (row.get("covered_sequence") or 0) == latest]
        if len({row["coverage_status"] for row in current}) > 1:
            issue(
                "COVERAGE_CONFLICT",
                f"{area} has conflicting proofs for the latest source sequence.",
            )
        coverage[area] = current[-1]
    # Statutory cells have two decimals; their totals must sum those same cells.
    # Source evidence remains unchanged at its native four-decimal scale.
    for values in totals.values():
        for head in FIELDS:
            values[head] = values[head].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    for key, cell_amount in offsets.items():
        offsets[key] = cell_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    for values in pos.values():
        for head, cell_amount in values.items():
            values[head] = cell_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    recorded = {row["category"] for row in selected}
    nonzero = {row["category"] for row in selected if any(amounts(row).values())}
    activity = {
        "OUTWARD": bool(recorded & OUTWARD),
        "INWARD": bool(recorded & INWARD),
        "ITC": bool(recorded & ITC),
        "OPENING": bool(nonzero & {"OPENING_ITC", "OPENING_CASH"}),
        "PAYMENT": any(category.startswith("OFFSET_") for category in nonzero)
        or bool(
            nonzero
            & {
                "3.1a",
                "3.1b",
                "3.1d",
                "3.1.1i",
                "PRIOR_LIABILITY",
                "INTEREST",
                "LATE_FEE",
                "CASH_DEPOSIT",
            }
        ),
        "GSTR1": bool(recorded & OUTWARD) or "GSTR1" in nonzero,
        "GSTR2B": bool(recorded & PORTAL_ITC) or "GSTR2B" in nonzero,
        "IMS": bool(recorded & PORTAL_ITC) or "IMS" in nonzero,
    }
    for area in sorted(COVERAGE_AREAS):
        coverage_row = coverage.get(area)
        if coverage_row is None:
            issue("SOURCE_COVERAGE", f"{area.title()} completeness evidence is missing.")
        elif sequence is not None and coverage_row.get("covered_sequence") != sequence:
            issue(
                "STALE_COVERAGE", f"{area.title()} evidence does not cover this frozen source cut."
            )
        if (
            coverage_row is not None
            and coverage_row["coverage_status"] == "NOT_APPLICABLE"
            and activity[area]
        ):
            issue(
                "COVERAGE_NOT_APPLICABLE",
                f"{area} has recorded activity; provide complete coverage evidence.",
            )
    for source in unresolved_sources or []:
        issue("UNALLOCATED_SOURCE", "Posted GST source has no return allocation.", source)
    for area in ("GSTR1", "GSTR2B", "IMS"):
        proof = coverage.get(area)
        if (
            proof
            and proof["coverage_status"] == "COMPLETE"
            and not any(row["category"] == area for row in selected)
        ):
            issue(
                "PORTAL_EVIDENCE_MISSING",
                f"{area} coverage is marked complete but its import evidence is missing.",
            )
    for head in ("taxable", "igst"):
        disclosed = sum((value[head] for value in pos.values()), Decimal(0))
        # GST Portal Table 15 ECO supplies feed both 3.1.1(i) and 3.2.
        outward = totals["3.1a"][head] + totals["3.1.1i"][head]
        if disclosed > max(Decimal(0), outward) and disclosed > 0:
            issue(
                "DISCLOSURE_EXCEEDS_OUTWARD",
                f"Table 3.2 {head} exceeds 3.1(a) plus 3.1.1(i); reconcile source classifications.",
            )
    for target, parts in (("4A", ("4A1", "4A2", "4A3", "4A4", "4A5")), ("4B", ("4B1", "4B2"))):
        for head in HEADS:
            totals[target][head] = sum((totals[part][head] for part in parts), Decimal(0))
    for head in HEADS:
        totals["4C"][head] = totals["4A"][head] - totals["4B"][head]
        if totals["4C"][head] < 0:
            issue(
                "NEGATIVE_NET_ITC",
                f"{head.upper()} net ITC is negative; reconcile portal treatment.",
            )
        if totals["4D1"][head] > totals["4A5"][head]:
            issue(
                "RECLAIM_NOT_INCLUDED",
                "Reclaimed credit disclosure must already be included in 4(A)(5).",
            )
    payment: dict[str, dict[str, str]] = {}
    for head in HEADS:
        normal = totals["3.1a"][head] + totals["3.1b"][head] + totals["PRIOR_LIABILITY"][head]
        rcm = totals["3.1d"][head]
        eco = totals["3.1.1i"][head]
        credit_available = totals["OPENING_ITC"][head] + max(Decimal(0), totals["4C"][head])
        credit_used = sum((v for (credit, _), v in offsets.items() if credit == head), Decimal(0))
        if credit_used > credit_available:
            issue(
                "ITC_OVERDRAWN",
                f"{head.upper()} credit offsets exceed opening plus current net credit.",
            )
        itc_paid = sum((v for (_, target), v in offsets.items() if target == head), Decimal(0))
        cash_used = sum(
            (
                totals[category][head]
                for category in (
                    "OFFSET_NORMAL_CASH",
                    "OFFSET_RCM_CASH",
                    "OFFSET_ECO_CASH",
                    "OFFSET_INTEREST_CASH",
                    "OFFSET_LATE_FEE_CASH",
                )
            ),
            Decimal(0),
        )
        cash_available = totals["OPENING_CASH"][head] + totals["CASH_DEPOSIT"][head]
        if cash_used > cash_available:
            issue(
                "CASH_OVERDRAWN",
                f"{head.upper()} cash offsets exceed recorded opening and deposits.",
            )
        values = {
            "normal_liability": normal,
            "rcm_liability": rcm,
            "eco_liability": eco,
            "prior_liability": totals["PRIOR_LIABILITY"][head],
            "itc_paid": itc_paid,
            "normal_cash_paid": totals["OFFSET_NORMAL_CASH"][head],
            "rcm_cash_paid": totals["OFFSET_RCM_CASH"][head],
            "eco_cash_paid": totals["OFFSET_ECO_CASH"][head],
            "interest": totals["INTEREST"][head],
            "late_fee": totals["LATE_FEE"][head],
            "interest_cash_paid": totals["OFFSET_INTEREST_CASH"][head],
            "late_fee_cash_paid": totals["OFFSET_LATE_FEE_CASH"][head],
            "interest_unpaid": totals["INTEREST"][head] - totals["OFFSET_INTEREST_CASH"][head],
            "late_fee_unpaid": totals["LATE_FEE"][head] - totals["OFFSET_LATE_FEE_CASH"][head],
            "normal_unpaid": normal - itc_paid - totals["OFFSET_NORMAL_CASH"][head],
            "rcm_unpaid": rcm - totals["OFFSET_RCM_CASH"][head],
            "eco_unpaid": eco - totals["OFFSET_ECO_CASH"][head],
            "closing_itc": credit_available - credit_used,
            "closing_cash": cash_available - cash_used,
        }
        if any(
            values[key] < 0
            for key in (
                "normal_unpaid",
                "rcm_unpaid",
                "eco_unpaid",
                "interest_unpaid",
                "late_fee_unpaid",
            )
        ):
            issue("OVERPAYMENT", f"{head.upper()} offsets exceed the corresponding liability.")
        payment[head.upper()] = {key: formatted(value) for key, value in values.items()}
    for (credit, target), offset_amount in offsets.items():
        if offset_amount < 0 or (
            offset_amount
            and (
                (credit == "cgst" and target == "sgst")
                or (credit == "sgst" and target == "cgst")
                or ((credit == "cess") != (target == "cess"))
            )
        ):
            issue(
                "ITC_UTILISATION", "CGST/SGST cross-use and cess/non-cess cross-use are prohibited."
            )
    for head in ("igst", "cgst", "sgst"):
        if (
            Decimal(payment[head.upper()]["normal_liability"])
            - Decimal(payment[head.upper()]["itc_paid"])
        ) > 0 and any(
            value > 0
            for (credit, target), value in offsets.items()
            if credit == head and target != head
        ):
            issue("OWN_HEAD_FIRST", f"{head.upper()} credit must first cover the same tax head.")
    if totals["OPENING_ITC"]["igst"] + max(Decimal(0), totals["4C"]["igst"]) - sum(
        (value for (credit, _), value in offsets.items() if credit == "igst"), Decimal(0)
    ) > 0 and any(
        value > 0 for (credit, _), value in offsets.items() if credit in {"cgst", "sgst"}
    ):
        issue("IGST_FIRST", "Available IGST credit must be exhausted before CGST/SGST credit.")
    reconciliation = []
    for category, actual_categories in (
        ("GSTR1", ("3.1a", "3.1b", "3.1c", "3.1e")),
        ("GSTR2B", ("4A1", "4A3", "4A4", "4A5")),
    ):
        if category not in totals:
            continue
        for head in FIELDS:
            if category == "GSTR2B" and head == "taxable":
                continue
            actual = sum((totals[key][head] for key in actual_categories), Decimal(0))
            difference = actual - totals[category][head]
            reconciliation.append(
                {
                    "source": category,
                    "head": head.upper(),
                    "return_amount": formatted(actual),
                    "source_amount": formatted(totals[category][head]),
                    "difference": formatted(difference),
                }
            )
            if difference:
                issue(
                    "RECONCILIATION_DIFFERENCE",
                    f"{category} {head.upper()} differs; record and resolve the reason.",
                )
    form = {
        key: {
            head: (
                None
                if (head in HEADS and key in TAXABLE_ONLY)
                or (head == "taxable" and (key.startswith("4") or key in {"INTEREST", "LATE_FEE"}))
                or (key in {"4A1", "4A2", "3.1b"} and head in {"cgst", "sgst"})
                else formatted(totals[key][head])
            )
            for head in FIELDS
        }
        for key in FORM_ROWS
    }
    payment_rows = []
    for head in HEADS:
        for liability_kind in ("OTHER_THAN_REVERSE_CHARGE", "REVERSE_CHARGE"):
            reverse = liability_kind == "REVERSE_CHARGE"
            payment_rows.append(
                {
                    "tax_head": head.upper(),
                    "liability_kind": liability_kind,
                    "tax_payable": formatted(
                        totals["3.1d"][head]
                        if reverse
                        else totals["3.1a"][head]
                        + totals["3.1b"][head]
                        + totals["PRIOR_LIABILITY"][head]
                        + totals["3.1.1i"][head]
                    ),
                    **{
                        f"paid_{credit}": formatted(
                            Decimal(0) if reverse else offsets[credit, head]
                        )
                        for credit in HEADS
                    },
                    "paid_cash": formatted(
                        totals["OFFSET_RCM_CASH"][head]
                        if reverse
                        else totals["OFFSET_NORMAL_CASH"][head] + totals["OFFSET_ECO_CASH"][head]
                    ),
                    "interest_paid": formatted(
                        Decimal(0) if reverse else totals["OFFSET_INTEREST_CASH"][head]
                    ),
                    "late_fee_paid": formatted(
                        Decimal(0) if reverse else totals["OFFSET_LATE_FEE_CASH"][head]
                    ),
                }
            )
    nil = not issues and not any(
        row["category"] not in {"GSTR1", "GSTR2B", "IMS"} or any(amounts(row).values())
        for row in selected
        if row["category"] not in {"COVERAGE", "OPENING_ITC", "OPENING_CASH", "PREVIOUS_RETURN"}
    )
    financial_year_start = start.year if start.month >= 4 else start.year - 1
    return {
        "calculation_version": CALCULATION_VERSION,
        "rule_version": RULE_VERSION,
        "registration": registration,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "financial_year": f"{financial_year_start}-{str(financial_year_start + 1)[-2:]}",
        "currency": "INR",
        "status": "NEEDS_ATTENTION" if issues else "DRAFT",
        "nil": nil,
        "form": form,
        "row_order": list(FORM_ROWS),
        "labels": FORM_ROWS,
        "pos_rows": [
            {
                "recipient": recipient,
                "place_of_supply": state,
                **{key: formatted(value) for key, value in values.items()},
            }
            for (recipient, state), values in sorted(pos.items())
        ],
        "payment": payment,
        "inward_rows": [
            {
                "nature": label,
                "interstate": formatted(totals[category + "_INTER"]["taxable"]),
                "intrastate": formatted(totals[category + "_INTRA"]["taxable"]),
            }
            for category, label in (
                ("5_EXEMPT", "Supplies from composition taxpayers, exempt and nil rated supplies"),
                ("5_NONGST", "Non-GST supply"),
            )
        ],
        "payment_rows": payment_rows,
        "prior_liability_rows": [row for row in selected if row["category"] == "PRIOR_LIABILITY"],
        "itc_offsets": [
            {
                "credit_head": credit.upper(),
                "liability_head": target.upper(),
                "amount": formatted(value),
            }
            for (credit, target), value in sorted(offsets.items())
        ],
        "issues": issues,
        "reconciliation": reconciliation,
        "source_count": len(selected),
        "portal_json_ready": False,
        "portal_json_reason": (
            "Official upload schema and portal import validation have not been verified. "
            "Use the preparation PDF and Excel workings for review."
        ),
    }

"""GSTR-1 working papers from immutable, detailed owner evidence.

Primary supplies contribute once. HSN, documents and supplier ECO disclosures
are separate controls. Amendments display full revised values and bridge only
the differential; previously furnished IFF invoices remain traceable.
"""

import datetime as dt
import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from reporting_contract.gst_outward import AREAS, DOCUMENT_KINDS, MONEY, GstOutwardRecord

from reports.domain.gstr1_rules import (
    DOCUMENT_CATEGORIES,
    RULE_VERSION,
    STATES,
    TABLES,
    UQC,
    correction_cutoff,
    hsn_digits,
    money,
    threshold,
)

ZERO = Decimal(0)
CALCULATION_VERSION = 3
AGGREGATE_TABLES = {"7", "8", "11A", "11B", "14_TCS", "14_9_5"}
BRIDGE = {
    "3.1a": "Taxable outward supplies",
    "3.1b": "Zero-rated supplies",
    "3.1c": "Nil-rated and exempt supplies",
    "3.1e": "Non-GST outward supplies",
    "3.1.1i": "ECO section 9(5) operator liability",
    "3.1.1ii": "Supplier section 9(5) supplies",
    "OUTWARD_RCM": "Outward supplies taxed by recipient",
}


def amounts(value: dict[str, Any], sign: Decimal = Decimal(1)) -> dict[str, Decimal]:
    return {head: Decimal(value.get(head, "0")) * sign for head in MONEY}


def activity_area(kind: str) -> str:
    if kind in {"CREDIT_NOTE", "DEBIT_NOTE"}:
        return "NOTES"
    if kind.startswith("ADVANCE"):
        return "ADVANCES"
    return "ECO" if kind == "ECO_OPERATOR" else "OUTWARD"


def primary(record: dict[str, Any], item: dict[str, Any], registration: dict[str, Any]) -> str:
    details = record["details"]
    if record["kind"] == "ECO_OPERATOR":
        supplier = "B" if details["supplier_type"] == "REGISTERED" else "URP"
        recipient = "B" if details["recipient_type"] != "UNREGISTERED" else "C"
        return f"15_{supplier}2{recipient}"
    if record["kind"] in {"ADVANCE", "ADVANCE_ADJUSTMENT"}:
        return "11A" if record["kind"] == "ADVANCE" else "11B"
    if details.get("eco_scheme") == "9_5":
        return "14_9_5"
    if item["treatment"] != "TAXABLE":
        return "8"
    if details["supply_type"].startswith("EXPORT"):
        return "6A"
    if details["supply_type"].startswith("SEZ"):
        return "6B"
    if details["supply_type"] == "DEEMED_EXPORT":
        return "6C"
    if details["recipient_type"] != "UNREGISTERED":
        return "4B" if details["reverse_charge"] else "4A"
    if details["place_of_supply"] != registration["number"][:2] and Decimal(
        record["invoice_value"]
    ) > threshold(dt.date.fromisoformat(record["return_date"])):
        return "5"
    return "7"


def bridge_key(record: dict[str, Any], item: dict[str, Any]) -> str:
    details = record["details"]
    if record["kind"] == "ECO_OPERATOR":
        return "3.1.1i"
    if details.get("eco_scheme") == "9_5":
        return "3.1.1ii"
    if item["treatment"] == "NON_GST":
        return "3.1e"
    if item["treatment"] in {"EXEMPT", "NIL_RATED"}:
        return "3.1c"
    if details["supply_type"].startswith(("EXPORT", "SEZ")):
        return "3.1b"
    if details["reverse_charge"]:
        return "OUTWARD_RCM"
    return "3.1a"


def calculate(
    records: list[dict[str, Any]],
    registration: dict[str, Any],
    start: dt.date,
    end: dt.date,
    *,
    sequence: int | None = None,
    originals: dict[str, dict[str, Any]] | None = None,
    unresolved_sources: list[str] | None = None,
    comparison: dict[str, Any] | None = None,
    as_of: dt.date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    originals = originals or {}
    selected: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    seen_issues: set[tuple[str, str]] = set()
    filing_cutoffs: list[dt.date] = []

    def issue(code: str, message: str, source_id: str = "") -> None:
        identity = (code, source_id)
        if identity not in seen_issues and len(issues) < 200:
            seen_issues.add(identity)
            issues.append({"code": code, "message": message, "source_id": source_id})

    for value in records:
        if str(value["registration_id"]) != str(registration["id"]) or not (
            start.isoformat() <= value["return_date"] <= end.isoformat()
        ):
            continue
        parsed = GstOutwardRecord.model_validate(
            {key: value[key] for key in GstOutwardRecord.model_fields if key in value}
        )
        selected.append(value | parsed.model_dump(mode="json"))
    if as_of and end > as_of:
        issue(
            "PERIOD_IN_PROGRESS",
            (
                "The statutory period is still in progress; prepare the final "
                "return after it closes."
            ),
        )
    selected.sort(key=lambda row: (row["return_date"], row["document_number"], row["id"]))
    by_id = originals | {row["id"]: row for row in selected}
    amended_children: dict[str, set[str]] = defaultdict(set)
    for history in by_id.values():
        if history["kind"] == "AMENDMENT" and history.get("original_record_id"):
            amended_children[history["original_record_id"]].add(history["id"])
    superseded = {
        row["original_record_id"]
        for row in selected
        if row["kind"] in {"COVERAGE", "DOCUMENTS", "PORTAL"} and row["original_record_id"]
    }
    selected = [row for row in selected if row["id"] not in superseded]
    gst_year = start.year if start.month >= 4 else start.year - 1
    profiles = [
        profile
        for profile in registration.get("outward_profiles", [])
        if profile["valid_from"] <= start.isoformat()
        and profile["valid_from"] >= dt.date(gst_year, 4, 1).isoformat()
        and (not profile.get("valid_to") or profile["valid_to"] > end.isoformat())
    ]
    profile = profiles[0] if len(profiles) == 1 else None
    if profile is None:
        issue(
            "OUTWARD_PROFILE_MISSING",
            (
                "Configure a dated prior-year aggregate turnover and Rule 14A "
                "profile for this complete return period."
            ),
        )
    digits = hsn_digits(Decimal(profile["annual_turnover"])) if profile else None
    if (
        profile
        and start.month != end.month
        and Decimal(profile["annual_turnover"]) > Decimal("50000000")
    ):
        issue("QRMP_TURNOVER", "QRMP requires eligible aggregate turnover up to five crore.")
    totals = {key: {head: ZERO for head in MONEY} for key in TABLES}
    bridge = {key: {head: ZERO for head in MONEY} for key in BRIDGE}
    hsn: dict[tuple[str, str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: {**{head: ZERO for head in MONEY}, "quantity": ZERO, "invoice_value": ZERO}
    )
    hsn_sources: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    coverage_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for proof in selected:
        if proof["kind"] == "COVERAGE":
            coverage_groups[proof["details"]["coverage_area"]].append(proof)
    coverage: dict[str, dict[str, Any]] = {}
    for area, proofs in coverage_groups.items():
        latest = max(proof["details"]["covered_sequence"] or 0 for proof in proofs)
        current = [
            proof for proof in proofs if (proof["details"]["covered_sequence"] or 0) == latest
        ]
        if len({proof["details"]["coverage_status"] for proof in current}) > 1:
            issue(
                "COVERAGE_CONFLICT_" + area,
                "Completeness proofs at the current source cut disagree; "
                "replace the conflicting evidence.",
            )
        coverage[area] = current[-1]
    activity: set[str] = set()
    monthly_b2b: dict[str, Decimal] = defaultdict(lambda: ZERO)
    monthly_iff: dict[str, Decimal] = defaultdict(lambda: ZERO)
    primary_count: set[str] = set()
    iff_count: set[str] = set()
    series_counts: dict[str, int] = defaultdict(int)
    documents_by_category: dict[str, set[str]] = defaultdict(set)

    def emit(
        record: dict[str, Any],
        item: dict[str, Any],
        table: str,
        sign: Decimal,
        *,
        liability: bool,
        original: dict[str, Any] | None = None,
        add_totals: bool = True,
    ) -> None:
        details = record["details"]
        values = amounts(item, sign)
        display = amounts(item) if table.startswith(("9B", "9C", "11B")) else values
        if add_totals:
            for head in MONEY:
                totals[table][head] += -values[head] if table.startswith("11B") else values[head]
        rows.append(
            {
                "id": f"{record['id']}:{table}:{len(rows)}",
                "table": table,
                "table_label": TABLES[table],
                "record_id": record["id"],
                "row_role": "SOURCE",
                "source_line_id": item.get("source_line_id") or "",
                "document_number": record["document_number"],
                "document_date": record["document_date"],
                "return_date": record["return_date"],
                "kind": record["kind"],
                "recipient_gstin": details["recipient_gstin"] or "",
                "recipient_name": details["recipient_name"],
                "recipient_type": details["recipient_type"],
                "place_of_supply": details["place_of_supply"] or "",
                "supply_type": details["supply_type"],
                "reverse_charge": details["reverse_charge"],
                "rate": item["rate"],
                "invoice_value": money(Decimal(record["invoice_value"])),
                "supply_location": "INTER_STATE"
                if details["place_of_supply"] != registration["number"][:2]
                else "INTRA_STATE",
                "signed_amounts": {head: format(value, ".4f") for head, value in values.items()},
                "original_taxable": money(Decimal(original["taxable"])) if original else "",
                "differential_taxable": money(
                    (Decimal(record["taxable"]) - Decimal(original["taxable"])) * sign
                )
                if original and record["kind"] == "AMENDMENT"
                else "",
                **{
                    key: details.get(key) or ""
                    for key in (
                        "source_currency",
                        "source_invoice_value",
                        "conversion_rate",
                        "conversion_date",
                        "conversion_reference",
                    )
                },
                **{head: money(value) for head, value in display.items()},
                "currency": "INR",
                "hsn": item["hsn"],
                "uqc": item["uqc"],
                "quantity": format(Decimal(item["quantity"]) * sign, ".4f"),
                "treatment": item["treatment"],
                "operator_gstin": details["operator_gstin"] or "",
                "supplier_gstin": details["supplier_gstin"] or "",
                "eco_scheme": details["eco_scheme"] or "",
                "shipping_bill_number": details["shipping_bill_number"] or "",
                "shipping_bill_date": details["shipping_bill_date"] or "",
                "port_code": details["port_code"] or "",
                "original_document_number": original["document_number"] if original else "",
                "original_document_date": original["document_date"] if original else "",
                "amendment_chain": original.get("amendment_chain", []) if original else [],
                "original_amounts": {head: money(Decimal(original[head])) for head in MONEY}
                if original
                else {},
                "document_differential": {
                    head: money((Decimal(record[head]) - Decimal(original[head])) * sign)
                    for head in MONEY
                }
                if original and record["kind"] == "AMENDMENT"
                else {},
                "original_record_id": record["original_record_id"] or "",
                "prior_filed_channel": details["prior_filed_channel"] or "",
                "reference": record["reference"],
                "evidence_hash": record["evidence_hash"],
                "explanation": record["explanation"],
                "liability_included": liability,
                "source_entity": record["source_entity"],
                "source_id": record["source_id"] or "",
                "voucher_id": record.get("voucher_id", ""),
                "journal_id": record.get("journal_id", ""),
                "total_count": "",
                "cancelled_count": "",
                "net_count": "",
                "serial_from": "",
                "serial_to": "",
            }
        )

    def account(record: dict[str, Any], sign: Decimal, *, add_hsn: bool = True) -> None:
        details = record["details"]
        for item in details["items"]:
            key = bridge_key(record, item)
            for head, value in amounts(item, sign).items():
                bridge[key][head] += value
            if details["recipient_type"] != "UNREGISTERED" and key in {"3.1a", "3.1b", "3.1.1i"}:
                monthly_b2b[record["return_date"][:7]] += sum(
                    amounts(item, sign)[head] for head in MONEY[1:]
                )
            if add_hsn and record["kind"] not in {"ADVANCE", "ADVANCE_ADJUSTMENT"}:
                activity.add("HSN")
                category = "12_B2B" if details["recipient_type"] != "UNREGISTERED" else "12_B2C"
                hsn_key = (category, item["hsn"], item["rate"], item["uqc"])
                for head, value in amounts(item, sign).items():
                    hsn[hsn_key][head] += value
                hsn[hsn_key]["quantity"] += Decimal(item["quantity"]) * sign
                hsn[hsn_key]["invoice_value"] += sum(amounts(item, sign).values())
                hsn_sources[hsn_key].add(record["id"])

    for record in selected:
        identity, kind, details = record["id"], record["kind"], record["details"]
        if kind not in DOCUMENT_KINDS:
            continue
        if kind in {"CREDIT_NOTE", "DEBIT_NOTE"} and not details["tax_note"]:
            continue
        primary_count.add(identity)
        if dt.date.fromisoformat(record["document_date"]) > end:
            issue(
                "DOCUMENT_AFTER_PERIOD",
                "The document was issued after this statutory return period.",
                identity,
            )
        if kind != "AMENDMENT":
            activity.add(activity_area(kind))
        category = {
            "INVOICE": "OUTWARD_INVOICE",
            "CREDIT_NOTE": "CREDIT_NOTE",
            "DEBIT_NOTE": "DEBIT_NOTE",
            "ADVANCE": "RECEIPT_VOUCHER",
        }.get(kind)
        if category:
            documents_by_category[category].add(record["document_number"])
        original = by_id.get(record["original_record_id"] or "")
        if (
            original
            and kind in {"CREDIT_NOTE", "DEBIT_NOTE"}
            and any(
                original["details"].get(key) != details.get(key)
                for key in (
                    "recipient_type",
                    "recipient_gstin",
                    "place_of_supply",
                    "supply_type",
                    "reverse_charge",
                    "eco_scheme",
                    "operator_gstin",
                )
            )
        ):
            issue(
                "NOTE_ORIGINAL_PROFILE",
                "Linked notes must retain the original recipient and statutory supply profile.",
                identity,
            )
        if kind == "CREDIT_NOTE":
            if not details["annual_return_checked"]:
                issue(
                    "NOTE_ANNUAL_REVIEW",
                    (
                        "Confirm the original supply financial year and any earlier "
                        "annual-return filing before tax reduction."
                    ),
                    identity,
                )
            supply_date = (
                original["document_date"] if original else details.get("original_supply_date")
            )
            if not supply_date:
                issue(
                    "NOTE_SUPPLY_DATE",
                    ("Retain the original supply date for the statutory credit-note " "cutoff."),
                    identity,
                )
            else:
                note_cutoff = correction_cutoff(
                    dt.date.fromisoformat(supply_date),
                    dt.date.fromisoformat(details["annual_return_filed_date"])
                    if details["annual_return_filed_date"]
                    else None,
                )
                filing_cutoffs.append(note_cutoff)
                declaration_date = max(
                    dt.date.fromisoformat(record["return_date"]),
                    dt.date.fromisoformat(record["document_date"]),
                    as_of or start,
                )
                if declaration_date > note_cutoff:
                    issue(
                        "NOTE_CUTOFF",
                        (
                            "The tax reduction is after the statutory or earlier "
                            "annual-return cutoff."
                        ),
                        identity,
                    )
        if kind == "AMENDMENT":
            if not original or original["registration_id"] != record["registration_id"]:
                issue(
                    "ORIGINAL_MISSING",
                    "The amendment's immutable original is missing from this source cut.",
                    identity,
                )
                continue
            ancestor = original
            chain: list[str] = []
            for _ in range(32):
                chain.append(ancestor["id"])
                if ancestor["kind"] != "AMENDMENT":
                    break
                parent = by_id.get(ancestor.get("original_record_id") or "")
                if (
                    not parent
                    or parent["id"] in chain
                    or parent["registration_id"] != record["registration_id"]
                ):
                    issue(
                        "AMENDMENT_HISTORY",
                        "Retain the complete acyclic amendment history for this GSTIN.",
                        identity,
                    )
                    ancestor = {}
                    break
                ancestor = parent
            else:
                issue(
                    "AMENDMENT_HISTORY",
                    "The amendment history exceeds its supported depth.",
                    identity,
                )
                ancestor = {}
            if not ancestor:
                continue
            if amended_children.get(original["id"], set()) - {identity}:
                issue(
                    "AMENDMENT_BASELINE_STALE",
                    (
                        "Use the latest amended evidence as the baseline; earlier "
                        "corrections must not be counted twice."
                    ),
                    identity,
                )
                continue
            original = GstOutwardRecord.model_validate(
                {key: original[key] for key in GstOutwardRecord.model_fields if key in original}
            ).model_dump(mode="json") | {
                "id": original["id"],
                "kind": ancestor["kind"],
                "amendment_chain": chain,
            }
            if original["kind"] not in DOCUMENT_KINDS or original["kind"] == "AMENDMENT":
                issue(
                    "ORIGINAL_INVALID",
                    "Amendments must refer to an original supply, note or advance.",
                    identity,
                )
                continue
            if original["return_date"] >= start.isoformat():
                issue(
                    "ORIGINAL_PERIOD_INVALID",
                    "An amendment must correct a previously furnished period.",
                    identity,
                )
            cutoff = correction_cutoff(
                dt.date.fromisoformat(ancestor["document_date"]),
                dt.date.fromisoformat(details["annual_return_filed_date"])
                if details["annual_return_filed_date"]
                else None,
            )
            filing_cutoffs.append(cutoff)
            if (
                max(
                    dt.date.fromisoformat(record["return_date"]),
                    dt.date.fromisoformat(record["document_date"]),
                    as_of or start,
                )
                > cutoff
            ):
                issue(
                    "AMENDMENT_CUTOFF",
                    "The correction is after the statutory or earlier annual-return cutoff.",
                    identity,
                )
            classification_original = original
            if original["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}:
                if any(
                    original["details"].get(key) != details.get(key)
                    for key in (
                        "recipient_type",
                        "recipient_gstin",
                        "place_of_supply",
                        "supply_type",
                        "reverse_charge",
                        "eco_scheme",
                        "operator_gstin",
                    )
                ):
                    issue(
                        "NOTE_ORIGINAL_PROFILE",
                        (
                            "Amended notes must retain the original recipient and statutory "
                            "supply profile."
                        ),
                        identity,
                    )
                classification_original = (
                    by_id.get(ancestor.get("original_record_id") or "") or original
                )
                supply_date = (
                    classification_original["document_date"]
                    if classification_original is not original
                    else ancestor["details"].get("original_supply_date")
                )
                if original["kind"] == "CREDIT_NOTE" and Decimal(record["taxable"]) > Decimal(
                    original["taxable"]
                ):
                    if not supply_date:
                        issue(
                            "NOTE_SUPPLY_DATE",
                            (
                                "Retain the original supply date before increasing a credit-note "
                                "reduction."
                            ),
                            identity,
                        )
                    else:
                        note_deadline = correction_cutoff(
                            dt.date.fromisoformat(supply_date),
                            dt.date.fromisoformat(details["annual_return_filed_date"])
                            if details["annual_return_filed_date"]
                            else None,
                        )
                        filing_cutoffs.append(note_deadline)
                        if (
                            max(dt.date.fromisoformat(record["return_date"]), as_of or start)
                            > note_deadline
                        ):
                            issue(
                                "NOTE_CUTOFF",
                                "The amended tax reduction exceeds its original supply cutoff.",
                                identity,
                            )
            old_classifications = {
                primary(classification_original, item, registration)
                for item in original["details"]["items"]
            }
            revised_classification = (
                classification_original
                if original["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}
                else record | {"kind": original["kind"]}
            )
            new_classifications = {
                primary(revised_classification, item, registration) for item in details["items"]
            }
            if old_classifications != new_classifications:
                issue(
                    "AMENDMENT_CLASSIFICATION",
                    (
                        "Reconcile corrections that change statutory supply "
                        "classification before review."
                    ),
                    identity,
                )
        effective_kind = original["kind"] if kind == "AMENDMENT" and original else kind
        if kind == "AMENDMENT":
            activity.add(activity_area(effective_kind))
        if details["place_of_supply"] not in STATES | {"96"}:
            issue(
                "PLACE_OF_SUPPLY",
                "The retained place of supply is not a supported GST state/territory code.",
                identity,
            )
        if details["supply_type"].startswith(("EXPORT", "SEZ")):
            if not details["export_reference"]:
                issue(
                    "ZERO_RATE_EVIDENCE",
                    "Exports and SEZ supplies require retained zero-rating evidence.",
                    identity,
                )
            if details["supply_type"].endswith("WOPAY") and any(
                Decimal(record[head]) for head in MONEY[1:]
            ):
                issue(
                    "WITHOUT_PAYMENT_TAX",
                    "Without-payment zero-rated supplies cannot carry charged GST.",
                    identity,
                )
            if Decimal(record["cgst"]) or Decimal(record["sgst"]):
                issue(
                    "ZERO_RATE_TAX_HEAD",
                    "Zero-rated supplies use integrated tax rather than central/state tax.",
                    identity,
                )
        elif details["place_of_supply"] == "96":
            issue(
                "DOMESTIC_EXPORT_POS",
                "Domestic supplies cannot use the foreign-country place-of-supply code.",
                identity,
            )
        if details["supply_type"] == "DEEMED_EXPORT" and details["recipient_type"] != "REGISTERED":
            issue(
                "DEEMED_EXPORT_RECIPIENT",
                "Deemed exports require the registered recipient and statutory evidence.",
                identity,
            )
        if details["eco_scheme"]:
            activity.add("ECO")
        if effective_kind == "ECO_OPERATOR" and (
            details["operator_gstin"] != registration["number"] or details["eco_scheme"] != "9_5"
        ):
            issue(
                "ECO_OPERATOR_SCOPE",
                "Table 15 evidence must identify this GSTIN as the section 9(5) operator.",
                identity,
            )
        if effective_kind in {"ADVANCE", "ADVANCE_ADJUSTMENT"} and any(
            item["goods_service"] == "GOODS" for item in details["items"]
        ):
            issue(
                "GOODS_ADVANCE_RELIEF",
                (
                    "Ordinary goods advances do not create the service-advance GST "
                    "liability shown in Table 11."
                ),
                identity,
            )
        prior = details["prior_filed_channel"]
        if prior:
            activity.add("IFF")
            if prior == "IFF":
                if (
                    start.month == end.month
                    or record["return_date"][:7] == end.isoformat()[:7]
                    or details["recipient_type"] == "UNREGISTERED"
                    or kind not in {"INVOICE", "CREDIT_NOTE", "DEBIT_NOTE"}
                    or details["eco_scheme"] == "9_5"
                ):
                    issue(
                        "IFF_PERIOD",
                        (
                            "IFF evidence is limited to eligible registered supplies in the "
                            "first two months of a QRMP quarter."
                        ),
                        identity,
                    )
                iff_count.add(identity)
                monthly_iff[record["return_date"][:7]] += Decimal(record["taxable"]) * (
                    Decimal(-1) if kind == "CREDIT_NOTE" else Decimal(1)
                )
                filed = dt.date.fromisoformat(details["prior_filing_date"])
                supplied = dt.date.fromisoformat(record["return_date"])
                following_month = dt.date(
                    supplied.year + (supplied.month == 12), supplied.month % 12 + 1, 1
                )
                if filed < following_month or (as_of and filed > as_of):
                    issue(
                        "IFF_FILING_DATE",
                        "Prior IFF proof must follow its supply period and cannot be future dated.",
                        identity,
                    )
            else:
                issue(
                    "GSTR1A_SEPARATE",
                    (
                        "GSTR-1A evidence belongs in its separate monthly correction/3B "
                        "bridge, not this GSTR-1 invoice payload."
                    ),
                    identity,
                )
        amended_tables: set[str] = set()
        for item in details["items"]:
            if effective_kind not in {"ADVANCE", "ADVANCE_ADJUSTMENT"}:
                if (
                    not item["hsn"]
                    or len(item["hsn"]) not in {4, 6, 8}
                    or (digits and len(item["hsn"]) < digits)
                ):
                    issue(
                        "HSN_MISSING",
                        f"Retain the applicable {digits or 'turnover-based'} digit HSN/SAC "
                        "for each supply line.",
                        identity,
                    )
                if item["uqc"] not in UQC or (
                    item["goods_service"] == "GOODS"
                    and (Decimal(item["quantity"]) <= 0 or item["uqc"] in {"NA", "N.A."})
                ):
                    issue(
                        "UQC_QUANTITY",
                        (
                            "Goods require actual positive quantities and a supported UQC; "
                            "services may use NA."
                        ),
                        identity,
                    )
            if (
                item["treatment"] == "TAXABLE"
                and details["supply_type"] == "DOMESTIC"
                and not details["eco_scheme"]
            ):
                interstate = details["place_of_supply"] != registration["number"][:2]
                if (interstate and (Decimal(item["cgst"]) or Decimal(item["sgst"]))) or (
                    not interstate and Decimal(item["igst"])
                ):
                    issue(
                        "TAX_JURISDICTION",
                        "The retained tax heads disagree with the domestic place of supply.",
                        identity,
                    )
            reference_record = original or record
            table = primary(reference_record, item, registration)
            sign = Decimal(-1) if kind in {"CREDIT_NOTE", "ADVANCE_ADJUSTMENT"} else Decimal(1)
            if kind in {"CREDIT_NOTE", "DEBIT_NOTE"}:
                if (
                    details["recipient_type"] == "UNREGISTERED"
                    and details["supply_type"] == "DOMESTIC"
                    and not original
                ):
                    issue(
                        "NOTE_ORIGINAL_MISSING",
                        (
                            "Link the original unregistered invoice to distinguish B2CS net "
                            "notes from separately reportable B2CL notes."
                        ),
                        identity,
                    )
                if table not in {"7", "8", "14_9_5"}:
                    table = "9B_UNREG" if details["recipient_type"] == "UNREGISTERED" else "9B_REG"
            if kind == "AMENDMENT" and original:
                old_table = primary(
                    classification_original, original["details"]["items"][0], registration
                )
                table = {
                    "4A": "9A_B2B",
                    "4B": "9A_B2B",
                    "6B": "9A_B2B",
                    "6C": "9A_B2B",
                    "5": "9A_B2CL",
                    "6A": "9A_EXP",
                    "7": "10",
                    "8": "10",
                    "11A": "11A_AMEND",
                    "11B": "11B_AMEND",
                    "14_9_5": "14A_9_5",
                }.get(old_table, old_table.replace("15_", "15A_"))
                if original["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"} and old_table not in {
                    "7",
                    "8",
                }:
                    table = (
                        "9C_UNREG"
                        if original["details"]["recipient_type"] == "UNREGISTERED"
                        else "9C_REG"
                    )
                sign = (
                    Decimal(-1)
                    if original["kind"] in {"CREDIT_NOTE", "ADVANCE_ADJUSTMENT"}
                    else Decimal(1)
                )
            if not prior:
                emit(
                    record, item, table, sign, liability=table not in {"14_9_5"}, original=original
                )
                if kind == "AMENDMENT":
                    amended_tables.add(table)
                if details["eco_scheme"] == "TCS":
                    emit(
                        record,
                        item,
                        "14A_TCS" if kind == "AMENDMENT" else "14_TCS",
                        sign,
                        liability=False,
                    )
        sign = Decimal(-1) if kind in {"CREDIT_NOTE", "ADVANCE_ADJUSTMENT"} else Decimal(1)
        if kind == "AMENDMENT" and original:
            sign = (
                Decimal(-1)
                if original["kind"] in {"CREDIT_NOTE", "ADVANCE_ADJUSTMENT"}
                else Decimal(1)
            )
            account(original, -sign)
            account(record | {"kind": original["kind"]}, sign)
            if len(amended_tables) == 1:
                amendment_table = next(iter(amended_tables))
                for head in MONEY:
                    totals[amendment_table][head] -= Decimal(original[head]) * (
                        -sign if amendment_table.startswith("11B") else sign
                    )
                if details["eco_scheme"] == "TCS":
                    for head in MONEY:
                        totals["14A_TCS"][head] -= Decimal(original[head]) * sign
            elif len(amended_tables) > 1:
                issue(
                    "AMENDMENT_TABLE_REVIEW",
                    (
                        "Reconcile an amendment spanning multiple statutory "
                        "classifications before review."
                    ),
                    identity,
                )
        else:
            account(record, sign)
    for month, taxable in monthly_iff.items():
        if taxable > Decimal("5000000"):
            issue(
                "IFF_VALUE_LIMIT",
                f"{month} IFF supplies exceed the monthly taxable value limit of fifty lakh.",
            )
    if profile and profile["rule_14a"]:
        for month, monthly_tax in monthly_b2b.items():
            if monthly_tax > Decimal("250000"):
                issue(
                    "RULE14A_LIMIT",
                    f"{month} registered outward tax exceeds the explicit "
                    "Rule 14A monthly limit of ₹2,50,000.",
                )
    invoice_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for source_row in rows:
        if source_row["table"] not in AGGREGATE_TABLES:
            invoice_groups[
                (source_row["table"], source_row["record_id"], source_row["rate"])
            ].append(source_row)
    for group, lines in invoice_groups.items():
        if len(lines) < 2:
            continue
        table, identity, rate = group
        grouped_invoice = lines[0] | {
            "id": f"invoice:{table}:{identity}:{rate}",
            "source_count": len(lines),
            "grouped_lines": True,
            "source_line_ids": [line["source_line_id"] for line in lines],
            "hsn": "",
            "uqc": "",
            "quantity": "",
        }
        for head in MONEY:
            signed_total = sum((Decimal(line["signed_amounts"][head]) for line in lines), ZERO)
            grouped_invoice[head] = money(
                abs(signed_total) if table.startswith(("9B", "9C")) else signed_total
            )
            grouped_invoice["signed_amounts"] = {
                **grouped_invoice["signed_amounts"],
                head: format(signed_total, ".4f"),
            }
        for line in lines:
            line["row_role"] = "LINE"
        rows.append(grouped_invoice)
    aggregates: dict[tuple[str, ...], dict[str, Any]] = {}
    for source_row in rows:
        table = source_row["table"]
        if table not in AGGREGATE_TABLES:
            continue
        keys = (
            ("recipient_type", "supply_location")
            if table == "8"
            else ("operator_gstin",)
            if table.startswith("14")
            else ("place_of_supply", "rate", "eco_scheme", "operator_gstin")
        )
        group = (table, *(str(source_row.get(key, "")) for key in keys))
        if group not in aggregates:
            aggregates[group] = {
                "id": "aggregate:" + ":".join(group),
                "row_role": "STATUTORY",
                "table": table,
                "table_label": TABLES[table],
                "record_id": "",
                "currency": "INR",
                "liability_included": False,
                **{key: source_row.get(key, "") for key in keys},
                "source_records": [],
                "source_count": 0,
                "reference": "Grouped from retained source contributions",
                **{head: ZERO for head in MONEY},
                "nil_rated": ZERO,
                "exempt": ZERO,
                "non_gst": ZERO,
            }
        grouped = aggregates[group]
        grouped["source_records"].append(source_row["record_id"])
        grouped["source_count"] += 1
        for head in MONEY:
            # Table 11B declares positive adjustments; its 3B bridge subtracts them.
            contribution = Decimal(source_row["signed_amounts"][head])
            grouped[head] += -contribution if table == "11B" else contribution
        if table == "8":
            field = {"NIL_RATED": "nil_rated", "EXEMPT": "exempt", "NON_GST": "non_gst"}[
                source_row["treatment"]
            ]
            grouped[field] += Decimal(source_row["signed_amounts"]["taxable"])
    for grouped in aggregates.values():
        for head in (*MONEY, "nil_rated", "exempt", "non_gst"):
            grouped[head] = money(grouped[head])
        grouped["source_records"] = sorted(set(grouped["source_records"]))
        rows.append(grouped)
    for hsn_group, values in sorted(hsn.items()):
        table, code, rate, uqc = hsn_group
        for head in MONEY:
            totals[table][head] += values[head]
        rows.append(
            {
                "id": f"{table}:{code}:{rate}:{uqc}",
                "table": table,
                "table_label": TABLES[table],
                "row_role": "STATUTORY",
                "hsn": code,
                "rate": rate,
                "uqc": uqc,
                "quantity": format(values["quantity"], ".4f"),
                "invoice_value": money(values["invoice_value"]),
                "currency": "INR",
                **{head: money(values[head]) for head in MONEY},
                "liability_included": False,
                "source_count": len(hsn_sources[hsn_group]),
                "record_id": "",
                "reference": "Derived from immutable outward line details",
            }
        )
    for record in selected:
        if record["kind"] != "DOCUMENTS":
            continue
        details = record["details"]
        activity.add("DOCUMENTS")
        category = details["document_category"]
        if category not in DOCUMENT_CATEGORIES:
            issue("DOCUMENT_CATEGORY", "Use an official Table 13 document category.", record["id"])
        count = details["total_count"] - details["cancelled_count"]
        series_counts[category] += count
        rows.append(
            {
                "id": record["id"] + ":13",
                "record_id": record["id"],
                "table": "13",
                "table_label": TABLES["13"],
                "row_role": "STATUTORY",
                "kind": category,
                "serial_from": details["serial_from"],
                "serial_to": details["serial_to"],
                "total_count": details["total_count"],
                "cancelled_count": details["cancelled_count"],
                "net_count": count,
                "reference": record["reference"],
                "evidence_hash": record["evidence_hash"],
                "explanation": record["explanation"],
                "currency": "INR",
                "liability_included": False,
                **{head: None for head in MONEY},
            }
        )
    for category, numbers in documents_by_category.items():
        if series_counts[category] != len(numbers):
            issue(
                "DOCUMENT_RECONCILIATION",
                f"{category}: Table 13 net issued count {series_counts[category]} "
                f"differs from {len(numbers)} retained documents.",
            )
        retained_series = [row for row in rows if row["table"] == "13" and row["kind"] == category]

        def in_series(number: str, series: dict[str, Any]) -> bool:
            first, last = series["serial_from"], series["serial_to"]
            parts = [re.fullmatch(r"(.*?)(\d+)", value) for value in (number, first, last)]
            if all(parts) and len({part[1] for part in parts if part}) == 1:
                return int(parts[1][2]) <= int(parts[0][2]) <= int(parts[2][2])  # type: ignore[index]
            return bool(first <= number <= last)

        for number in numbers:
            if sum(in_series(number, series) for series in retained_series) != 1:
                issue(
                    "DOCUMENT_SERIES_MEMBERSHIP",
                    (
                        "Every issued document must belong to exactly one retained Table "
                        "13 series."
                    ),
                    number,
                )
    for identity in (unresolved_sources or [])[:200]:
        issue(
            "UNALLOCATED_OUTWARD_SOURCE",
            "A committed outward tax source lacks its detailed GSTR-1 evidence allocation.",
            identity,
        )
    portal = [record for record in selected if record["kind"] == "PORTAL"]
    if portal:
        activity.add("PORTAL")
    for area in sorted(AREAS):
        area_record = coverage.get(area)
        if area_record is None:
            issue(
                "COVERAGE_" + area,
                f"Record explicit completeness or non-applicability evidence for {area.lower()}.",
            )
            continue
        details = area_record["details"]
        if details["coverage_status"] == "NOT_APPLICABLE" and area in activity:
            issue(
                "COVERAGE_CONTRADICTION_" + area,
                f"{area.lower()} is marked not applicable despite retained activity.",
            )
        if sequence is not None and details["covered_sequence"] != sequence:
            issue(
                "COVERAGE_STALE_" + area,
                f"Refresh the {area.lower()} completeness review against this source cut.",
            )
    reconciliation: list[dict[str, str]] = []
    if portal:
        activity.add("PORTAL")
        actual = {
            head: sum(
                (bridge[key][head] for key in ("3.1a", "3.1b", "3.1c", "3.1e", "3.1.1i")), ZERO
            )
            for head in MONEY
        }
        for head in MONEY:
            external = sum((Decimal(record[head]) for record in portal), ZERO)
            difference = actual[head] - external
            reconciliation.append(
                {
                    "source": "PORTAL",
                    "category": "OUTWARD_TOTAL",
                    "head": head.upper(),
                    "return_amount": money(actual[head]),
                    "source_amount": money(external),
                    "difference": money(difference),
                }
            )
            if money(difference) != "0.00":
                issue(
                    "PORTAL_DIFFERENCE_" + head,
                    f"The retained portal {head.upper()} total differs "
                    "from the outward working papers.",
                )
    if comparison:
        for key in BRIDGE:
            if key == "OUTWARD_RCM":
                continue
            for head in MONEY:
                external_value = comparison.get("form", {}).get(key, {}).get(head)
                if external_value is None:
                    continue
                external = Decimal(external_value)
                difference = bridge[key][head] - external
                reconciliation.append(
                    {
                        "source": "GSTR3B",
                        "category": key,
                        "head": head.upper(),
                        "return_amount": money(bridge[key][head]),
                        "source_amount": money(external),
                        "difference": money(difference),
                    }
                )
                if money(difference) != "0.00":
                    issue(
                        "GSTR3B_DIFFERENCE_" + key + head,
                        f"GSTR-3B {key} {head.upper()} differs; retain and resolve the reason.",
                    )
    year = start.year if start.month >= 4 else start.year - 1
    order = {key: index for index, key in enumerate(TABLES)}
    rows.sort(
        key=lambda row: (
            order[row["table"]],
            row.get("return_date", ""),
            row.get("document_number", ""),
            row["id"],
        )
    )
    return rows, {
        "calculation_version": CALCULATION_VERSION,
        "rule_version": RULE_VERSION,
        "registration": registration,
        "currency": "INR",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "financial_year": f"{year}-{str(year + 1)[-2:]}",
        "status": "NEEDS_ATTENTION" if issues else "DRAFT",
        "nil": not primary_count and not any(series_counts.values()) and not issues,
        "form": {
            key: {head: money(value) for head, value in values.items()}
            for key, values in totals.items()
        },
        "row_order": list(TABLES),
        "labels": TABLES,
        "table_counts": {
            key: sum(
                row["table"] == key
                and row.get("row_role") != "LINE"
                and (key not in AGGREGATE_TABLES or row.get("row_role") == "STATUTORY")
                for row in rows
            )
            for key in TABLES
        },
        "bridge": {
            key: {head: money(value) for head, value in values.items()}
            for key, values in bridge.items()
        },
        "bridge_labels": BRIDGE,
        "reconciliation": reconciliation,
        "issues": issues,
        "coverage": {
            area: record["details"]["coverage_status"] for area, record in coverage.items()
        },
        "source_count": len(selected),
        "document_count": len(primary_count),
        "iff_count": len(iff_count),
        "hsn_min_digits": digits,
        "filing_cutoff": min(filing_cutoffs).isoformat() if filing_cutoffs else None,
        "coverage_details": {
            area: {
                "record_id": record["id"],
                "reference": record["reference"],
                "evidence_hash": record["evidence_hash"],
                "status": record["details"]["coverage_status"],
                "covered_sequence": record["details"]["covered_sequence"],
            }
            for area, record in coverage.items()
        },
        "portal_json_ready": False,
        "portal_json_reason": (
            "Official upload schema and portal import validation have not "
            "been verified. PDF, Excel and CSV are review working papers."
        ),
    }

"""Check retained invoice grains and their native GL links without recalculating tax."""

from collections import defaultdict
from fractions import Fraction
from typing import Any

from billing_platform.errors import ConflictError

Live = dict[tuple[str, str], dict[str, Any]]


def reconcile_invoices(live: Live) -> None:
    def require(entity: str, identity: object) -> dict[str, Any]:
        row = live.get((entity, str(identity)))
        if row is None:
            raise ConflictError("required invoice source reference is missing")
        return row

    grouped: dict[str, dict[str, list[tuple[str, dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    journal_lines: dict[str, set[str]] = defaultdict(set)
    open_items_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (entity, identity), row in live.items():
        assert row is not None
        if entity == "journal_line":
            journal_lines[row["journal_id"]].add(identity)
        if entity == "open_item":
            open_items_by_line[row["journal_line_id"]].append(row)
        if entity.startswith("invoice_") and entity != "invoice_record":
            require("invoice_record", row["invoice_id"])
            grouped[row["invoice_id"]][entity].append((identity, row))
            if entity == "invoice_supply_fact":
                require("account", row["account_id"])
            if entity == "invoice_component_fact" and row["account_id"]:
                require("account", row["account_id"])
            references = {
                "invoice_allocation_fact": {
                    "component_id": "invoice_component_fact",
                    "supply_id": "invoice_supply_fact",
                },
                "invoice_tax_component": {"supply_id": "invoice_supply_fact"},
                "invoice_posting_line": {"tax_component_id": "invoice_tax_component"},
                "invoice_credit_action": {"component_id": "invoice_tax_component"},
                "invoice_credit_event": {"action_id": "invoice_credit_action"},
            }
            for key, target in references.get(entity, {}).items():
                if row[key] and require(target, row[key])["invoice_id"] != row["invoice_id"]:
                    raise ConflictError("invoice relation crosses original document scope")
            if entity == "invoice_credit_action":
                if row["journal_id"]:
                    require("journal", row["journal_id"])
                if row["offset_account_id"]:
                    require("account", row["offset_account_id"])
                if row["cash_deposit_line_id"]:
                    require("journal_line", row["cash_deposit_line_id"])
            if entity == "invoice_credit_event":
                action = require("invoice_credit_action", row["action_id"])
                if (
                    action["journal_id"]
                    and require("journal", action["journal_id"])["status"] != "POSTED"
                ):
                    raise ConflictError("credit event has no committed native journal")
                if not action["journal_id"] and action["kind"] != "VERIFY":
                    raise ConflictError("financial credit event is missing its journal")

    for (entity, identity), row in live.items():
        if entity != "invoice_record":
            continue
        assert row is not None
        intent = require("voucher_money_intent", row["intent_id"])
        journal = require("journal", intent["journal_id"])
        require("account", row["party_account_id"])
        original_id = row.get("source_invoice_id")
        if row["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}:
            original = require("invoice_record", original_id)
            expected_kind = "SALES" if row["kind"] == "CREDIT_NOTE" else "PURCHASE"
            if (
                original["kind"] != expected_kind
                or original["party_account_id"] != row["party_account_id"]
                or original["currency"] != row["currency"]
                or original["posting_date"] > row["posting_date"]
                or Fraction(row["tax_total"]) != 0
                or Fraction(original["tax_total"]) != 0
                or Fraction(row["rounding"]) != 0
                or Fraction(original["rounding"]) != 0
                or grouped[str(original_id)]["invoice_component_fact"]
                or grouped[str(original_id)]["invoice_tax_component"]
                or grouped[identity]["invoice_component_fact"]
                or grouped[identity]["invoice_tax_component"]
            ):
                raise ConflictError("financial note differs from its original invoice")
            source_intent = require("voucher_money_intent", original["intent_id"])
            if (
                source_intent["status"] != "COMMITTED"
                or require("journal", source_intent["journal_id"])["status"] != "POSTED"
            ):
                raise ConflictError("financial note original invoice is not committed")
        elif original_id:
            raise ConflictError("ordinary invoice cannot claim an original source")
        if (row["kind"], row["posting_date"], row["currency"]) != (
            intent["kind"],
            journal["posting_date"],
            journal["base_currency"],
        ):
            raise ConflictError("invoice source kind, date or currency differs from its GL")
        if (intent["status"], journal["status"]) not in {
            ("COMMITTED", "POSTED"),
            ("CANCELLED", "VOID"),
            ("PREPARED", "PREPARED"),
        }:
            raise ConflictError("invoice intent and journal states do not reconcile")
        children = grouped[identity]
        supplies = children["invoice_supply_fact"]
        taxes = children["invoice_tax_component"]
        allocations = children["invoice_allocation_fact"]
        links = children["invoice_posting_line"]
        if (
            not supplies
            or {r["journal_line_id"] for _, r in links} != journal_lines[intent["journal_id"]]
        ):
            raise ConflictError("invoice supply or native GL linkage is incomplete")
        bill_links = [link for _, link in links if link["tracking"] == "NEW_REF"]
        bill_line_ids = [link["journal_line_id"] for link in bill_links]
        bills = [require("journal_line", line_id) for line_id in bill_line_ids]
        if (
            len(bills) != 1
            or bills[0]["account_id"] != row["party_account_id"]
            or bills[0]["currency"] != row["currency"]
            or Fraction(bills[0]["amount"]) != Fraction(row["payable"])
            or bills[0]["side"] != ("DEBIT" if row["kind"] in {"SALES", "DEBIT_NOTE"} else "CREDIT")
            or bill_links[0]["bill_reference"] != row["bill_reference"]
            or bill_links[0]["due_date"] != row["due_date"]
        ):
            raise ConflictError("invoice party bill differs from its native GL")
        bill_items = open_items_by_line[bill_line_ids[0]]
        if intent["status"] == "COMMITTED":
            if (
                len(bill_items) != 1
                or bill_items[0]["account_id"] != row["party_account_id"]
                or bill_items[0]["currency"] != row["currency"]
                or bill_items[0]["reference"] != row["bill_reference"]
                or bill_items[0]["due_date"] != row["due_date"]
                or Fraction(bill_items[0]["amount"]) != Fraction(row["payable"])
                or bill_items[0]["direction"]
                != ("DEBT" if row["kind"] in {"SALES", "PURCHASE"} else "CREDIT")
            ):
                raise ConflictError("invoice party bill has no matching native open item")
        elif bill_items:
            raise ConflictError("uncommitted invoice cannot have a native open item")
        for _, link in links:
            native = require("journal_line", link["journal_line_id"])
            if native["journal_id"] != intent["journal_id"]:
                raise ConflictError("invoice GL link crosses journals")
            if bool(link["tax_component_id"]) != bool(link["tax_purpose"]):
                raise ConflictError("invoice tax GL lineage is incomplete")
            if link["tax_component_id"]:
                tax = require("invoice_tax_component", link["tax_component_id"])
                if Fraction(native["amount"]) != Fraction(tax["amount"]):
                    raise ConflictError("tax component differs from its native GL amount")
        tax_links: dict[str, list[str]] = defaultdict(list)
        for _, link in links:
            if link["tax_component_id"]:
                tax_links[link["tax_component_id"]].append(link["tax_purpose"])
        supplies_by_id = dict(supplies)
        for tax_id, tax in taxes:
            amount = Fraction(tax["amount"])
            expected = set()
            if amount:
                if row["kind"] == "SALES":
                    expected.add("OUTPUT_" + tax["code"])
                elif row["kind"] == "PURCHASE":
                    supply = supplies_by_id[tax["supply_id"]]
                    expected.add(
                        ("PENDING_" + tax["code"])
                        if supply["credit_state"] == "PENDING_EVIDENCE"
                        else "NONRECOVERABLE"
                    )
                    if not tax["supplier_charged"]:
                        expected.add("RCM_" + tax["code"])
                else:
                    raise ConflictError("tax note reconciliation requires original source claims")
            observed = tax_links.get(tax_id, [])
            if len(observed) != len(expected) or set(observed) != expected:
                raise ConflictError("invoice tax GL purposes differ from their source components")
        for field, value in (
            ("commercial_total", sum((Fraction(r["commercial"]) for _, r in supplies), Fraction())),
            ("tax_total", sum((Fraction(r["amount"]) for _, r in taxes), Fraction())),
            (
                "charged_tax_total",
                sum((Fraction(r["amount"]) for _, r in taxes if r["supplier_charged"]), Fraction()),
            ),
            (
                "payable",
                Fraction(row["commercial_total"])
                + Fraction(row["charged_tax_total"])
                + Fraction(row["rounding"]),
            ),
        ):
            if Fraction(row[field]) != value:
                raise ConflictError("invoice totals do not reconcile to their component grains")
        for supply_id, supply in supplies:
            for field, purpose in (("commercial", "COMMERCIAL"), ("taxable", "TAX_BASE")):
                allocated = sum(
                    (
                        Fraction(a["amount"])
                        for _, a in allocations
                        if a["supply_id"] == supply_id and a["purpose"] == purpose
                    ),
                    Fraction(),
                )
                if Fraction(supply[field]) != Fraction(supply["entered"]) + allocated:
                    raise ConflictError(
                        "supply allocation does not reconcile to its declared purpose"
                    )
        for component_id, component in children["invoice_component_fact"]:
            purposes = {a["purpose"] for _, a in allocations if a["component_id"] == component_id}
            required = set()
            if component["commercial_treatment"] == "COUNTERPARTY":
                required.add("COMMERCIAL")
            if component["tax_treatment"] == "ASSESSABLE":
                required.add("TAX_BASE")
            if not required <= purposes:
                raise ConflictError("component allocation purpose is missing")
            for purpose in purposes:
                amount = sum(
                    (
                        Fraction(a["amount"])
                        for _, a in allocations
                        if a["component_id"] == component_id and a["purpose"] == purpose
                    ),
                    Fraction(),
                )
                if amount != Fraction(component["amount"]):
                    raise ConflictError(
                        "component distribution does not conserve its source amount"
                    )

    for (entity, identity), source in live.items():
        if entity != "invoice_record" or source["kind"] not in {"SALES", "PURCHASE"}:
            continue
        assert source is not None
        original = {row["line_key"]: row for _, row in grouped[identity]["invoice_supply_fact"]}
        claimed: dict[str, Fraction] = defaultdict(Fraction)
        for (other_entity, note_id), note in live.items():
            if other_entity != "invoice_record" or note.get("source_invoice_id") != identity:
                continue
            assert note is not None
            note_intent = require("voucher_money_intent", note["intent_id"])
            if note_intent["status"] == "CANCELLED":
                continue
            for _, line in grouped[note_id]["invoice_supply_fact"]:
                key = line["line_key"]
                if (
                    key not in original
                    or Fraction(line["commercial"]) <= 0
                    or line["tax_profile"] != "UNTAXED_ACCOUNT"
                    or original[key]["tax_profile"] != "UNTAXED_ACCOUNT"
                    or line["supply_kind"] not in {"ACCOUNT", "SERVICE"}
                    or line["supply_kind"] != original[key]["supply_kind"]
                    or line["account_id"] != original[key]["account_id"]
                ):
                    raise ConflictError("financial note has an unknown original supply")
                claimed[key] += Fraction(line["commercial"])
        if any(amount > Fraction(original[key]["commercial"]) for key, amount in claimed.items()):
            raise ConflictError("financial notes exceed their original supply entitlement")

"""Invoice registers use distinct immutable source grains and dated settlement histories."""

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from billing_platform.errors import ConflictError

from reports.domain.reconcile import fixed, money
from reports.schemas.requests import RunRequest

if TYPE_CHECKING:
    from reports.domain.statements import Facts

CODES = (
    "SALES_REGISTER",
    "PURCHASE_REGISTER",
    "INVOICE_COMPONENT_REGISTER",
    "INVOICE_TAX_REGISTER",
    "INVOICE_CREDIT_REGISTER",
    "INVOICE_SETTLEMENT_REGISTER",
    "INVOICE_GL_BRIDGE",
    "TAX_GL_BRIDGE",
)


def in_range(value: str | None, query: RunRequest) -> bool:
    assert query.date_from and query.date_to
    return bool(value and query.date_from.isoformat() <= value <= query.date_to.isoformat())


def register(data: "Facts", query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_to
    as_of = query.date_to.isoformat()
    invoices = {}
    journals = {}
    lineage = data.lineage()
    for identity, row in data.rows["invoice_record"].items():
        intent = data.rows["voucher_money_intent"][row["intent_id"]]
        journal = data.journals[intent["journal_id"]]
        account = data.accounts[row["party_account_id"]]
        if (
            journal["status"] != "POSTED"
            or intent["status"] != "COMMITTED"
            or (query.invoice_id and identity != str(query.invoice_id))
            or not data.selected(account, row["party_account_id"], query)
            or (query.currency and row["currency"] != query.currency)
        ):
            continue
        invoices[identity] = row
        journals[identity] = intent["journal_id"]
    reversals = {
        str(journal["reversal_of_id"]): (identity, journal)
        for identity, journal in data.journals.items()
        if journal.get("reversal_of_id") and journal["status"] == "POSTED"
    }

    def identity_fields(invoice_id: str) -> dict[str, Any]:
        row = invoices[invoice_id]
        journal_id = journals[invoice_id]
        return {
            **lineage.get(journal_id, {}),
            "invoice_id": invoice_id,
            "journal_id": journal_id,
            "journal_posting_date": data.journals[journal_id]["posting_date"],
            "invoice_kind": row["kind"],
            "source_invoice_id": row.get("source_invoice_id"),
            "currency": row["currency"],
            "bill_reference": row["bill_reference"],
            "party_account_id": row["party_account_id"],
            "account_code": data.accounts[row["party_account_id"]]["code"],
            "account_name": data.accounts[row["party_account_id"]]["name"],
            "party_id": data.accounts[row["party_account_id"]]["party_id"],
            "role": data.accounts[row["party_account_id"]]["party_role"],
            "posting_date": row["posting_date"],
            "configuration_hash": row["configuration_hash"],
            "calculation_hash": row["calculation_hash"],
        }

    if query.code in {"SALES_REGISTER", "PURCHASE_REGISTER"}:
        kinds = (
            {"SALES", "CREDIT_NOTE"}
            if query.code == "SALES_REGISTER"
            else {"PURCHASE", "DEBIT_NOTE"}
        )
        invoice_rows = [
            identity_fields(key)
            | {
                "row_kind": "INVOICE",
                "document_date": row["document_date"],
                "posting_date": row["posting_date"],
                "due_date": row["due_date"],
                "commercial_total": row["commercial_total"],
                "tax_total": row["tax_total"],
                "charged_tax_total": row["charged_tax_total"],
                "rounding": row["rounding"],
                "payable": row["payable"],
                "supplier_difference": row["supplier_difference"],
                "direction": "REDUCTION"
                if row["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}
                else "ORIGINAL",
            }
            for key, row in sorted(invoices.items())
            if row["kind"] in kinds and in_range(row[query.date_basis.lower() + "_date"], query)
        ]
        for key, row in sorted(invoices.items()):
            if row["kind"] not in {"SALES", "PURCHASE"} or row["kind"] not in kinds:
                continue
            reversed_fact = reversals.get(journals[key])
            if reversed_fact is None:
                continue
            reversal_id, reversal = reversed_fact
            date = reversal["posting_date"]
            if not in_range(date, query):
                continue
            invoice_rows.append(identity_fields(key) | {
                **lineage.get(reversal_id, {}),
                "row_kind": "INVOICE",
                "effect": "REVERSAL",
                "source_invoice_id": key,
                "journal_id": reversal_id,
                "journal_posting_date": date,
                "document_date": date,
                "posting_date": date,
                "original_document_date": row["document_date"],
                "due_date": row["due_date"],
                "commercial_total": row["commercial_total"],
                "tax_total": row["tax_total"],
                "charged_tax_total": row["charged_tax_total"],
                "rounding": row["rounding"],
                "payable": row["payable"],
                "supplier_difference": row["supplier_difference"],
                "direction": "REDUCTION",
            })
        return sorted(invoice_rows, key=lambda item: (item["posting_date"], item["journal_id"]))

    rows: list[dict[str, Any]] = []
    if query.code == "INVOICE_COMPONENT_REGISTER":
        for entity, row_kind in (
            ("invoice_component_fact", "COMPONENT"),
            ("invoice_allocation_fact", "ALLOCATION"),
        ):
            for key, row in sorted(data.rows[entity].items()):
                if row["invoice_id"] not in invoices or not in_range(
                    invoices[row["invoice_id"]]["posting_date"], query
                ):
                    continue
                amount_field = (
                    "component_amount" if row_kind == "COMPONENT" else "allocation_amount"
                )
                rows.append(
                    identity_fields(row["invoice_id"])
                    | {
                        "row_kind": row_kind,
                        "source_id": key,
                        **{k: v for k, v in row.items() if k not in {"amount", "invoice_id"}},
                        amount_field: row["amount"],
                    }
                )
        return rows

    taxes = {}
    for key, row in sorted(data.rows["invoice_tax_component"].items()):
        if row["invoice_id"] not in invoices:
            continue
        supply = data.rows["invoice_supply_fact"][row["supply_id"]]
        if query.company_registration_id and supply["company_registration_id"] != str(
            query.company_registration_id
        ):
            continue
        taxes[key] = row
        if query.code == "INVOICE_TAX_REGISTER":
            invoice = invoices[row["invoice_id"]]
            selected_date = (
                supply["tax_point_date"]
                if query.date_basis == "TAX_POINT"
                else invoice[query.date_basis.lower() + "_date"]
            )
            detail = identity_fields(row["invoice_id"]) | {
                    "row_kind": "TAX_COMPONENT",
                    "component_id": key,
                    "supply_id": row["supply_id"],
                    "tax_code": row["code"],
                    "taxable_value": supply["taxable"],
                    "direction": "REDUCTION"
                    if invoice["kind"] in {"CREDIT_NOTE", "DEBIT_NOTE"}
                    else "ORIGINAL",
                    "component_taxable_basis": row["basis"],
                    "tax_amount": row["amount"],
                    "percentage": row["percentage"],
                    "supplier_charged": row["supplier_charged"],
                    "posting_date": invoice["posting_date"],
                    **{
                        k: supply[k]
                        for k in (
                            "tax_point_date",
                            "tax_point_basis",
                            "company_registration_id",
                            "party_registration_id",
                            "place_of_supply",
                            "classification_code",
                            "treatment",
                            "reverse_charge",
                            "credit_state",
                        )
                    },
                }
            if in_range(selected_date, query):
                rows.append(detail)
            reversed_fact = reversals.get(journals[row["invoice_id"]])
            if reversed_fact and invoice["kind"] in {"SALES", "PURCHASE"}:
                reversal_id, reversal = reversed_fact
                date = reversal["posting_date"]
                if in_range(date, query):
                    rows.append(detail | {
                        **lineage.get(reversal_id, {}),
                        "journal_id": reversal_id,
                        "journal_posting_date": date,
                        "document_date": date,
                        "posting_date": date,
                        "tax_point_date": date,
                        "tax_point_basis": "REVERSAL",
                        "direction": "REDUCTION",
                        "effect": "REVERSAL",
                    })
    if query.code == "INVOICE_TAX_REGISTER":
        from reports.domain.tax_summaries import selected

        return [row for row in rows if selected(row, query)]

    actions = [
        (event_id, data.rows["invoice_credit_action"][event["action_id"]])
        for event_id, event in sorted(data.rows["invoice_credit_event"].items())
        if data.rows["invoice_credit_action"][event["action_id"]]["component_id"] in taxes
    ]
    if query.code == "INVOICE_CREDIT_REGISTER":
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for event_id, action in actions:
            if action["posting_date"] > as_of or action["event_date"] > as_of:
                continue
            totals[action["component_id"]][action["kind"]] += money(action["amount"])
            if in_range(action["posting_date"], query):
                rows.append(
                    identity_fields(action["invoice_id"])
                    | {
                        "row_kind": "CREDIT_EVENT",
                        "event_id": event_id,
                        "component_id": action["component_id"],
                        "tax_code": taxes[action["component_id"]]["code"],
                        "action": action["kind"],
                        "event_date": action["event_date"],
                        "posting_date": action["posting_date"],
                        "event_amount": action["amount"],
                        "action_journal_id": action["journal_id"],
                        "journal_id": action["journal_id"] or journals[action["invoice_id"]],
                        "journal_posting_date": action["posting_date"]
                        if action["journal_id"]
                        else data.journals[journals[action["invoice_id"]]]["posting_date"],
                        "reference": action["reference"],
                        "evidence_sha256": action["evidence_sha256"],
                    }
                )
        for key, tax in taxes.items():
            invoice = invoices[tax["invoice_id"]]
            if invoice["kind"] != "PURCHASE" or invoice["posting_date"] > as_of:
                continue
            reversed_fact = reversals.get(journals[tax["invoice_id"]])
            if reversed_fact and reversed_fact[1]["posting_date"] <= as_of:
                continue
            supply = data.rows["invoice_supply_fact"][tax["supply_id"]]
            amounts = totals[key]
            recorded = money(tax["amount"])
            blocked = amounts["BLOCK"] + (
                recorded if supply["credit_state"] != "PENDING_EVIDENCE" else Decimal(0)
            )
            claimed = amounts["CLAIM"] - amounts["REVERSE_PAYMENT"] + amounts["RECLAIM_PAYMENT"]
            suspended = amounts["REVERSE_PAYMENT"] - amounts["RECLAIM_PAYMENT"]
            position = {
                "recorded_tax": recorded,
                "pending": recorded - blocked - amounts["VERIFY"],
                "eligible_unclaimed": amounts["VERIFY"] - claimed - suspended,
                "claimed": claimed,
                "suspended": suspended,
                "blocked": blocked,
                "rcm_discharged": amounts["RCM_DISCHARGE"],
            }
            if any(amount < 0 for amount in position.values()):
                raise ConflictError("credit history does not reconcile to the recorded source")
            rows.append(
                identity_fields(tax["invoice_id"])
                | {
                    "row_kind": "CREDIT_POSITION",
                    "component_id": key,
                    "as_of": as_of,
                    "tax_code": tax["code"],
                    **{name: fixed(amount) for name, amount in position.items()},
                }
            )
        from reports.domain.tax_summaries import selected

        return [row for row in rows if selected(row, query)]

    if query.code == "INVOICE_SETTLEMENT_REGISTER":
        by_line = {item["journal_line_id"]: key for key, item in data.rows["open_item"].items()}
        bills = {
            by_line[link["journal_line_id"]]: link["invoice_id"]
            for link in data.rows["invoice_posting_line"].values()
            if link["invoice_id"] in invoices
            and link["tracking"] == "NEW_REF"
            and link["journal_line_id"] in by_line
        }
        for key, allocation in sorted(data.rows["allocation"].items()):
            if allocation["posting_date"] > as_of:
                continue
            for side in ("debt", "credit"):
                item_id = allocation[side + "_item_id"]
                if item_id not in bills:
                    continue
                rows.append(
                    identity_fields(bills[item_id])
                    | {
                        "row_kind": "SETTLEMENT",
                        "allocation_id": key,
                        "bill_item_id": item_id,
                        "other_item_id": allocation[
                            ("credit" if side == "debt" else "debt") + "_item_id"
                        ],
                        "posting_date": allocation["posting_date"],
                        "settlement_amount": allocation["amount"],
                        "reversal_date": allocation["reversal_date"],
                        "as_of": as_of,
                        "active": not allocation["reversal_date"]
                        or allocation["reversal_date"] > as_of,
                    }
                )
        return rows

    def gl_row(
        invoice_id: str,
        line_id: str,
        component_id: str | None,
        purpose: str,
        event_date: str | None,
    ) -> None:
        line = data.rows["journal_line"][line_id]
        journal = data.journals[line["journal_id"]]
        tax = taxes.get(component_id or "")
        if query.code == "TAX_GL_BRIDGE" and tax is None:
            return
        selected_date = event_date if query.date_basis == "TAX_POINT" else journal["posting_date"]
        if not in_range(selected_date, query) or journal["status"] != "POSTED":
            return
        rows.append(
            identity_fields(invoice_id)
            | {
                "row_kind": "GL_ENTRY",
                "journal_id": line["journal_id"],
                "journal_posting_date": journal["posting_date"],
                "line_id": line_id,
                "component_id": component_id,
                "tax_code": tax["code"] if tax else None,
                "tax_purpose": purpose,
                "event_date": event_date,
                "posting_date": journal["posting_date"],
                "account_id": line["account_id"],
                "account_code": data.accounts[line["account_id"]]["code"],
                "account_name": data.accounts[line["account_id"]]["name"],
                "currency": line["currency"],
                "side": line["side"],
                "amount": line["amount"],
                "signed_debit": fixed(
                    money(line["amount"]) * (1 if line["side"] == "DEBIT" else -1)
                ),
            }
        )

    for link in data.rows["invoice_posting_line"].values():
        if link["invoice_id"] not in invoices:
            continue
        linked_tax = taxes.get(link["tax_component_id"])
        point = (
            data.rows["invoice_supply_fact"][linked_tax["supply_id"]]["tax_point_date"]
            if linked_tax
            else None
        )
        gl_row(
            link["invoice_id"],
            link["journal_line_id"],
            link["tax_component_id"],
            link["tax_purpose"] or "COMMERCIAL",
            point,
        )
        reversed_fact = reversals.get(journals[link["invoice_id"]])
        if reversed_fact and invoices[link["invoice_id"]]["kind"] in {"SALES", "PURCHASE"}:
            reversal_id, reversal = reversed_fact
            source_line = data.rows["journal_line"][link["journal_line_id"]]
            matching = [
                identity
                for identity, line in data.rows["journal_line"].items()
                if line["journal_id"] == reversal_id
                and line["sequence"] == source_line["sequence"]
                and line["account_id"] == source_line["account_id"]
                and line["amount"] == source_line["amount"]
                and line["side"] != source_line["side"]
            ]
            if len(matching) != 1:
                raise ConflictError("Purchase correction GL does not match its retained invoice")
            gl_row(
                link["invoice_id"],
                matching[0],
                link["tax_component_id"],
                "REVERSAL",
                reversal["posting_date"] if link["tax_component_id"] else None,
            )
    for _, action in actions:
        for line_id, line in data.rows["journal_line"].items():
            if line["journal_id"] == action["journal_id"]:
                gl_row(
                    action["invoice_id"],
                    line_id,
                    action["component_id"],
                    action["kind"],
                    action["event_date"],
                )
    if query.code == "TAX_GL_BRIDGE":
        from reports.domain.tax_summaries import selected

        rows = [
            row
            for row in rows
            if selected(row, query)
            and (not query.tax_ledger_id or row["account_id"] == str(query.tax_ledger_id))
            and (not query.tax_purpose or row["tax_purpose"] == query.tax_purpose)
        ]
    return sorted(rows, key=lambda r: (r["posting_date"], r["journal_id"], r["line_id"]))

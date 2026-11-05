"""Native invoice facts attached to the existing multi-year settlement fixture."""

import uuid

from financial_fixture import financial_dataset
from fixtures import source


def invoice_dataset():
    facts, ids = financial_dataset()
    journal = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "invoice"
    )
    invoice, intent, supply = [uuid.uuid4() for _ in range(3)]
    ids |= {"invoice": str(invoice), "supply": str(supply)}
    facts.extend(
        [
            source(
                "voucher_money_intent",
                intent,
                {
                    "execution_id": str(uuid.uuid4()),
                    "voucher_id": str(uuid.uuid4()),
                    "journal_id": str(journal.source_id),
                    "kind": "SALES",
                    "status": "COMMITTED",
                    "posting_date": "2026-04-02",
                },
            ),
            source(
                "invoice_record",
                invoice,
                {
                    "intent_id": str(intent),
                    "revision_id": str(uuid.uuid4()),
                    "calculation_version": 1,
                    "calculation_hash": "a" * 64,
                    "configuration_hash": "b" * 64,
                    "company_configuration_hash": "c" * 64,
                    "kind": "SALES",
                    "source_invoice_id": None,
                    "currency": "INR",
                    "document_date": "2026-03-31",
                    "posting_date": "2026-04-02",
                    "party_account_id": ids["party"],
                    "bill_reference": "INV-1",
                    "due_date": "2026-04-30",
                    "commercial_total": "200",
                    "tax_total": "0",
                    "charged_tax_total": "0",
                    "rounding": "0",
                    "payable": "200",
                    "supplier_declared_total": None,
                    "supplier_difference": None,
                    "supplier_difference_reason": None,
                },
            ),
            source(
                "invoice_supply_fact",
                supply,
                {
                    "invoice_id": str(invoice),
                    "line_key": str(uuid.uuid4()),
                    "sequence": 1,
                    "account_id": ids["income"],
                    "supply_kind": "ACCOUNT",
                    "description": "Service",
                    "entered": "200",
                    "commercial": "200",
                    "taxable": "200",
                    "price_rounding": "0",
                    "payable": "200",
                    "tax_profile": "UNTAXED_ACCOUNT",
                    "date_contract_version": 2,
                    "tax_point_date": None,
                    "tax_point_basis": None,
                    "service_completion_date": None,
                    "company_registration_id": None,
                    "party_registration_id": None,
                    "place_of_supply": None,
                    "supply_context": None,
                    "classification_code": None,
                    "treatment": "NONE",
                    "reverse_charge": False,
                    "credit_state": "NONE",
                    "supplier_invoice_number": None,
                    "supplier_invoice_date": None,
                },
            ),
        ]
    )
    facts = [
        source(
            row.entity,
            row.source_id,
            row.data | {"reference": "INV-1", "due_date": "2026-04-30"},
        )
        if row.entity == "open_item" and row.data["reference"] == "invoice"
        else row
        for row in facts
    ]
    for row in list(facts):
        if row.entity != "journal_line" or row.data["journal_id"] != str(journal.source_id):
            continue
        facts.append(
            source(
                "invoice_posting_line",
                uuid.uuid4(),
                {
                    "invoice_id": str(invoice),
                    "journal_line_id": str(row.source_id),
                    "tax_component_id": None,
                    "tax_purpose": None,
                    "line_key": str(uuid.uuid4()),
                    "sequence": row.data["sequence"],
                    "source_version": 1,
                    "purpose": "PRINCIPAL",
                    "tracking": "NEW_REF" if row.data["account_id"] == ids["party"] else "NONE",
                    "bill_reference": "INV-1" if row.data["account_id"] == ids["party"] else None,
                    "due_date": "2026-04-30" if row.data["account_id"] == ids["party"] else None,
                },
            )
        )
    return sorted(facts, key=lambda row: (row.entity, str(row.source_id))), ids

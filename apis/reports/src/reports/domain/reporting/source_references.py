"""Owner-local relationships used to prefetch bounded validation inputs."""

from typing import Any

REFERENCES = {
    "account": {"group_id": "account_group", "party_id": "party"},
    "account_group": {"head_id": "account_head", "parent_id": "account_group"},
    "fiscal_period": {"fiscal_year_id": "fiscal_year"},
    "fiscal_status_transition": {"period_id": "fiscal_period"},
    "journal": {"fiscal_period_id": "fiscal_period", "reversal_of_id": "journal"},
    "journal_line": {"journal_id": "journal", "account_id": "account", "party_id": "party"},
    "open_item": {"journal_line_id": "journal_line", "account_id": "account"},
    "allocation": {"debt_item_id": "open_item", "credit_item_id": "open_item"},
    "opening_batch": {"journal_id": "journal"},
    "voucher_money_intent": {"journal_id": "journal"},
    "voucher_money_allocation": {
        "intent_id": "voucher_money_intent",
        "allocation_id": "allocation",
    },
    "bank_instrument": {"journal_line_id": "journal_line", "intent_id": "voucher_money_intent"},
    "bank_instrument_event": {"instrument_id": "bank_instrument"},
    "bank_statement_import": {"account_id": "account"},
    "bank_statement_entry": {"import_id": "bank_statement_import"},
    "bank_match_event": {
        "statement_entry_id": "bank_statement_entry",
        "instrument_id": "bank_instrument",
        "reverses_id": "bank_match_event",
    },
    "bank_opening_item": {"account_id": "account", "instrument_id": "bank_instrument"},
    "bank_reconciliation_session": {"account_id": "account"},
    "bank_adjustment_proposal": {"statement_entry_id": "bank_statement_entry"},
    "source_document": {"journal_id": "journal"},
    "invoice_record": {
        "intent_id": "voucher_money_intent",
        "party_account_id": "account",
        "source_invoice_id": "invoice_record",
    },
    "invoice_supply_fact": {"invoice_id": "invoice_record", "account_id": "account"},
    "invoice_component_fact": {"invoice_id": "invoice_record", "account_id": "account"},
    "invoice_allocation_fact": {
        "invoice_id": "invoice_record",
        "component_id": "invoice_component_fact",
        "supply_id": "invoice_supply_fact",
    },
    "invoice_tax_component": {"invoice_id": "invoice_record", "supply_id": "invoice_supply_fact"},
    "invoice_posting_line": {
        "invoice_id": "invoice_record",
        "journal_line_id": "journal_line",
        "tax_component_id": "invoice_tax_component",
    },
    "invoice_credit_action": {
        "invoice_id": "invoice_record",
        "component_id": "invoice_tax_component",
        "journal_id": "journal",
        "offset_account_id": "account",
        "cash_deposit_line_id": "journal_line",
    },
    "invoice_credit_event": {"invoice_id": "invoice_record", "action_id": "invoice_credit_action"},
    "gst_return_record": {"original_record_id": "gst_return_record"},
    "journal_tax": {"journal_id": "journal"},
}


def references(entity: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    result = [
        (target, str(data[key]))
        for key, target in REFERENCES.get(entity, {}).items()
        if data.get(key)
    ]
    if entity == "gst_return_record" and data["source_entity"] != "EXTERNAL":
        result.append((data["source_entity"], str(data["source_id"])))
    if entity == "opening_batch":
        result.extend(("journal", str(key)) for key in data.get("journal_ids", []))
        if data.get("coverage"):
            result.extend(
                ("account", str(entry["account_id"]))
                for entry in data["coverage"].get("ytd_summary") or []
            )
    if entity == "bank_reconciliation_session":
        result.extend(
            ("bank_statement_import", str(key)) for key in data["snapshot"].get("import_ids", [])
        )
    return result

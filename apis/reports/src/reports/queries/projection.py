"""Deterministic native columns derived from retained, validated source JSON."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.exact import exact_decimal

QUERY_VERSION = 4


def source_projection(entity: str, data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    parent_field = {
        "journal_line": "journal_id",
        "account": "group_id",
        "account_group": "head_id",
        "fiscal_period": "fiscal_year_id",
        "fiscal_status_transition": "period_id",
        "open_item": "journal_line_id",
        "allocation": "debt_item_id",
        "bank_instrument": "journal_line_id",
        "bank_instrument_event": "instrument_id",
        "bank_statement_entry": "import_id",
        "bank_match_event": "statement_entry_id",
        "bank_opening_item": "instrument_id",
        "bank_adjustment_proposal": "statement_entry_id",
        "voucher_money_allocation": "intent_id",
        "source_document": "journal_id",
        "invoice_record": "intent_id",
        "gst_outward_record": "registration_id",
    }.get(entity, "invoice_id" if entity.startswith("invoice_") else "journal_id")
    result: dict[str, Any] = {}
    result["inventory_kind"] = (
        data.get("payload", {}).get("kind") if entity == "inventory_report_record" else None
    )
    origin_field = {
        "invoice_record": "source_invoice_id",
        "allocation": "credit_item_id",
        "bank_match_event": "instrument_id",
        "gst_outward_record": "original_record_id",
    }.get(entity)
    origin = data.get(origin_field) if origin_field else None
    result["origin_id"] = uuid.UUID(origin) if origin else None
    for key, source in (
        ("relation_id", parent_field),
        ("account_id", "party_account_id" if entity == "invoice_record" else "account_id"),
        ("party_id", "party_id"),
    ):
        value = data.get(source)
        result[key] = uuid.UUID(value) if value else None
    for key in ("currency", "base_currency", "side"):
        result[key] = data.get(key)
    result["source_status"] = (
        data.get("kind") if entity == "gst_outward_record" else data.get("status")
    )
    for key, currency in (("amount", "currency"), ("base_amount", "base_currency")):
        result[key] = (
            exact_decimal(data[key]) if data.get(key) is not None and data.get(currency) else None
        )
    source_date = (
        data.get("return_date") if entity == "gst_outward_record" else data.get("posting_date")
    )
    result["posting_date"] = dt.date.fromisoformat(source_date) if source_date else None
    return result

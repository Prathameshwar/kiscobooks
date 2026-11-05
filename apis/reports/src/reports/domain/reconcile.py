"""Pure committed-source reconciliation and exact daily/monthly projection rules."""

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.exact import exact_decimal
from reporting_contract.contract import FACT_MODELS, Control, Fact, Journal, Line, digest
from reporting_contract.invoice import INVOICE_FACT_MODELS

from reports.domain.invoice_reconciliation import reconcile_invoices
from reports.domain.reporting.opening_coverage import OpeningControls

RULE_HASH = digest(
    {"report": "SOURCE_RECONCILIATION", "version": 2, "basis": "OWNER_BASE_CURRENCY"}
)


def money(value: Any) -> Decimal:
    return exact_decimal(value)


def fixed(value: Decimal) -> str:
    return format(money(format(value, "f")), ".4f")


def reconcile(
    facts: list[Fact], expected: Control
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    live = {(row.entity, str(row.source_id)): row.data for row in facts if row.data is not None}
    if len(live) != sum(row.data is not None for row in facts):
        raise ConflictError("duplicate source identities")
    counts = dict(Counter(key[0] for key in live))
    if {key: counts.get(key, 0) for key in FACT_MODELS} != {
        key: expected.counts.get(key, 0) for key in FACT_MODELS
    } or set(expected.counts) - FACT_MODELS.keys():
        raise ConflictError("source grain counts differ")
    if expected.coverage_kind != "RETAINED_LEDGER" or expected.coverage_start is None:
        raise ConflictError("financial history coverage is unavailable")

    def require(entity: str, key: Any) -> dict[str, Any]:
        value = live.get((entity, str(key)))
        if value is None:
            raise ConflictError("required source reference is missing")
        return value

    for (entity, identity), data in live.items():
        assert data is not None
        validate_source_record(entity, identity, data, require)
    opening_controls = OpeningControls()
    for (entity, _), data in live.items():
        if entity == "opening_batch":
            opening_controls.register(data, require)
    journal_totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
    )
    totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
    )
    grouped: dict[tuple[str, str, str, dt.date], dict[str, Decimal]] = defaultdict(
        lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
    )
    lines = []
    for (entity, identity), data in live.items():
        assert data is not None
        if entity != "journal_line":
            continue
        projected = validated_line(identity, data, require, expected.coverage_start)
        if projected is None:
            continue
        opening_controls.add(data, require)
        amount, side = projected["base_amount"], projected["side"]
        journal_totals[projected["journal_id"]][side] += amount
        totals[projected["base_currency"]][side] += amount
        for grain, start in (
            ("DAY", projected["posting_date"]),
            ("MONTH", projected["posting_date"].replace(day=1)),
        ):
            grouped[(projected["account_id"], projected["base_currency"], grain, start)][side] += (
                amount
            )
        lines.append(projected)
    for (entity, identity), data in live.items():
        assert data is not None
        if entity == "journal" and data["status"] == "POSTED":
            sides = journal_totals[identity]
            if (
                sides["DEBIT"] != sides["CREDIT"]
                or sides["DEBIT"] <= 0
                or sides["DEBIT"] != money(data["total_debit"])
                or sides["CREDIT"] != money(data["total_credit"])
            ):
                raise ConflictError("posted journal does not reconcile")
    opening_controls.finish()
    wire_totals = {
        currency: {side: fixed(value) for side, value in sides.items()}
        for currency, sides in totals.items()
    }
    normalized_expected = {
        currency: {side: fixed(money(value)) for side, value in sides.items()}
        for currency, sides in expected.base_totals.items()
    }
    if wire_totals != normalized_expected:
        raise ConflictError("owner control totals differ")
    reconcile_invoices(live)
    summaries = [
        {
            "account_id": account,
            "currency": currency,
            "grain": grain,
            "start_date": start,
            "debit": money(sides["DEBIT"]),
            "credit": money(sides["CREDIT"]),
        }
        for (account, currency, grain, start), sides in sorted(grouped.items())
    ]
    return (
        lines,
        summaries,
        {
            "counts": expected.counts,
            "base_totals": wire_totals,
            "coverage_start": expected.coverage_start.isoformat(),
            "coverage_kind": expected.coverage_kind,
            "rule_hash": RULE_HASH,
            "differences": [],
        },
    )


def immutable_claim(row: Fact, journals: dict[str, dict[str, Any]]) -> str | None:
    if row.data is None:
        return None
    data = row.data
    if row.entity == "inventory_report_record":
        return digest(data) if data["payload"]["kind"] == "MOVEMENT" else None
    if row.entity == "journal_line":
        if journals.get(data["journal_id"], {}).get("status") != "POSTED":
            return None
    elif row.entity == "journal":
        if data["status"] != "POSTED":
            return None
    elif row.entity not in INVOICE_FACT_MODELS and row.entity not in {
        "open_item",
        "allocation",
        "voucher_execution",
        "bank_instrument",
        "bank_instrument_event",
        "bank_match_event",
        "bank_opening_item",
        "voucher_money_allocation",
    }:
        return None
    return digest(
        {
            key: value
            for key, value in data.items()
            if key not in {"reversal_journal_id", "reversal_date", "fx_reversal_id"}
        }
    )


def validate_source_record(
    entity: str,
    identity: str,
    data: dict[str, Any],
    require: Callable[[str, Any], dict[str, Any]],
) -> None:
    assert data is not None
    if entity == "gst_return_record":
        from reporting_contract.gst import GstReturnRecord

        GstReturnRecord.model_validate(data)
        if data["source_entity"] != "EXTERNAL":
            source = require(data["source_entity"], data["source_id"])
            if (
                data["source_entity"] == "invoice_supply_fact"
                and source["company_registration_id"] != data["registration_id"]
            ):
                raise ConflictError("GST supply allocation belongs to another registration")
        if data.get("original_record_id"):
            original = require("gst_return_record", data["original_record_id"])
            if original["registration_id"] != data["registration_id"]:
                raise ConflictError("GST adjustment belongs to another registration")
    if entity == "account":
        require("account_group", data["group_id"])
        if data["party_id"]:
            require("party", data["party_id"])
    if entity == "fiscal_status_transition":
        require("fiscal_period", data["period_id"])
    if entity == "account_group":
        require("account_head", data["head_id"])
        seen = {identity}
        parent = data["parent_id"]
        while parent:
            if parent in seen:
                raise ConflictError("classification hierarchy contains a cycle")
            seen.add(parent)
            parent = require("account_group", parent)["parent_id"]
    if entity == "open_item":
        if data["document_date"] is None or data["due_date"] is None:
            if (
                data["document_date"] is not None
                or data["due_date"] is not None
                or data["terms"].get("tracking") != "ON_ACCOUNT"
                or not data["terms"].get("history_unknown")
            ):
                raise ConflictError("unknown bill dates require explicit on-account provenance")
        source = require("journal_line", data["journal_line_id"])
        require("account", data["account_id"])
        if source["account_id"] != data["account_id"] or source["party_id"] != data["party_id"]:
            raise ConflictError("open item source identity differs")
    if entity == "allocation":
        debt = require("open_item", data["debt_item_id"])
        credit = require("open_item", data["credit_item_id"])
        if (
            debt["party_id"] != credit["party_id"]
            or debt["role"] != credit["role"]
            or debt["currency"] != data["currency"]
            or credit["currency"] != data["currency"]
        ):
            raise ConflictError("allocation source identity differs")
    if (
        entity == "opening_batch"
        and data["status"] in {"FINALIZED", "REVERSED"}
        and data["journal_id"] is not None
    ):
        require("journal", data["journal_id"])
    if entity == "voucher_money_intent" and data["journal_id"] is not None:
        require("journal", data["journal_id"])
    if entity == "voucher_money_allocation":
        require("voucher_money_intent", data["intent_id"])
        require("allocation", data["allocation_id"])
    if entity == "bank_instrument":
        bank_line = require("journal_line", data["journal_line_id"])
        if data["intent_id"] is not None:
            require("voucher_money_intent", data["intent_id"])
        if (
            data["account_id"] != bank_line["account_id"]
            or data["currency"] != bank_line["currency"]
            or money(data["amount"]) <= 0
        ):
            raise ConflictError("bank instrument differs from its journal line")
    if entity == "bank_instrument_event":
        instrument = require("bank_instrument", data["instrument_id"])
        if data["event_date"] < instrument["booking_date"]:
            raise ConflictError("bank history precedes booking")
    if entity == "bank_statement_import":
        account = require("account", data["account_id"])
        if account["kind"] != "BANK" or data["period_from"] > data["period_to"]:
            raise ConflictError("statement import is not scoped to a valid bank period")
    if entity == "bank_statement_entry":
        batch = require("bank_statement_import", data["import_id"])
        if (
            data["account_id"] != batch["account_id"]
            or data["currency"] != batch["currency"]
            or not batch["period_from"] <= data["transaction_date"] <= batch["period_to"]
            or money(data["amount"]) <= 0
        ):
            raise ConflictError("statement row differs from its owner import")
    if entity == "bank_match_event":
        entry = require("bank_statement_entry", data["statement_entry_id"])
        instrument = require("bank_instrument", data["instrument_id"])
        if (
            entry["account_id"] != instrument["account_id"]
            or entry["currency"] != instrument["currency"]
            or data["bank_date"] != entry["transaction_date"]
            or money(data["amount"]) <= 0
        ):
            raise ConflictError("bank allocation crosses evidence boundaries")
        if data["reverses_id"] is not None:
            require("bank_match_event", data["reverses_id"])
    if entity == "bank_opening_item":
        account = require("account", data["account_id"])
        instrument = require("bank_instrument", data["instrument_id"])
        if account["kind"] != "BANK" or instrument["account_id"] != data["account_id"]:
            raise ConflictError("opening bank item does not belong to the account")
    if entity == "bank_reconciliation_session":
        account = require("account", data["account_id"])
        if account["kind"] != "BANK" or data["period_from"] > data["period_to"]:
            raise ConflictError("bank session has an invalid account or period")
        for import_id in data["snapshot"].get("import_ids", []):
            require("bank_statement_import", import_id)
    if entity == "bank_adjustment_proposal":
        entry = require("bank_statement_entry", data["statement_entry_id"])
        if (
            entry["account_id"] != data["account_id"]
            or entry["currency"] != data["currency"]
            or not 0 < money(data["amount"]) <= money(entry["amount"])
        ):
            raise ConflictError("bank adjustment proposal differs from its statement row")
    if entity == "source_document":
        require("journal", data["journal_id"])


def validated_line(
    identity: str,
    data: dict[str, Any],
    require: Callable[[str, Any], dict[str, Any]],
    coverage_start: dt.date,
) -> dict[str, Any] | None:
    line = Line.model_validate(data)
    journal = Journal.model_validate(require("journal", line.journal_id))
    if journal.status != "POSTED":
        return None
    require("account", line.account_id)
    if line.party_id:
        require("party", line.party_id)
    period = require("fiscal_period", journal.fiscal_period_id)
    require("fiscal_year", period["fiscal_year_id"])
    if (
        journal.posting_date < coverage_start
        or not dt.date.fromisoformat(period["start_date"])
        <= journal.posting_date
        <= dt.date.fromisoformat(period["end_date"])
        or journal.base_currency != line.base_currency
    ):
        raise ConflictError("source period/currency/coverage differs")
    amount = money(line.base_amount)
    return {
        "source_id": identity,
        "journal_id": str(line.journal_id),
        "account_id": str(line.account_id),
        "party_id": str(line.party_id) if line.party_id else None,
        "role": line.role,
        "period_id": str(journal.fiscal_period_id),
        "posting_date": journal.posting_date,
        "component": line.component,
        "side": line.side,
        "currency": line.currency,
        "amount": money(line.amount),
        "base_currency": line.base_currency,
        "base_amount": amount,
    }

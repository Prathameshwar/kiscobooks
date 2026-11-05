"""As-of bill/advance/aging and bank reconciliation from dated native histories."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.money import quantize_storage

from reports.domain.reconcile import fixed, money
from reports.domain.statements import Facts
from reports.schemas.requests import RunRequest


def outstanding(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_to
    date = query.date_to.isoformat()
    allocated: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for allocation in data.rows["allocation"].values():
        if allocation["posting_date"] > date or (
            allocation["reversal_date"] and allocation["reversal_date"] <= date
        ):
            continue
        for side in ("debt", "credit"):
            item_id = allocation[side + "_item_id"]
            allocated[item_id]["amount"] += money(allocation["amount"])
            allocated[item_id]["base"] += money(allocation[side + "_base_amount"])
    result = []
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for identity, item in sorted(data.rows["open_item"].items()):
        account = data.accounts[item["account_id"]]
        if (
            item["posting_date"] > date
            or (item["reversal_date"] and item["reversal_date"] <= date)
            or not data.selected(account, item["account_id"], query)
        ):
            continue
        if query.basis == "TRANSACTION" and item["currency"] != query.currency:
            continue
        remaining = money(item["amount"]) - allocated[identity]["amount"]
        base = money(item["base_amount"]) - allocated[identity]["base"]
        if remaining < 0 or base < 0 or (remaining == 0 and base != 0):
            raise ConflictError("bill allocations exceed owner carrying balances")
        amount = base if query.basis == "BASE" else remaining
        positive = (item["role"] == "CUSTOMER") == (item["direction"] == "DEBT")
        totals[item["account_id"]] += amount if positive else -amount
        if remaining == 0:
            continue
        import datetime as dt

        days = (
            max(0, (query.date_to - dt.date.fromisoformat(item["due_date"])).days)
            if item["due_date"]
            else None
        )
        bucket = (
            "UNKNOWN"
            if days is None
            else "CURRENT"
            if days == 0
            else "DAYS_1_30"
            if days <= 30
            else "DAYS_31_60"
            if days <= 60
            else "DAYS_61_90"
            if days <= 90
            else "DAYS_OVER_90"
        )
        result.append(
            {
                "row_kind": "BILL",
                "item_id": identity,
                "account_id": item["account_id"],
                "account_code": account["code"],
                "account_name": account["name"],
                "party_id": item["party_id"],
                "role": item["role"],
                "direction": item["direction"],
                "reference": item["reference"],
                "document_date": item["document_date"],
                "posting_date": item["posting_date"],
                "due_date": item["due_date"],
                "currency": item["currency"],
                "original_amount": item["amount"],
                "allocated_amount": fixed(allocated[identity]["amount"]),
                "remaining": fixed(remaining),
                "base_currency": item["base_currency"],
                "base_remaining": fixed(base),
                "report_amount": fixed(amount),
                "report_currency": query.currency or data.currency,
                "tracking": item["terms"].get(
                    "tracking", "NEW_REF" if item["direction"] == "DEBT" else "ON_ACCOUNT"
                ),
                "days_overdue": days,
                "aging_bucket": bucket,
            }
        )
    ledger: dict[str, Decimal] = defaultdict(Decimal)
    for line in data.lines(query):
        if (
            line["posting_date"] <= query.date_to
            and data.accounts[line["account_id"]]["kind"] == "PARTY"
        ):
            ledger[line["account_id"]] += line["signed"]
    if any(totals[account] != ledger[account] for account in totals.keys() | ledger.keys()):
        raise ConflictError("party open items do not reconcile to the as-of general ledger")
    return result


def aging(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for row in rows:
        key = (row["party_id"], row["role"], row["account_id"], row["report_currency"])
        amount = money(row["report_amount"])
        if row["direction"] == "CREDIT":
            grouped[key]["unapplied_credit"] += amount
        else:
            grouped[key]["debt"] += amount
            grouped[key][row["aging_bucket"]] += amount
    return [
        {
            "row_kind": "AGING",
            "party_id": key[0],
            "role": key[1],
            "account_id": key[2],
            "currency": key[3],
            **{
                name: fixed(values[name])
                for name in (
                    "debt",
                    "unapplied_credit",
                    "CURRENT",
                    "DAYS_1_30",
                    "DAYS_31_60",
                    "DAYS_61_90",
                    "DAYS_OVER_90",
                    "UNKNOWN",
                )
            },
        }
        for key, values in sorted(grouped.items())
    ]


def instrument_values(
    line: dict[str, Any], instruments: list[tuple[str, dict[str, Any]]], basis: str
) -> list[tuple[str, dict[str, Any], Decimal]]:
    native_sum = sum((money(item["amount"]) for _, item in instruments), Decimal(0))
    if native_sum > money(line["amount"]):
        raise ConflictError("instruments exceed their native bank line")
    base_left = money(line["base_amount"])
    result = []
    for index, (identity, instrument) in enumerate(sorted(instruments)):
        native = money(instrument["amount"])
        base = (
            base_left
            if index == len(instruments) - 1 and native_sum == money(line["amount"])
            else quantize_storage(money(line["base_amount"]) * native / money(line["amount"]))
        )
        base_left -= base
        result.append((identity, instrument, base if basis == "BASE" else native))
    return result


def payments(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    """One tender per row, with explicit legacy coverage and no multiplied voucher totals."""
    assert query.date_from and query.date_to
    kind = "PAYMENT" if query.code == "PAYMENT_REGISTER" else "RECEIPT"
    lineage = data.lineage()
    kinds = {
        item["journal_id"]: item["kind"]
        for item in data.rows["voucher_money_intent"].values()
        if item["journal_id"]
    }
    rows = []
    matching_parties = {
        line["journal_id"]
        for line in data.rows["journal_line"].values()
        if (not query.party_id or line["party_id"] == str(query.party_id))
        and (not query.role or line["role"] == query.role)
    }
    source_lines = {
        (line["journal_id"], line["sequence"]): key
        for key, line in data.rows["journal_line"].items()
    }
    by_line: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for identity, instrument in data.rows["bank_instrument"].items():
        by_line[instrument["journal_line_id"]].append((identity, instrument))
    for line in data.lines(query.model_copy(update={"party_id": None, "role": None})):
        original_id = data.journals[line["journal_id"]]["reversal_of_id"]
        source_id = original_id or line["journal_id"]
        if (
            not query.date_from <= line["posting_date"] <= query.date_to
            or data.accounts[line["account_id"]]["kind"] not in {"CASH", "BANK"}
            or kinds.get(source_id, data.journals[source_id]["kind"]) != kind
            or line["journal_id"] not in matching_parties
        ):
            continue
        source_line = source_lines[(source_id, line["sequence"])]
        instruments = by_line[source_line]
        values = instrument_values(line, instruments, query.basis)
        covered = sum((value for _, _, value in values), Decimal(0))
        if covered != line["value"]:
            values.append(
                (
                    "",
                    {
                        "mode": "UNSPECIFIED",
                        "reference": None,
                        "instrument_date": None,
                        "recognition": None,
                    },
                    line["value"] - covered,
                )
            )
        for identity, instrument, amount in values:
            rows.append(
                {
                    "row_kind": "TENDER",
                    "voucher_kind": kind,
                    "journal_id": line["journal_id"],
                    "line_id": line["line_id"],
                    "reversal_of_id": original_id,
                    "number": line["number"],
                    "posting_date": line["posting_date"].isoformat(),
                    "account_id": line["account_id"],
                    "account_code": data.accounts[line["account_id"]]["code"],
                    "account_name": data.accounts[line["account_id"]]["name"],
                    "instrument_id": identity or None,
                    "side": line["side"],
                    "amount": fixed(amount),
                    "currency": query.currency or data.currency,
                    "signed_amount": fixed(amount if line["side"] == "DEBIT" else -amount),
                    **{
                        name: instrument[name]
                        for name in ("mode", "reference", "instrument_date", "recognition")
                    },
                    **lineage.get(line["journal_id"], {}),
                }
            )
    return rows


def bank_reconciliation(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_to and query.account_id and query.statement_balance is not None
    account_id, day = str(query.account_id), query.date_to.isoformat()
    if data.accounts[account_id]["kind"] != "BANK":
        raise ConflictError("bank reconciliation requires a bank ledger")
    lines = [line for line in data.lines(query) if line["posting_date"] <= query.date_to]
    book = sum((line["signed"] for line in lines), Decimal(0))
    covered: dict[str, Decimal] = defaultdict(Decimal)
    pending = Decimal(0)
    rows = []
    histories: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for key, event in data.rows["bank_instrument_event"].items():
        if event["event_date"] <= day:
            histories[event["instrument_id"]].append((event["event_date"], key, event["action"]))
    corrections: dict[tuple[str, int], list[str]] = defaultdict(list)
    for line in lines:
        original = data.journals[line["journal_id"]]["reversal_of_id"]
        if original:
            corrections[(original, line["sequence"])].append(line["line_id"])
    by_line: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for identity, instrument in data.rows["bank_instrument"].items():
        if instrument["account_id"] == account_id and instrument["booking_date"] <= day:
            if query.basis == "TRANSACTION" and instrument["currency"] != query.currency:
                continue
            by_line[instrument["journal_line_id"]].append((identity, instrument))
    for line in lines:
        instruments = sorted(by_line[line["line_id"]])
        for identity, instrument, amount in instrument_values(line, instruments, query.basis):
            signed = amount if line["side"] == "DEBIT" else -amount
            covered[line["line_id"]] += amount
            events = histories[identity]
            state = max(events)[2] if events else "BOOKED"
            cleared = state in {"CLEARED", "RECONCILED", "UNRECONCILED"}
            if state == "REVERSED":
                for reversed_line_id in corrections[(line["journal_id"], line["sequence"])]:
                    covered[reversed_line_id] += amount
            elif not cleared:
                pending += signed
            rows.append(
                {
                    "row_kind": "BANK_INSTRUMENT",
                    "account_id": account_id,
                    "instrument_id": identity,
                    "journal_id": line["journal_id"],
                    "line_id": line["line_id"],
                    "booking_date": instrument["booking_date"],
                    "instrument_date": instrument["instrument_date"],
                    "mode": instrument["mode"],
                    "reference": instrument["reference"],
                    "state": state,
                    "amount": fixed(amount),
                    "signed_amount": fixed(signed),
                    "currency": query.currency or data.currency,
                    "cleared": cleared,
                }
            )
    if any(covered[line["line_id"]] != line["value"] for line in lines):
        raise ConflictError(
            "bank reconciliation requires instrument evidence for every retained bank entry, "
            "including openings"
        )
    expected = book - pending
    stated = money(query.statement_balance)
    rows.append(
        {
            "row_kind": "BANK_RECONCILIATION_CONTROL",
            "account_id": account_id,
            "as_of": day,
            "currency": query.currency or data.currency,
            "book_balance": fixed(book),
            "uncleared_signed": fixed(pending),
            "expected_statement_balance": fixed(expected),
            "statement_balance": fixed(stated),
            "difference": fixed(stated - expected),
            "balance_agrees": stated == expected,
            "statement_rows_verified": False,
            "reconciled": stated == expected,
        }
    )
    return rows


def bank_reconciliation_evidence(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    """Read a finalized Accounting session at one frozen owner generation."""
    assert query.session_id and query.account_id and query.date_from and query.date_to
    sessions = data.rows["bank_reconciliation_session"]
    selected = sessions.get(str(query.session_id))
    if selected is None:
        raise ConflictError("selected bank session is absent from this report generation")
    if (
        selected["status"] != "FINALIZED"
        or selected["account_id"] != str(query.account_id)
        or selected["period_from"] != query.date_from.isoformat()
        or selected["period_to"] != query.date_to.isoformat()
        or selected["currency"] != query.currency
    ):
        raise ConflictError("report selection differs from the frozen bank session")
    control = selected["snapshot"]
    if not control.get("balance_agrees") or not control.get("rows_covered"):
        raise ConflictError("finalized bank session has incomplete owner controls")
    entries = data.rows["bank_statement_entry"]
    imports = data.rows["bank_statement_import"]
    instruments = data.rows["bank_instrument"]
    events = data.rows["bank_match_event"]
    reversed_ids = {event["reverses_id"] for event in events.values() if event["reverses_id"]}
    active = {
        identity: event
        for identity, event in events.items()
        if event["reverses_id"] is None and identity not in reversed_ids
    }
    statement_used: dict[str, Decimal] = defaultdict(Decimal)
    instrument_used: dict[str, Decimal] = defaultdict(Decimal)
    for event in active.values():
        value = money(event["amount"])
        statement_used[event["statement_entry_id"]] += value
        if event["bank_date"] <= query.date_to.isoformat():
            instrument_used[event["instrument_id"]] += value
    rows: list[dict[str, Any]] = []
    for entry_id in control.get("entry_ids", []):
        entry = entries.get(entry_id)
        if entry is None or entry["account_id"] != str(query.account_id):
            raise ConflictError("bank statement membership differs from frozen session")
        batch = imports.get(entry["import_id"])
        if batch is None or batch["status"] != "COMMITTED":
            raise ConflictError("bank statement import is absent or uncommitted")
        matched = statement_used[entry_id]
        amount = money(entry["amount"])
        if matched > amount:
            raise ConflictError("bank statement row is overmatched")
        rows.append(
            {
                "row_kind": "STATEMENT_ROW",
                "account_id": str(query.account_id),
                "statement_entry_id": entry_id,
                "reference": entry.get("reference"),
                "transaction_date": entry["transaction_date"],
                "side": entry["side"],
                "amount": fixed(amount),
                "matched_amount": fixed(matched),
                "residual": fixed(amount - matched),
                "currency": selected["currency"],
            }
        )
    if any(row["residual"] != "0.0000" for row in rows):
        raise ConflictError("finalized bank session has unmatched statement evidence")
    movement = sum(
        (
            money(row["amount"]) if row["side"] == "CREDIT" else -money(row["amount"])
            for row in rows
        ),
        Decimal(0),
    )
    if fixed(movement) != control["statement_movement"] or money(
        selected["opening_balance"]
    ) + movement != money(selected["closing_balance"]):
        raise ConflictError("frozen statement movements do not reach the session closing")
    outstanding = Decimal(0)
    precleared_ids = set(control.get("precleared_instrument_ids", []))
    prior_bank_events: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for event_id, event in data.rows["bank_instrument_event"].items():
        if (
            event["instrument_id"] in precleared_ids
            and event["event_date"] < selected["period_from"]
        ):
            prior_bank_events[event["instrument_id"]].append((event_id, event))
    for instrument_id in control.get("instrument_ids", []):
        instrument = instruments.get(instrument_id)
        if instrument is None or instrument["account_id"] != str(query.account_id):
            raise ConflictError("bank book membership differs from frozen session")
        matched = instrument_used[instrument_id]
        amount = money(instrument["amount"])
        if instrument_id in precleared_ids:
            prior_events = prior_bank_events[instrument_id]
            if not prior_events or max(
                prior_events, key=lambda pair: (pair[1]["event_date"], pair[0])
            )[1]["action"] not in {"CLEARED", "RECONCILED"}:
                raise ConflictError("pre-cutover clearance lacks bank event evidence")
            if matched:
                raise ConflictError("pre-cutover clearance was also statement matched")
        if matched > amount:
            raise ConflictError("bank book instrument is overmatched")
        line = data.rows["journal_line"].get(instrument["journal_line_id"])
        if line is None:
            raise ConflictError("bank book instrument has no frozen journal line")
        cleared = amount if instrument_id in precleared_ids else matched
        outstanding += (amount - cleared) * (1 if line["side"] == "DEBIT" else -1)
        rows.append(
            {
                "row_kind": "BOOK_INSTRUMENT",
                "account_id": str(query.account_id),
                "journal_id": data.rows["journal_line"][instrument["journal_line_id"]][
                    "journal_id"
                ],
                "line_id": instrument["journal_line_id"],
                "instrument_id": instrument_id,
                "reference": instrument["reference"],
                "mode": instrument["mode"],
                "booking_date": instrument["booking_date"],
                "amount": fixed(amount),
                "matched_amount": fixed(matched),
                "residual": fixed(amount - cleared),
                "precleared_before_cutover": instrument_id in precleared_ids,
                "currency": selected["currency"],
            }
        )
    book_balance = sum(
        (line["signed"] for line in data.lines(query) if line["posting_date"] <= query.date_to),
        Decimal(0),
    )
    if (
        fixed(book_balance) != control["book_balance"]
        or fixed(outstanding) != control["outstanding_book_amount"]
        or book_balance - outstanding != money(selected["closing_balance"])
    ):
        raise ConflictError("frozen bank book and statement balances do not agree")
    rows.append(
        {
            "row_kind": "BANK_SESSION_CONTROL",
            "session_id": str(query.session_id),
            "account_id": str(query.account_id),
            "from": selected["period_from"],
            "to": selected["period_to"],
            "opening_balance": selected["opening_balance"],
            "closing_balance": selected["closing_balance"],
            "currency": selected["currency"],
            "book_balance": control["book_balance"],
            "outstanding_book_amount": control["outstanding_book_amount"],
            "source_sha256": control["source_sha256"],
            "status": "FINALIZED",
        }
    )
    return rows


def bank_reconciliation_worklist(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    """Frozen-generation bank/book residuals with dated clearance and aging."""
    assert query.account_id and query.date_from and query.date_to and query.currency
    account_id = str(query.account_id)
    account = data.accounts.get(account_id)
    if account is None or account["kind"] != "BANK":
        raise ConflictError("bank worklist requires a bank account")
    events = data.rows["bank_match_event"]
    reversed_ids = {row["reverses_id"] for row in events.values() if row["reverses_id"]}
    active = [
        row
        for identity, row in events.items()
        if row["reverses_id"] is None and identity not in reversed_ids
    ]
    statement_used: dict[str, Decimal] = defaultdict(Decimal)
    instrument_used: dict[str, Decimal] = defaultdict(Decimal)
    later_instruments: set[str] = set()
    for event in active:
        value = money(event["amount"])
        statement_used[event["statement_entry_id"]] += value
        if event["bank_date"] <= query.date_to.isoformat():
            instrument_used[event["instrument_id"]] += value
        else:
            later_instruments.add(event["instrument_id"])
    bank_history: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for event_id, event in data.rows["bank_instrument_event"].items():
        if event["event_date"] <= query.date_to.isoformat():
            bank_history[event["instrument_id"]].append((event_id, event))
    rows: list[dict[str, Any]] = []
    for identity, entry in data.rows["bank_statement_entry"].items():
        batch = data.rows["bank_statement_import"].get(entry["import_id"])
        if (
            entry["account_id"] != account_id
            or entry["currency"] != query.currency
            or batch is None
            or batch["status"] != "COMMITTED"
            or entry["review_status"] not in {"NEW", "ACCEPTED"}
            or not query.date_from.isoformat()
            <= entry["transaction_date"]
            <= query.date_to.isoformat()
        ):
            continue
        matched = statement_used[identity]
        amount = money(entry["amount"])
        if matched > amount:
            raise ConflictError("bank statement worklist row is overmatched")
        residual = amount - matched
        if residual == 0:
            continue
        rows.append(
            {
                "row_kind": "BANK_ACTIVITY",
                "account_id": account_id,
                "statement_entry_id": identity,
                "reference": entry.get("reference"),
                "source_id": identity,
                "date": entry["transaction_date"],
                "side": entry["side"],
                "amount": fixed(amount),
                "matched_amount": fixed(matched),
                "residual": fixed(residual),
                "currency": query.currency,
                "status": "BANK_ONLY" if matched == 0 else "PARTIAL" if residual else "MATCHED",
                "age_days": (query.date_to - dt.date.fromisoformat(entry["transaction_date"])).days,
            }
        )
    for identity, instrument in data.rows["bank_instrument"].items():
        if (
            instrument["account_id"] != account_id
            or instrument["currency"] != query.currency
            or instrument["booking_date"] > query.date_to.isoformat()
        ):
            continue
        line = data.rows["journal_line"].get(instrument["journal_line_id"])
        if line is None:
            raise ConflictError("bank worklist instrument lacks its journal line")
        matched = instrument_used[identity]
        amount = money(instrument["amount"])
        if matched > amount:
            raise ConflictError("bank worklist instrument is overmatched")
        residual = amount - matched
        history = bank_history[identity]
        latest = (
            max(history, key=lambda pair: (pair[1]["event_date"], pair[0]))[1]["action"]
            if history
            else None
        )
        later = identity in later_instruments
        if latest == "REVERSED" or residual == 0:
            continue
        status = (
            "RECONCILED_LATER"
            if later
            else "MANUAL_EVIDENCE"
            if latest in {"CLEARED", "RECONCILED"} and not matched
            else "BOOK_ONLY"
            if matched == 0
            else "PARTIAL"
            if residual
            else "MATCHED"
        )
        rows.append(
            {
                "row_kind": "BOOK_ACTIVITY",
                "account_id": account_id,
                "instrument_id": identity,
                "reference": instrument["reference"],
                "mode": instrument["mode"],
                "journal_id": line["journal_id"],
                "line_id": instrument["journal_line_id"],
                "source_id": identity,
                "date": instrument["booking_date"],
                "side": "CREDIT" if line["side"] == "DEBIT" else "DEBIT",
                "amount": fixed(amount),
                "matched_amount": fixed(matched),
                "residual": fixed(residual),
                "currency": query.currency,
                "status": status,
                "age_days": (
                    query.date_to - dt.date.fromisoformat(instrument["booking_date"])
                ).days,
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["row_kind"], row["source_id"]))


def register(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    if query.code in {"PAYMENT_REGISTER", "RECEIPT_REGISTER"}:
        return payments(data, query)
    if query.code == "BANK_RECONCILIATION":
        return bank_reconciliation(data, query)
    if query.code == "BANK_RECONCILIATION_EVIDENCE":
        return bank_reconciliation_evidence(data, query)
    if query.code == "BANK_RECONCILIATION_WORKLIST":
        return bank_reconciliation_worklist(data, query)
    rows = outstanding(data, query)
    if query.code == "AGING":
        values = aging(rows)
        for row in values:
            account = data.accounts[row["account_id"]]
            row.update(account_code=account["code"], account_name=account["name"])
        return values
    if query.code == "ADVANCES":
        return [row for row in rows if row["direction"] == "CREDIT"]
    return rows

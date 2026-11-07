"""Exact financial statements over frozen owner facts; no editable balance source."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from reporting_contract.contract import Fact, digest

from reports.domain.invoice_registers import CODES as INVOICE_CODES
from reports.domain.reconcile import fixed, money
from reports.domain.reporting.opening import opening_effect
from reports.domain.reporting.opening_coverage import (
    includes_ytd,
    migration,
    opening_earnings_bucket,
)
from reports.schemas.requests import RunRequest

STATEMENTS = frozenset({"TRIAL_BALANCE", "PROFIT_LOSS", "INCOME_EXPENSE", "BALANCE_SHEET"})
CODES = (
    "ACCOUNT_LEDGER",
    "DAY_BOOK",
    "TRIAL_BALANCE",
    "PROFIT_LOSS",
    "INCOME_EXPENSE",
    "BALANCE_SHEET",
    "BALANCE_CONTINUITY",
    "ACCOUNT_SUMMARY",
    "PARTY_LEDGER",
    "OUTSTANDING_BILLS",
    "ADVANCES",
    "AGING",
    "CASH_BOOK",
    "BANK_BOOK",
    "BANK_RECONCILIATION",
    "BANK_RECONCILIATION_EVIDENCE",
    "BANK_RECONCILIATION_WORKLIST",
    "PAYMENT_REGISTER",
    "RECEIPT_REGISTER",
    *INVOICE_CODES,
)
RULE_VERSIONS = {
    code: 2
    if code
    in {
        "ACCOUNT_SUMMARY",
        "PROFIT_LOSS",
        "INCOME_EXPENSE",
        "BALANCE_SHEET",
        "AGING",
        "OUTSTANDING_BILLS",
        "ADVANCES",
    }
    else 1
    for code in CODES
}
RULES = {
    code: digest(
        {
            "code": code,
            "version": RULE_VERSIONS[code],
            "basis": "FROZEN_OWNER_FACTS",
            "arithmetic": "EXACT_19_4",
            "earnings": "UNTRANSFERRED_WITH_SEPARATE_PRIOR_AND_CURRENT",
        }
    )
    for code in CODES
}


class Facts:
    def __init__(self, facts: list[Fact]) -> None:
        self.rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for fact in facts:
            if fact.data is not None:
                self.rows[fact.entity][str(fact.source_id)] = fact.data
        self.accounts = self.rows["account"]
        self.groups = self.rows["account_group"]
        self.journals = self.rows["journal"]
        self.finance = list(self.rows["financial_setup"].values())
        if len(self.finance) != 1:
            raise ConflictError("one authoritative financial setup is required")
        self.currency = str(self.finance[0]["base_currency"])

    def ancestry(self, group: str) -> list[str]:
        result = []
        while group:
            if group in result or group not in self.groups:
                raise ConflictError("invalid frozen classification hierarchy")
            result.append(group)
            group = self.groups[group]["parent_id"]
        return result

    def nature(self, account: dict[str, Any]) -> str:
        group = self.groups[account["group_id"]]
        return str(self.rows["account_head"][group["head_id"]]["nature"])

    def opening_effect(self, journal: dict[str, Any]) -> bool:
        original_id = journal.get("reversal_of_id")
        original = self.journals.get(str(original_id)) if original_id else None
        try:
            return opening_effect(
                journal["kind"], original_id is not None, original["kind"] if original else None
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def selected(self, account: dict[str, Any], identity: str, query: RunRequest) -> bool:
        return not (
            (query.account_id and identity != str(query.account_id))
            or (query.group_id and str(query.group_id) not in self.ancestry(account["group_id"]))
            or (query.party_id and account["party_id"] != str(query.party_id))
            or (query.role and account["party_role"] != query.role)
            or (query.code == "CASH_BOOK" and account["kind"] != "CASH")
            or (
                query.code
                in {
                    "BANK_BOOK",
                    "BANK_RECONCILIATION",
                    "BANK_RECONCILIATION_EVIDENCE",
                    "BANK_RECONCILIATION_WORKLIST",
                }
                and account["kind"] != "BANK"
            )
            or (query.code == "PARTY_LEDGER" and account["kind"] != "PARTY")
        )

    def lines(self, query: RunRequest) -> list[dict[str, Any]]:
        result = []
        for identity, line in self.rows["journal_line"].items():
            journal = self.journals[line["journal_id"]]
            account = self.accounts[line["account_id"]]
            if journal["status"] != "POSTED" or not self.selected(
                account, line["account_id"], query
            ):
                continue
            if query.basis == "TRANSACTION" and line["currency"] != query.currency:
                continue
            amount = money(line["base_amount"] if query.basis == "BASE" else line["amount"])
            result.append(
                line
                | {
                    "line_id": identity,
                    "posting_date": dt.date.fromisoformat(journal["posting_date"]),
                    "kind": journal["kind"],
                    "opening_effect": self.opening_effect(journal),
                    "number": journal["number"],
                    "value": amount,
                    "signed": amount if line["side"] == "DEBIT" else -amount,
                    "account_code": account["code"],
                    "account_name": account["name"],
                }
            )
        return sorted(
            result,
            key=lambda row: (
                row["posting_date"],
                row["journal_id"],
                row["sequence"],
                row["line_id"],
            ),
        )

    def lineage(self) -> dict[str, dict[str, Any]]:
        result = {}
        for data in self.rows["voucher_execution"].values():
            for effect in data["result"].get("effects", []):
                if effect["effect_kind"] == "JOURNAL":
                    result[effect["effect_id"]] = {
                        key: data.get(key)
                        for key in (
                            "voucher_id",
                            "revision_id",
                            "execution_id",
                            "kind",
                            "profile",
                            "type_revision_id",
                            "class_id",
                            "configuration_hash",
                        )
                    }
        return result


def ledger(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_from and query.date_to
    running: dict[str, Decimal] = defaultdict(Decimal)
    rows = []
    selected = data.lines(query)
    lineage = data.lineage()
    for line in selected:
        if line["posting_date"] < query.date_from:
            running[line["account_id"]] += line["signed"]
    accounts = {
        identity
        for identity, account in data.accounts.items()
        if data.selected(account, identity, query)
    }
    for identity in sorted(accounts):
        if query.code == "DAY_BOOK":
            continue
        rows.append(
            {
                "row_kind": "OPENING",
                "account_id": identity,
                "account_code": data.accounts[identity]["code"],
                "account_name": data.accounts[identity]["name"],
                "currency": query.currency or data.currency,
                "date": query.date_from.isoformat(),
                "balance": fixed(running[identity]),
            }
        )
    for line in selected:
        if not query.date_from <= line["posting_date"] <= query.date_to:
            continue
        running[line["account_id"]] += line["signed"]
        if query.journal_id and line["journal_id"] != str(query.journal_id):
            continue
        rows.append(
            {
                "row_kind": "ENTRY",
                "line_id": line["line_id"],
                "journal_id": line["journal_id"],
                "number": line["number"],
                "kind": data.journals[line["journal_id"]]["kind"],
                "date": line["posting_date"].isoformat(),
                "account_id": line["account_id"],
                "account_code": line["account_code"],
                "account_name": line["account_name"],
                "party_id": line["party_id"],
                "role": line["role"],
                "currency": query.currency or data.currency,
                "transaction_currency": line["currency"],
                "transaction_amount": line["amount"],
                "base_amount": line["base_amount"],
                "debit": fixed(line["value"] if line["side"] == "DEBIT" else Decimal(0)),
                "credit": fixed(line["value"] if line["side"] == "CREDIT" else Decimal(0)),
                "balance": fixed(running[line["account_id"]]),
                **lineage.get(line["journal_id"], {}),
            }
        )
    return rows


def balances(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_from and query.date_to
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for line in data.lines(query):
        if line["posting_date"] > query.date_to:
            continue
        field = (
            "opening"
            if line["posting_date"] < query.date_from
            or (line["opening_effect"] and line["posting_date"] == query.date_from)
            else line["side"].lower()
        )
        totals[line["account_id"]][field] += line["signed"] if field == "opening" else line["value"]
    result = []
    for identity, account in sorted(
        data.accounts.items(), key=lambda pair: (pair[1]["code"], pair[0])
    ):
        if not data.selected(account, identity, query):
            continue
        item = totals[identity]
        closing = item["opening"] + item["debit"] - item["credit"]
        result.append(
            {
                "row_kind": "ACCOUNT",
                "account_id": identity,
                "account_code": account["code"],
                "account_name": account["name"],
                "group_id": account["group_id"],
                "group_code": data.groups[account["group_id"]]["code"],
                "group_name": data.groups[account["group_id"]]["name"],
                "nature": data.nature(account),
                "currency": data.currency,
                "opening": fixed(item["opening"]),
                "debit": fixed(item["debit"]),
                "credit": fixed(item["credit"]),
                "closing": fixed(closing),
                "balance_debit": fixed(max(closing, Decimal(0))),
                "balance_credit": fixed(max(-closing, Decimal(0))),
            }
        )
    return result


def profit(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_from and query.date_to
    amounts: dict[str, Decimal] = defaultdict(Decimal)
    for line in data.lines(query):
        if query.date_from <= line["posting_date"] <= query.date_to and not line["opening_effect"]:
            amounts[line["account_id"]] += line["signed"]
    imported: dict[str, Decimal] = defaultdict(Decimal)
    coverage = migration(data.rows)
    if includes_ytd(data.rows, query) and coverage:
        for entry in coverage["ytd_summary"] or []:
            account = data.accounts[entry["account_id"]]
            if not data.selected(account, entry["account_id"], query):
                continue
            if query.basis == "TRANSACTION" and entry["currency"] != query.currency:
                continue
            value = money(entry["base_amount"] if query.basis == "BASE" else entry["amount"])
            imported[entry["account_id"]] += value if entry["side"] == "DEBIT" else -value
        for identity, amount in imported.items():
            amounts[identity] += amount
    rows = []
    income, expense, gross = Decimal(0), Decimal(0), Decimal(0)
    for identity, account in sorted(
        data.accounts.items(), key=lambda pair: (pair[1]["code"], pair[0])
    ):
        nature = data.nature(account)
        if nature not in {"INCOME", "EXPENSE"}:
            continue
        value = -amounts[identity] if nature == "INCOME" else amounts[identity]
        income += value if nature == "INCOME" else Decimal(0)
        expense += value if nature == "EXPENSE" else Decimal(0)
        direct = any(
            data.groups[group]["affects_gross_profit"]
            for group in data.ancestry(account["group_id"])
        )
        if direct:
            gross += value if nature == "INCOME" else -value
        if (
            query.code == "INCOME_EXPENSE"
            and not query.show_zero
            and value == 0
            and imported[identity] == 0
        ):
            continue
        rows.append(
            {
                "row_kind": nature,
                "account_id": identity,
                "account_code": account["code"],
                "account_name": account["name"],
                "group_id": account["group_id"],
                "group_code": data.groups[account["group_id"]]["code"],
                "group_name": data.groups[account["group_id"]]["name"],
                "amount": fixed(value),
                "nature": nature,
                **(
                    {
                        "imported_ytd_amount": fixed(
                            -imported[identity] if nature == "INCOME" else imported[identity]
                        )
                    }
                    if includes_ytd(data.rows, query)
                    else {}
                ),
                "affects_gross_profit": direct,
                "currency": data.currency,
            }
        )
    totals = [("TOTAL_INCOME", income), ("TOTAL_EXPENSE", expense)]
    if query.code == "INCOME_EXPENSE":
        totals.append(("NET_SURPLUS_DEFICIT", income - expense))
    else:
        totals.extend([("GROSS_PROFIT", gross), ("NET_PROFIT", income - expense)])
    rows.extend(
        {"row_kind": key, "amount": fixed(value), "currency": data.currency}
        for key, value in totals
    )
    return rows


def balance_sheet(data: Facts, query: RunRequest) -> list[dict[str, Any]]:
    assert query.date_to
    years = [
        year
        for year in data.rows["fiscal_year"].values()
        if year["start_date"] <= query.date_to.isoformat() <= year["end_date"]
    ]
    if len(years) != 1:
        raise ConflictError(
            "generate the company's financial year before producing its Balance Sheet"
        )
    year_start = dt.date.fromisoformat(years[0]["start_date"])
    rows = []
    sides: dict[str, Decimal] = defaultdict(Decimal)
    for row in balances(data, query):
        nature = row["nature"]
        if nature in {"INCOME", "EXPENSE"}:
            continue
        signed = money(row["closing"])
        value = signed if nature == "ASSET" else -signed
        sides[nature] += value
        rows.append(row | {"amount": fixed(value)})
    earnings: dict[str, Decimal] = defaultdict(Decimal)
    for line in data.lines(query):
        if line["posting_date"] > query.date_to or data.nature(
            data.accounts[line["account_id"]]
        ) not in {"INCOME", "EXPENSE"}:
            continue
        bucket = (
            opening_earnings_bucket(data.rows, year_start)
            if line["opening_effect"]
            else "PRIOR_UNTRANSFERRED_EARNINGS"
            if line["posting_date"] < year_start
            else "CURRENT_YEAR_EARNINGS"
        )
        earnings[bucket] -= line["signed"]
    for bucket in ("OPENING_EARNINGS", "PRIOR_UNTRANSFERRED_EARNINGS", "CURRENT_YEAR_EARNINGS"):
        rows.append(
            {
                "row_kind": bucket,
                "amount": fixed(earnings[bucket]),
                "currency": data.currency,
                "derived": True,
            }
        )
    difference = (
        sides["ASSET"] - sides["LIABILITY"] - sides["EQUITY"] - sum(earnings.values(), Decimal(0))
    )
    if difference:
        raise ConflictError("Balance Sheet does not reconcile with owner journals")
    rows.append(
        {
            "row_kind": "BALANCE_SHEET_CONTROL",
            "assets": fixed(sides["ASSET"]),
            "liabilities": fixed(sides["LIABILITY"]),
            "equity": fixed(sides["EQUITY"]),
            "untransferred_earnings": fixed(sum(earnings.values(), Decimal(0))),
            "difference": fixed(difference),
        }
    )
    return rows


def summarize(
    data: Facts, query: RunRequest, maximum: int = 100000, opening_boundary: dt.date | None = None
) -> list[dict[str, Any]]:
    assert query.date_from and query.date_to
    accounts = {
        identity: data.ancestry(account["group_id"])
        for identity, account in data.accounts.items()
        if data.selected(account, identity, query)
    }
    groups = {group for ancestry in accounts.values() for group in ancestry}
    period_count = (
        (query.date_to - query.date_from).days + 1
        if query.grain == "DAY"
        else (query.date_to.year - query.date_from.year) * 12
        + query.date_to.month
        - query.date_from.month
        + 1
    )
    if period_count * (len(accounts) + len(groups)) > maximum:
        raise ConflictError("financial summary exceeds its configured result bound")
    periods = (
        (
            [
                (query.date_from + dt.timedelta(days=index)).isoformat()
                for index in range(period_count)
            ]
            if query.grain == "DAY"
            else [
                dt.date(month // 12, month % 12 + 1, 1).isoformat()
                for month in range(
                    query.date_from.year * 12 + query.date_from.month - 1,
                    query.date_to.year * 12 + query.date_to.month,
                )
            ]
        )
        if accounts
        else []
    )
    totals: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for account in accounts:
        for period in periods:
            totals[(account, period)]  # Zero turnover still carries an opening/closing balance.
    initial: dict[str, Decimal] = defaultdict(Decimal)
    for line in data.lines(query):
        if line["posting_date"] < query.date_from:
            initial[line["account_id"]] += line["signed"]
            continue
        if line["opening_effect"] and line["posting_date"] == (opening_boundary or query.date_from):
            initial[line["account_id"]] += line["signed"]
            continue
        if not query.date_from <= line["posting_date"] <= query.date_to:
            continue
        day = line["posting_date"] if query.grain == "DAY" else line["posting_date"].replace(day=1)
        totals[(line["account_id"], day.isoformat())][line["side"]] += line["value"]
    rows = [
        {
            "row_kind": "ACCOUNT_PERIOD",
            "account_id": account,
            "account_code": data.accounts[account]["code"],
            "account_name": data.accounts[account]["name"],
            "group_id": data.accounts[account]["group_id"],
            "group_code": data.groups[data.accounts[account]["group_id"]]["code"],
            "group_name": data.groups[data.accounts[account]["group_id"]]["name"],
            "date": day,
            "grain": query.grain,
            "debit": fixed(values["DEBIT"]),
            "credit": fixed(values["CREDIT"]),
            "net": fixed(values["DEBIT"] - values["CREDIT"]),
            "currency": query.currency or data.currency,
        }
        for (account, day), values in sorted(totals.items())
    ]

    group_totals: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for (account, day), values in totals.items():
        for group in data.ancestry(data.accounts[account]["group_id"]):
            group_totals[(group, day)]["DEBIT"] += values["DEBIT"]
            group_totals[(group, day)]["CREDIT"] += values["CREDIT"]
    rows.extend(
        {
            "row_kind": "GROUP_PERIOD",
            "group_id": group,
            "group_code": data.groups[group]["code"],
            "group_name": data.groups[group]["name"],
            "date": day,
            "grain": query.grain,
            "debit": fixed(values["DEBIT"]),
            "credit": fixed(values["CREDIT"]),
            "net": fixed(values["DEBIT"] - values["CREDIT"]),
            "includes_descendants": True,
            "currency": query.currency or data.currency,
        }
        for (group, day), values in sorted(group_totals.items())
    )
    carry: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for account, balance in initial.items():
        carry[("ACCOUNT_PERIOD", account)] = balance
        for group in data.ancestry(data.accounts[account]["group_id"]):
            carry[("GROUP_PERIOD", group)] += balance
    for row in rows:
        key = (str(row["row_kind"]), str(row.get("account_id", row["group_id"])))
        row["opening"] = fixed(carry[key])
        carry[key] += money(row["net"])
        row["closing"] = fixed(carry[key])
    return rows


def calculate(
    facts: list[Fact], query: RunRequest, coverage_start: dt.date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return calculate_data(Facts(facts), query, coverage_start)


def calculate_data(
    data: Facts,
    query: RunRequest,
    coverage_start: dt.date,
    *,
    maximum: int = 100000,
    opening_boundary: dt.date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Same financial rules for a frozen reference or a verified native aggregate input."""
    assert query.date_from and query.date_to
    if query.date_from < coverage_start and not includes_ytd(data.rows, query):
        from reports.domain.reporting.history_coverage import InsufficientHistoryError

        raise InsufficientHistoryError("requested history precedes retained owner coverage")
    if query.basis == "BASE" and query.currency not in {None, data.currency}:
        raise ValidationFailedError("base reporting currency differs from the company")
    for name, table in (
        ("account_id", "account"),
        ("tax_ledger_id", "account"),
        ("group_id", "account_group"),
        ("party_id", "party"),
        ("invoice_id", "invoice_record"),
        ("journal_id", "journal"),
    ):
        selected = getattr(query, name)
        if selected is not None and str(selected) not in data.rows[table]:
            raise ValidationFailedError("report filter is outside the frozen company source")
    with localcontext() as context:
        context.prec = 48
        if query.code in INVOICE_CODES:
            from reports.domain.invoice_registers import register as invoice_register

            rows = invoice_register(data, query)
        elif query.code == "BALANCE_CONTINUITY":
            from reports.domain.balance_continuity import continuity

            rows = continuity(data, query, coverage_start)
        elif query.code == "TRIAL_BALANCE":
            rows = balances(data, query)
            debit = sum((money(row["balance_debit"]) for row in rows), Decimal(0))
            credit = sum((money(row["balance_credit"]) for row in rows), Decimal(0))
            if debit != credit:
                raise ConflictError("trial balance does not reconcile")
            rows.append(
                {
                    "row_kind": "TRIAL_BALANCE_CONTROL",
                    "debit": fixed(debit),
                    "credit": fixed(credit),
                    "difference": "0.0000",
                }
            )
        elif query.code in {"PROFIT_LOSS", "INCOME_EXPENSE"}:
            rows = profit(data, query)
        elif query.code == "BALANCE_SHEET":
            rows = balance_sheet(data, query)
        elif query.code == "ACCOUNT_SUMMARY":
            rows = summarize(data, query, maximum, opening_boundary)
        elif query.code in {
            "OUTSTANDING_BILLS",
            "ADVANCES",
            "AGING",
            "BANK_RECONCILIATION",
            "BANK_RECONCILIATION_EVIDENCE",
            "BANK_RECONCILIATION_WORKLIST",
            "PAYMENT_REGISTER",
            "RECEIPT_REGISTER",
        }:
            from reports.domain.registers import register

            rows = register(data, query)
        else:
            rows = ledger(data, query)
        for row in rows:
            row["period"] = "CURRENT"
        if query.comparative_from and query.comparative_to:
            comparison = query.model_copy(
                update={
                    "date_from": query.comparative_from,
                    "date_to": query.comparative_to,
                    "comparative_from": None,
                    "comparative_to": None,
                }
            )
            comparative, _ = calculate_data(
                data, comparison, coverage_start, maximum=maximum - len(rows)
            )
            rows.extend(row | {"period": "COMPARATIVE"} for row in comparative)
    return rows, calculation_evidence(data, query, coverage_start, rows)


def calculation_evidence(
    data: Facts, query: RunRequest, coverage_start: dt.date, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    from reports.domain.tax_summaries import CODES as TAX_CODES
    from reports.domain.tax_summaries import summarize as tax_summary

    return {
        **({"tax_summary": tax_summary(query.code, rows)} if query.code in TAX_CODES else {}),
        "rule_hash": RULES[query.code],
        "coverage_start": coverage_start.isoformat(),
        "historical_detail_start": coverage_start.isoformat(),
        "migration_coverage": {
            key: value
            for key, value in (migration(data.rows) or {}).items()
            if key != "ytd_summary"
        },
        "imported_ytd_included": includes_ytd(data.rows, query),
        "pre_cutover_monthly_activity_available": False,
        "basis": query.basis,
        "currency": query.currency or data.currency,
        "classification": "FROZEN_GENERATION",
        "earnings_basis": "UNTRANSFERRED_PRIOR_CURRENT_AND_OPENING",
        "accounting_basis": "ACCRUAL",
        "differences": [
            row["difference"]
            for row in rows
            if row["row_kind"] == "BANK_RECONCILIATION_CONTROL" and not row["reconciled"]
        ],
        "row_count": len(rows),
        **(
            {"continuity_basis": "RETAINED_LEDGER_BEFORE_FIRST_MOVEMENT"}
            if query.code == "BALANCE_CONTINUITY"
            else {}
        ),
        **(
            {
                "invoice_coverage": "NATIVE_VOUCHER_INVOICES",
                "date_basis": query.date_basis,
                "credit_basis": "OWNER_COMMITTED_EVENTS",
            }
            if query.code in INVOICE_CODES
            else {}
        ),
    }

"""Two fiscal years, earned profit, unsettled customer bills and carried advances."""

import uuid
from decimal import Decimal

from fixtures import dataset, manifest, source


def financial_dataset():
    base = dataset()
    templates = {row.entity: row.data for row in base}
    rows = [
        row for row in base if row.entity in {"financial_setup", "fiscal_year", "fiscal_period"}
    ]
    ids = {}
    party = uuid.uuid4()
    rows.append(
        source(
            "party",
            party,
            {"code": "BUYER", "name": "Buyer", "party_type": "ORGANISATION", "status": "ACTIVE"},
        )
    )
    for name, nature, kind in (
        ("cash", "ASSET", "CASH"),
        ("equity", "EQUITY", "GENERAL"),
        ("income", "INCOME", "GENERAL"),
        ("expense", "EXPENSE", "GENERAL"),
        ("party", "ASSET", "PARTY"),
    ):
        head, group, account = [uuid.uuid4() for _ in range(3)]
        ids[name] = str(account)
        rows.append(
            source("account_head", head, {"code": name.upper(), "name": name, "nature": nature})
        )
        rows.append(
            source(
                "account_group",
                group,
                templates["account_group"]
                | {
                    "code": name.upper(),
                    "name": name,
                    "head_id": str(head),
                    "affects_gross_profit": name == "income",
                },
            )
        )
        rows.append(
            source(
                "account",
                account,
                templates["account"]
                | {
                    "code": name.upper(),
                    "name": name,
                    "group_id": str(group),
                    "kind": kind,
                    "party_id": str(party) if kind == "PARTY" else None,
                    "party_role": "CUSTOMER" if kind == "PARTY" else None,
                },
            )
        )
    year2, period2 = uuid.uuid4(), uuid.uuid4()
    rows.append(
        source(
            "fiscal_year",
            year2,
            {"code": "2027", "start_date": "2027-04-01", "end_date": "2028-03-31"},
        )
    )
    rows.append(
        source(
            "fiscal_period",
            period2,
            templates["fiscal_period"]
            | {
                "code": "2027-04",
                "fiscal_year_id": str(year2),
                "start_date": "2027-04-01",
                "end_date": "2027-04-30",
            },
        )
    )
    period1 = str(next(row.source_id for row in base if row.entity == "fiscal_period"))
    items = {}
    for code, date, debit, credit, amount, kind in (
        ("opening", "2026-04-01", "cash", "equity", "100", "OPENING"),
        ("invoice", "2026-04-02", "party", "income", "200", "INVOICE"),
        ("receipt", "2026-04-03", "cash", "party", "120", "RECEIPT"),
        ("expense", "2026-04-04", "expense", "cash", "40", "MANUAL"),
        ("receipt2", "2027-04-02", "cash", "party", "30", "RECEIPT"),
    ):
        journal = uuid.uuid4()
        rows.append(
            source(
                "journal",
                journal,
                templates["journal"]
                | {
                    "kind": kind,
                    "document_date": date,
                    "posting_date": date,
                    "total_debit": amount,
                    "total_credit": amount,
                    "source_id": str(journal),
                    "number": code,
                    "fiscal_period_id": period1 if date < "2027-04-01" else str(period2),
                },
            )
        )
        for index, (side, account_name) in enumerate((("DEBIT", debit), ("CREDIT", credit)), 1):
            line = uuid.uuid4()
            rows.append(
                source(
                    "journal_line",
                    line,
                    templates["journal_line"]
                    | {
                        "journal_id": str(journal),
                        "sequence": index,
                        "account_id": ids[account_name],
                        "side": side,
                        "amount": amount,
                        "base_amount": amount,
                        "party_id": str(party) if account_name == "party" else None,
                        "role": "CUSTOMER" if account_name == "party" else None,
                    },
                )
            )
            if account_name == "party":
                item = uuid.uuid4()
                items[code] = str(item)
                rows.append(
                    source(
                        "open_item",
                        item,
                        {
                            "journal_line_id": str(line),
                            "sequence": 1,
                            "account_id": ids["party"],
                            "party_id": str(party),
                            "role": "CUSTOMER",
                            "direction": "DEBT" if side == "DEBIT" else "CREDIT",
                            "reference": code,
                            "currency": "INR",
                            "amount": amount,
                            "base_currency": "INR",
                            "base_amount": amount,
                            "document_date": date,
                            "posting_date": date,
                            "due_date": date,
                            "terms": {"tracking": "NEW_REF" if side == "DEBIT" else "ADVANCE"},
                            "reversal_journal_id": None,
                            "reversal_date": None,
                        },
                    )
                )
    for credit, amount, date in (("receipt", "50", "2026-04-03"), ("receipt2", "30", "2027-04-02")):
        rows.append(
            source(
                "allocation",
                uuid.uuid4(),
                {
                    "debt_item_id": items["invoice"],
                    "credit_item_id": items[credit],
                    "posting_date": date,
                    "currency": "INR",
                    "amount": amount,
                    "base_currency": "INR",
                    "debt_base_amount": amount,
                    "credit_base_amount": amount,
                    "fx_journal_id": None,
                    "reversal_date": None,
                    "fx_reversal_id": None,
                },
            )
        )
    return sorted(rows, key=lambda row: (row.entity, str(row.source_id))), ids


def financial_manifest(rows, **kwargs):
    result = manifest(rows, **kwargs)
    total = sum(
        (
            Decimal(row.data["base_amount"])
            for row in rows
            if row.entity == "journal_line" and row.data["side"] == "DEBIT"
        ),
        Decimal(0),
    )
    return result.model_copy(
        update={
            "control": result.control.model_copy(
                update={"base_totals": {"INR": {"DEBIT": str(total), "CREDIT": str(total)}}}
            )
        }
    )

"""A company with every overview shape.

Eight customers and three suppliers (one of each holding only an advance) across every ageing
bucket, a
ranked and a refunded expense ledger, and cash plus bank movements.

``JOURNALS`` is the single specification: the fact rows are built from it and the tests compute
their expected figures from it, so the expectation never reads the code under test.
"""

import uuid

from fixtures import dataset, source

ACCOUNTS: dict[str, tuple[str, str, str | None]] = {
    "cash": ("ASSET", "CASH", None),
    "bank": ("ASSET", "BANK", None),
    "equity": ("EQUITY", "GENERAL", None),
    "income": ("INCOME", "GENERAL", None),
    **{
        name: ("EXPENSE", "GENERAL", None)
        for name in (
            "Purchases",
            "Rent",
            "Salaries",
            "Utilities",
            "Travel",
            "Software",
            "Repairs",
            "Printing",
            "Refunds",
        )
    },
    **{f"Customer {n}": ("ASSET", "PARTY", "CUSTOMER") for n in range(1, 9)},
    "Supplier 1": ("LIABILITY", "PARTY", "SUPPLIER"),
    "Supplier 2": ("LIABILITY", "PARTY", "SUPPLIER"),
    "Supplier 3": ("LIABILITY", "PARTY", "SUPPLIER"),
    "Customer 2 second ledger": ("ASSET", "PARTY", "CUSTOMER"),
}
# Ledgers that belong to a party another ledger already created (one party, two accounts).
SHARED_PARTY = {"Customer 2 second ledger": "Customer 2"}

# (posting date, kind, debit account, credit account, amount, open item or None)
# An open item is (party account, role, direction, due date). ``DEBT`` is the bill side for
# both roles — a customer invoice and a supplier bill — and ``CREDIT`` the unapplied side.
Item = tuple[str, str, str, str | None]
JOURNALS: list[tuple[str, str, str, str, str, Item | None]] = [
    ("2026-04-01", "OPENING", "cash", "equity", "1000", None),
    # A brought-forward expense: it is a balance, so it is never activity or a top expense.
    ("2026-04-01", "OPENING", "Rent", "equity", "15", None),
    (
        "2026-04-02",
        "INVOICE",
        "Customer 1",
        "income",
        "700",
        ("Customer 1", "CUSTOMER", "DEBT", "2026-07-01"),
    ),
    (
        "2026-04-03",
        "INVOICE",
        "Customer 2",
        "income",
        "600",
        ("Customer 2", "CUSTOMER", "DEBT", "2026-06-05"),
    ),
    (
        "2026-04-04",
        "INVOICE",
        "Customer 3",
        "income",
        "500",
        ("Customer 3", "CUSTOMER", "DEBT", "2026-04-20"),
    ),
    (
        "2026-04-05",
        "INVOICE",
        "Customer 4",
        "income",
        "400",
        ("Customer 4", "CUSTOMER", "DEBT", "2026-04-05"),
    ),
    (
        "2026-04-06",
        "INVOICE",
        "Customer 5",
        "income",
        "300",
        ("Customer 5", "CUSTOMER", "DEBT", "2026-07-15"),
    ),
    (
        "2026-04-07",
        "INVOICE",
        "Customer 6",
        "income",
        "200",
        ("Customer 6", "CUSTOMER", "DEBT", "2026-08-01"),
    ),
    (
        "2026-04-08",
        "INVOICE",
        "Customer 7",
        "income",
        "100",
        ("Customer 7", "CUSTOMER", "DEBT", None),
    ),
    (
        "2026-04-09",
        "RECEIPT",
        "cash",
        "Customer 1",
        "50",
        ("Customer 1", "CUSTOMER", "CREDIT", "2026-04-09"),
    ),
    (
        "2026-04-10",
        "MANUAL",
        "Purchases",
        "Supplier 1",
        "900",
        ("Supplier 1", "SUPPLIER", "DEBT", "2026-07-01"),
    ),
    (
        "2026-04-11",
        "MANUAL",
        "Purchases",
        "Supplier 2",
        "250",
        ("Supplier 2", "SUPPLIER", "DEBT", None),
    ),
    (
        "2026-04-12",
        "MANUAL",
        "Supplier 1",
        "cash",
        "100",
        ("Supplier 1", "SUPPLIER", "CREDIT", "2026-04-12"),
    ),
    ("2026-04-13", "MANUAL", "Rent", "cash", "70", None),
    ("2026-04-14", "MANUAL", "Salaries", "cash", "60", None),
    ("2026-04-15", "MANUAL", "Utilities", "cash", "50", None),
    ("2026-04-16", "MANUAL", "Travel", "cash", "40", None),
    ("2026-04-17", "MANUAL", "Software", "cash", "30", None),
    ("2026-04-18", "MANUAL", "Repairs", "cash", "20", None),
    ("2026-04-19", "MANUAL", "Printing", "cash", "10", None),
    ("2026-04-20", "MANUAL", "cash", "Refunds", "5", None),
    ("2026-04-21", "MANUAL", "bank", "cash", "100", None),
    # Advances with no bill lower the net but the party is owed or owes nothing.
    (
        "2026-04-22",
        "RECEIPT",
        "cash",
        "Customer 8",
        "20",
        ("Customer 8", "CUSTOMER", "CREDIT", "2026-04-22"),
    ),
    # Customer 2's second ledger: one party, so its 150 joins the 600 on the first ledger.
    (
        "2026-04-08",
        "INVOICE",
        "Customer 2 second ledger",
        "income",
        "150",
        ("Customer 2 second ledger", "CUSTOMER", "DEBT", "2026-04-20"),
    ),
    (
        "2026-04-23",
        "MANUAL",
        "Supplier 3",
        "cash",
        "30",
        ("Supplier 3", "SUPPLIER", "CREDIT", "2026-04-23"),
    ),
]


def terms(direction: str, due: str | None) -> dict[str, object]:
    if due is None:  # a bill with no known dates must say so (source verification)
        return {"tracking": "ON_ACCOUNT", "history_unknown": True}
    return {"tracking": "NEW_REF" if direction == "DEBT" else "ADVANCE"}


# Expense returns: Refunds ends with a credit balance, so "other expenses" is negative.
RETURNS: list[tuple[str, str, str, str, str, Item | None]] = [
    ("2026-04-01", "OPENING", "cash", "equity", "1000", None),
    ("2026-04-02", "MANUAL", "Rent", "cash", "100", None),
    ("2026-04-03", "MANUAL", "cash", "Refunds", "300", None),
]


def overview_dataset(journals=JOURNALS):
    base = dataset()
    templates = {row.entity: row.data for row in base}
    rows = [
        row for row in base if row.entity in {"financial_setup", "fiscal_year", "fiscal_period"}
    ]
    period = str(next(row.source_id for row in base if row.entity == "fiscal_period"))
    groups: dict[str, uuid.UUID] = {}
    for nature in ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"):
        head, group = uuid.uuid4(), uuid.uuid4()
        groups[nature] = group
        rows.append(
            source("account_head", head, {"code": nature, "name": nature.title(), "nature": nature})
        )
        rows.append(
            source(
                "account_group",
                group,
                templates["account_group"]
                | {
                    "code": nature,
                    "name": nature.title(),
                    "head_id": str(head),
                    "affects_gross_profit": nature == "INCOME",
                },
            )
        )
    ids: dict[str, str] = {}
    parties: dict[str, str] = {}
    for name, (nature, kind, role) in ACCOUNTS.items():
        account = uuid.uuid4()
        ids[name] = str(account)
        if role and name in SHARED_PARTY:
            parties[name] = parties[SHARED_PARTY[name]]
        elif role:
            party = uuid.uuid4()
            parties[name] = str(party)
            rows.append(
                source(
                    "party",
                    party,
                    {
                        "code": name.upper().replace(" ", "-"),
                        "name": name + " Ltd",
                        "party_type": "ORGANISATION",
                        "status": "ACTIVE",
                    },
                )
            )
        rows.append(
            source(
                "account",
                account,
                templates["account"]
                | {
                    "code": name.upper().replace(" ", "-"),
                    "name": name,
                    "group_id": str(groups[nature]),
                    "kind": kind,
                    "party_id": parties.get(name),
                    "party_role": role,
                },
            )
        )
    for number, (date, kind, debit, credit, amount, item) in enumerate(journals, 1):
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
                    "number": f"J/{number}",
                    "fiscal_period_id": period,
                },
            )
        )
        for sequence, (side, name) in enumerate((("DEBIT", debit), ("CREDIT", credit)), 1):
            line = uuid.uuid4()
            role = ACCOUNTS[name][2]
            rows.append(
                source(
                    "journal_line",
                    line,
                    templates["journal_line"]
                    | {
                        "journal_id": str(journal),
                        "sequence": sequence,
                        "account_id": ids[name],
                        "side": side,
                        "amount": amount,
                        "base_amount": amount,
                        "party_id": parties.get(name),
                        "role": role,
                    },
                )
            )
            if item and item[0] == name:
                _, item_role, direction, due = item
                rows.append(
                    source(
                        "open_item",
                        uuid.uuid4(),
                        {
                            "journal_line_id": str(line),
                            "sequence": 1,
                            "account_id": ids[name],
                            "party_id": parties[name],
                            "role": item_role,
                            "direction": direction,
                            "reference": f"J/{number}",
                            "currency": "INR",
                            "amount": amount,
                            "base_currency": "INR",
                            "base_amount": amount,
                            "document_date": None if due is None else date,
                            "posting_date": date,
                            "due_date": due,
                            "terms": terms(direction, due),
                            "reversal_journal_id": None,
                            "reversal_date": None,
                        },
                    )
                )
    return sorted(rows, key=lambda row: (row.entity, str(row.source_id))), ids

"""Overview position, ageing, ranked parties and ranked expenses over one verified source cut.

Expected figures are computed from ``overview_fixture.JOURNALS`` (and, for ageing, from the
reference engine), never from the code under test.
"""

import datetime as dt
import re
import uuid
from decimal import Decimal
from types import SimpleNamespace

from conftest import COMPANY, PERMISSIONS, headers
from financial_fixture import financial_dataset
from fixtures import dataset
from overview_fixture import ACCOUNTS, JOURNALS, RETURNS, overview_dataset
from sqlalchemy import Column, MetaData, String, Table, case, create_engine, event, insert, select
from test_native_ledger import prepared, request

from reports.domain.statements import calculate
from reports.queries.native_open_items import BUCKETS as BUCKET_NAMES
from reports.queries.native_open_items import bucket_conditions
from reports.tasks.overview import _party_name

BASE = f"/v2/companies/{COMPANY}/overview"
DATE_TO = "2026-07-15"
COVERAGE = dt.date(2026, 4, 1)
BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_over_90", "unknown")


def fixed(value: Decimal | int | str) -> str:
    return format(Decimal(value), ".4f")


async def read(app, client, *, dataset=None, **params):
    identities, facts, ids = await prepared(app, dataset=dataset or overview_dataset())
    response = await client.get(
        BASE,
        params={"generation_id": str(identities[2]), "date_to": DATE_TO, **params},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    return response.json(), facts, ids, identities


def cash_and_bank_positions(first: str, last: str) -> list[dict[str, str]]:
    """Closing cash+bank balance per day, derived straight from the journal specification."""
    held = {"cash", "bank"}
    opening = Decimal(0)
    by_day: dict[str, Decimal] = {}
    for date, _kind, debit, credit, amount, _item in JOURNALS:
        net = (Decimal(amount) if debit in held else 0) - (Decimal(amount) if credit in held else 0)
        if date < first:
            opening += net
        elif date <= last:
            by_day[date] = by_day.get(date, Decimal(0)) + net
    day, end, running, result = (
        dt.date.fromisoformat(first),
        dt.date.fromisoformat(last),
        opening,
        [],
    )
    while day <= end:
        running += by_day.get(day.isoformat(), Decimal(0))
        result.append({"date": day.isoformat(), "cash_and_bank": fixed(running)})
        day += dt.timedelta(days=1)
    return result


def expenses_by_account(first: str, last: str, journals=JOURNALS) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for date, kind, debit, credit, amount, _item in journals:
        if kind == "OPENING" or not first <= date <= last:
            continue
        for name, sign in ((debit, 1), (credit, -1)):
            if ACCOUNTS[name][0] == "EXPENSE":
                result[name] = result.get(name, Decimal(0)) + sign * Decimal(amount)
    return result


def expected_top_expenses(first: str, last: str, journals=JOURNALS):
    amounts = expenses_by_account(first, last, journals)
    ranked = sorted(((v, k) for k, v in amounts.items() if v > 0), key=lambda p: (-p[0], p[1]))[:5]
    other = sum(amounts.values(), Decimal(0)) - sum((v for v, _ in ranked), Decimal(0))
    return (
        [(name, fixed(value)) for value, name in ranked],
        fixed(other),
        fixed(sum(amounts.values())),
    )


async def test_position_is_the_running_cash_and_bank_balance_and_ends_at_the_totals(app, client):
    value, *_ = await read(app, client)
    assert value["position"] == cash_and_bank_positions("2026-04-01", DATE_TO)
    assert len(value["position"]) == len(value["series"]) == 106
    assert [row["date"] for row in value["position"]] == [row["date"] for row in value["series"]]
    # cash 565 + bank 100: the transfer moves money between the two, never out of the position
    assert (value["totals"]["cash"], value["totals"]["bank"]) == ("565.0000", "100.0000")
    assert value["position"][-1]["cash_and_bank"] == "665.0000"
    assert value["position"][0]["cash_and_bank"] == "1000.0000"


async def test_position_starts_from_everything_posted_before_the_selected_range(app, client):
    value, *_ = await read(app, client, date_from="2026-04-13")
    assert value["position"] == cash_and_bank_positions("2026-04-13", DATE_TO)
    # 1000 opening + 50 receipt - 100 supplier advance were all posted before the range
    assert value["position"][0]["cash_and_bank"] == fixed(1000 + 50 - 100 - 70)
    assert value["position"][-1]["cash_and_bank"] == "665.0000"
    assert value["totals"]["income"] == "0.0000"


async def test_ageing_buckets_advances_overdue_and_net_for_both_roles(app, client):
    value, facts, _, identities = await read(app, client)
    receivables, payables = value["receivables"], value["payables"]
    assert receivables["buckets"] == {
        "current": "500.0000",
        "days_1_30": "700.0000",
        "days_31_60": "600.0000",
        "days_61_90": "650.0000",
        "days_over_90": "400.0000",
        "unknown": "100.0000",
    }
    assert {k: receivables[k] for k in ("gross", "advances", "net", "overdue")} == {
        "gross": "2950.0000",
        "advances": "70.0000",
        "net": "2880.0000",
        "overdue": "2350.0000",
    }
    assert payables["buckets"] == {
        "current": "0.0000",
        "days_1_30": "900.0000",
        "days_31_60": "0.0000",
        "days_61_90": "0.0000",
        "days_over_90": "0.0000",
        "unknown": "250.0000",
    }
    assert {k: payables[k] for k in ("gross", "advances", "net", "overdue")} == {
        "gross": "1150.0000",
        "advances": "130.0000",
        "net": "1020.0000",
        "overdue": "900.0000",
    }
    # Existing totals agree, and what the company owes suppliers is a positive payable.
    assert value["totals"]["net_receivable"] == receivables["net"] == "2880.0000"
    assert value["totals"]["net_payable"] == payables["net"] == "1020.0000"
    for part in (receivables, payables):
        assert Decimal(part["gross"]) == sum((Decimal(part["buckets"][k]) for k in BUCKETS), 0)
        assert Decimal(part["gross"]) - Decimal(part["advances"]) == Decimal(part["net"])
        assert Decimal(part["overdue"]) == sum(
            (Decimal(part["buckets"][k]) for k in BUCKETS[1:5]), Decimal(0)
        )
    # The reference AGING engine agrees bucket for bucket.
    rows, _ = calculate(
        facts, request(identities[2], "AGING", date_from="2026-04-01", date_to=DATE_TO), COVERAGE
    )
    reference = {
        role: {
            key: sum((Decimal(row[key]) for row in rows if row["role"] == role), Decimal(0))
            for key in (
                "debt",
                "unapplied_credit",
                "CURRENT",
                "DAYS_1_30",
                "DAYS_31_60",
                "DAYS_61_90",
                "DAYS_OVER_90",
                "UNKNOWN",
            )
        }
        for role in ("CUSTOMER", "SUPPLIER")
    }
    for role, part in (("CUSTOMER", receivables), ("SUPPLIER", payables)):
        assert Decimal(part["gross"]) == reference[role]["debt"]
        assert Decimal(part["advances"]) == reference[role]["unapplied_credit"]
        for bucket, key in zip(
            BUCKETS,
            ("CURRENT", "DAYS_1_30", "DAYS_31_60", "DAYS_61_90", "DAYS_OVER_90", "UNKNOWN"),
            strict=True,
        ):
            assert Decimal(part["buckets"][bucket]) == reference[role][key]


async def test_top_parties_are_ranked_by_net_outstanding_and_bounded_to_five(app, client):
    value, facts, *_ = await read(app, client)
    party_ids = {row.data["name"]: str(row.source_id) for row in facts if row.entity == "party"}
    customers = value["receivables"]["parties"]
    # Customer 2 holds two ledgers (600 and 150): one row with the summed 750, ranked first.
    assert [(row["name"], row["outstanding"], row["overdue"]) for row in customers] == [
        ("Customer 2 Ltd", "750.0000", "750.0000"),
        ("Customer 1 Ltd", "650.0000", "700.0000"),
        ("Customer 3 Ltd", "500.0000", "500.0000"),
        ("Customer 4 Ltd", "400.0000", "400.0000"),
        ("Customer 5 Ltd", "300.0000", "0.0000"),
    ]
    assert len({row["party_id"] for row in customers}) == len(customers)
    # Customer 6 and 7 rank below the fifth; Customer 8 holds only an advance.
    for name in ("Customer 6", "Customer 7", "Customer 8", "Supplier 3"):
        assert name not in str(value)
    suppliers = value["payables"]["parties"]
    assert [(row["name"], row["outstanding"], row["overdue"]) for row in suppliers] == [
        ("Supplier 1 Ltd", "800.0000", "900.0000"),
        ("Supplier 2 Ltd", "250.0000", "0.0000"),
    ]
    # The party id is the party's own identity, not the id of its ledger account.
    assert [row["party_id"] for row in customers + suppliers] == [
        party_ids[name + " Ltd"]
        for name in (
            "Customer 2",
            "Customer 1",
            "Customer 3",
            "Customer 4",
            "Customer 5",
            "Supplier 1",
            "Supplier 2",
        )
    ]


async def test_top_expenses_list_positive_ledgers_and_other_reconciles_to_the_total(app, client):
    value, *_ = await read(app, client)
    top, other, total = expected_top_expenses("2026-04-01", DATE_TO)
    assert [(row["name"], row["amount"]) for row in value["top_expenses"]] == top
    assert top[0] == ("Purchases", "1150.0000") and len(top) == 5
    assert value["other_expenses"] == other == "55.0000"  # 30 + 20 + 10 and a -5 refund
    assert value["totals"]["expenses"] == total == "1425.0000"
    listed = sum((Decimal(row["amount"]) for row in value["top_expenses"]), Decimal(0))
    assert listed + Decimal(value["other_expenses"]) == Decimal(value["totals"]["expenses"])
    assert all(Decimal(row["amount"]) > 0 for row in value["top_expenses"])
    assert "Refunds" not in {row["name"] for row in value["top_expenses"]}


async def test_top_expenses_follow_the_selected_range_and_exclude_opening_effects(app, client):
    value, *_ = await read(app, client, date_from="2026-04-13")
    top, other, total = expected_top_expenses("2026-04-13", DATE_TO)
    assert [(row["name"], row["amount"]) for row in value["top_expenses"]] == top
    assert "Purchases" not in {row["name"] for row in value["top_expenses"]}
    assert value["other_expenses"] == other
    assert value["totals"]["expenses"] == total


def _walk(node):
    if isinstance(node, dict):
        for key, child in node.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk(child)


async def test_every_new_amount_is_an_exact_four_place_decimal_string(app, client):
    value, *_ = await read(app, client)
    amount_keys = {
        "cash_and_bank",
        "gross",
        "advances",
        "net",
        "overdue",
        "outstanding",
        "amount",
        "other_expenses",
        *BUCKETS,
    }
    seen = 0
    for key, child in _walk(value):
        assert not isinstance(child, float), key
        if key in amount_keys and not isinstance(child, dict | list):
            assert isinstance(child, str) and re.fullmatch(r"-?\d+\.\d{4}", child), key
            seen += 1
    assert seen > 100
    assert set(value) >= {"position", "receivables", "payables", "top_expenses", "other_expenses"}


async def test_a_company_with_nothing_posted_reports_zeros_and_empty_lists_not_missing_data(
    app, client
):
    identities, *_ = await prepared(app, dataset=(dataset(), {}))  # one cash-to-cash journal
    response = await client.get(
        BASE,
        params={"generation_id": str(identities[2]), "date_to": "2026-04-05"},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    value = response.json()
    zero = fixed(0)
    for part in (value["receivables"], value["payables"]):
        assert part["parties"] == []
        assert {part[k] for k in ("gross", "advances", "net", "overdue")} == {zero}
        assert set(part["buckets"].values()) == {zero}
    assert value["top_expenses"] == [] and value["other_expenses"] == zero
    assert len(value["position"]) == len(value["series"]) == 5
    assert {row["cash_and_bank"] for row in value["position"]} == {zero}


async def test_partially_settled_bills_and_unapplied_credit_use_the_remaining_balance(app, client):
    value, *_ = await read(app, client, dataset=financial_dataset(), date_to="2026-04-30")
    receivables = value["receivables"]
    # invoice 200 less 50 allocated = 150 owed; receipts 120 + 30 less 50 allocated = 70 unapplied
    assert (receivables["gross"], receivables["advances"], receivables["net"]) == (
        "150.0000",
        "70.0000",
        "80.0000",
    )
    assert receivables["buckets"]["days_1_30"] == "150.0000"
    assert receivables["overdue"] == "150.0000"
    assert [(r["name"], r["outstanding"]) for r in receivables["parties"]] == [("Buyer", "80.0000")]
    assert value["payables"]["net"] == "0.0000"
    assert value["position"][-1]["cash_and_bank"] == "180.0000"
    assert [(r["name"], r["amount"]) for r in value["top_expenses"]] == [("expense", "40.0000")]
    assert value["other_expenses"] == "0.0000"


async def test_new_figures_are_refused_without_party_authority_and_never_leak_names(app, client):
    identities, *_ = await prepared(app, dataset=overview_dataset())
    params = {"generation_id": str(identities[2]), "date_to": DATE_TO}
    for denial in (
        headers(permissions=PERMISSIONS - {"accounting.party.read"}),
        headers(permissions=PERMISSIONS - {"accounting.account.read"}),
        headers(
            policies=[
                {"access": "read", "effect": "deny", "entity": "accounting.party", "field": "name"}
            ]
        ),
    ):
        response = await client.get(BASE, params=params, headers=denial)
        assert response.status_code == 403
        assert "Customer" not in response.text and "Supplier" not in response.text
    other = uuid.uuid4()
    foreign = await client.get(
        f"/v2/companies/{other}/overview", params=params, headers=headers(company=other)
    )
    assert foreign.status_code == 403
    assert (await client.get(BASE, params=params)).status_code == 401
    assert (
        await client.get(BASE, params=params | {"unexpected": "x"}, headers=headers())
    ).status_code == 422


async def test_each_new_aggregate_is_tenant_scoped(app, client):
    identities, _, ids = await prepared(app, dataset=overview_dataset())
    other_tenant = uuid.uuid4()
    other_identities, _, other_ids = await prepared(
        app, tenant=other_tenant, dataset=financial_dataset()
    )
    mine = await client.get(
        BASE, params={"generation_id": str(identities[2]), "date_to": DATE_TO}, headers=headers()
    )
    assert mine.status_code == 200, mine.text
    value = mine.json()
    assert value["receivables"]["net"] == "2880.0000"
    assert value["position"][-1]["cash_and_bank"] == "665.0000"
    assert value["top_expenses"][0]["name"] == "Purchases"
    assert other_ids["party"] not in mine.text
    # The other tenant, same company id, sees only its own dataset's figures.
    theirs = await client.get(
        BASE,
        params={"generation_id": str(other_identities[2]), "date_to": "2026-04-30"},
        headers=headers(tenant=other_tenant),
    )
    assert theirs.status_code == 200, theirs.text
    assert theirs.json()["receivables"]["net"] == "80.0000"
    assert theirs.json()["position"][-1]["cash_and_bank"] == "180.0000"
    assert [row["name"] for row in theirs.json()["receivables"]["parties"]] == ["Buyer"]
    assert [row["name"] for row in theirs.json()["top_expenses"]] == ["expense"]
    assert ids["Customer 1"] not in theirs.text and "Purchases" not in theirs.text


async def test_overview_issues_a_bounded_number_of_aggregate_statements(app, client):
    identities, *_ = await prepared(app, dataset=overview_dataset())
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(" ".join(statement.split()))

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = await client.get(
            BASE,
            params={"generation_id": str(identities[2]), "date_to": DATE_TO},
            headers=headers(),
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    aggregates = [s for s in statements if "SUM(" in s.upper() and "report_" in s]
    # One for cash/bank, one for the daily series, one for ageing, one for expenses and one
    # for the top parties of each role: the previous overview ran three, this adds three.
    assert len(aggregates) <= BASELINE_AGGREGATES + 3, aggregates
    grouped = [s for s in aggregates if "GROUP BY" in s.upper()]
    assert grouped and all("LIMIT" in s.upper() for s in grouped if "ORDER BY" in s.upper())
    for statement in aggregates:
        assert "report_posted_line" not in statement  # never the transaction history


# Statements the overview issued before this change, measured on the unmodified implementation.
BASELINE_AGGREGATES = 6


async def test_net_payable_is_positive_when_the_company_owes_suppliers(app, client):
    """``DEBT`` is the bill side for both roles, so unpaid supplier bills add to payables."""
    value, *_ = await read(app, client)
    assert value["totals"]["net_payable"] == "1020.0000"  # 900 + 250 owed, less 130 of advances
    assert value["totals"]["net_receivable"] == "2880.0000"


async def test_other_expenses_is_the_net_of_everything_outside_the_top_and_may_be_negative(
    app, client
):
    """A ledger with a credit balance (expense returns) is not listed, but it is not lost."""
    value, *_ = await read(app, client, dataset=overview_dataset(RETURNS), date_to="2026-04-30")
    top, other, total = expected_top_expenses("2026-04-01", "2026-04-30", RETURNS)
    assert [(row["name"], row["amount"]) for row in value["top_expenses"]] == top
    assert top == [("Rent", "100.0000")]
    assert value["other_expenses"] == other == "-300.0000"
    assert value["totals"]["expenses"] == total == "-200.0000"
    listed = sum((Decimal(row["amount"]) for row in value["top_expenses"]), Decimal(0))
    assert listed + Decimal(value["other_expenses"]) == Decimal(value["totals"]["expenses"])
    assert re.fullmatch(r"-\d+\.\d{4}", value["other_expenses"])  # not clamped to zero


def test_ageing_bucket_edges_each_land_in_exactly_one_bucket():
    """Pin ``bucket_conditions`` at every boundary, evaluated by a real SQL engine."""
    as_of = dt.date(2026, 7, 15)
    expected = {
        -1: "CURRENT",  # due tomorrow
        0: "CURRENT",  # due on the as-of date
        1: "DAYS_1_30",
        30: "DAYS_1_30",
        31: "DAYS_31_60",
        60: "DAYS_31_60",
        61: "DAYS_61_90",
        90: "DAYS_61_90",
        91: "DAYS_OVER_90",
        400: "DAYS_OVER_90",
        None: "UNKNOWN",
    }
    table = Table("bill", MetaData(), Column("days", String), Column("due_date", String))
    conditions = bucket_conditions(SimpleNamespace(due_date=table.c.due_date), as_of)
    assert len(conditions) == len(BUCKET_NAMES) == 6
    engine = create_engine("sqlite://")
    table.metadata.create_all(engine)
    rows_in = [
        {
            "days": str(days),
            "due_date": None if days is None else (as_of - dt.timedelta(days=days)).isoformat(),
        }
        for days in expected
    ]
    with engine.begin() as connection:
        connection.execute(insert(table), rows_in)
        rows = connection.execute(
            select(table.c.days, *[case((condition, 1), else_=0) for condition in conditions])
        ).all()
    assert len(rows) == len(expected)
    for days, *flags in rows:
        assert sum(flags) == 1, (days, flags)
        wanted = expected[None if days == "None" else int(days)]
        assert flags[BUCKET_NAMES.index(wanted)] == 1, (days, wanted, flags)


def test_a_party_is_named_from_its_fact_and_falls_back_to_a_ledger_name():
    named = SimpleNamespace(data={"name": "Meridian Wholesale"})
    assert _party_name(named, "Debtors") == "Meridian Wholesale"
    for missing in (None, SimpleNamespace(data=None), SimpleNamespace(data={"name": "  "})):
        assert _party_name(missing, "Debtors") == "Debtors"

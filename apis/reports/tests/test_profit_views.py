"""Presentation checks sit on top of the authoritative P&L calculation."""

from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError

from reports.domain.reporting.drilldowns import parameters_for
from reports.domain.reporting.navigation import capabilities
from reports.domain.reporting.profit_views import present
from reports.tasks.report_catalog import catalog


def account(period: str, identity: str, kind: str, amount: str, direct: bool = True) -> dict:
    return {
        "period": period,
        "row_kind": kind,
        "account_id": identity,
        "account_code": identity,
        "account_name": f"Account {identity}",
        "group_id": f"group-{kind}-{direct}",
        "group_code": f"{kind}-{direct}",
        "group_name": f"{kind.title()} group",
        "affects_gross_profit": direct,
        "amount": amount,
        "currency": "INR",
    }


def period(name: str, sales: str, cost: str, other: str, overhead: str) -> list[dict]:
    accounts = [
        account(name, "sales", "INCOME", sales),
        account(name, "cost", "EXPENSE", cost),
        account(name, "other", "INCOME", other, False),
        account(name, "overhead", "EXPENSE", overhead, False),
    ]
    income, expense = Decimal(sales) + Decimal(other), Decimal(cost) + Decimal(overhead)
    gross = Decimal(sales) - Decimal(cost)
    return accounts + [
        {"period": name, "row_kind": kind, "amount": format(value, ".4f"), "currency": "INR"}
        for kind, value in (
            ("TOTAL_INCOME", income),
            ("TOTAL_EXPENSE", expense),
            ("GROSS_PROFIT", gross),
            ("NET_PROFIT", income - expense),
        )
    ]


def test_statement_groups_reconcile_and_hide_zero_accounts() -> None:
    rows, evidence = present(
        period("CURRENT", "100.0000", "30.0000", "5.0000", "0.0000"),
        comparison=False,
        show_zero=False,
    )
    assert [
        row["row_kind"] for row in rows if row["row_kind"] in {"GROSS_PROFIT", "NET_PROFIT"}
    ] == ["GROSS_PROFIT", "NET_PROFIT"]
    assert not any(row.get("account_id") == "overhead" for row in rows)
    assert evidence["totals"]["NET_PROFIT"]["current"] == "75.0000"
    assert evidence["sections"]["DIRECT_EXPENSE"]["current"] == "30.0000"
    assert catalog().resolve("PROFIT_LOSS", 6).definition.views[1].key == "comparison"
    assert catalog().resolve("PROFIT_LOSS", 6).definition.title == "Profit and Loss"
    assert capabilities(catalog().resolve("PROFIT_LOSS", 6).definition)["method"] == "NONE"


def test_comparison_aligns_account_ids_and_undefined_percentage() -> None:
    rows, evidence = present(
        period("CURRENT", "110.0000", "30.0000", "0.0000", "5.0000")
        + period("COMPARATIVE", "100.0000", "20.0000", "0.0000", "0.0000"),
        comparison=True,
        show_zero=False,
    )
    sales = next(row for row in rows if row.get("account_id") == "sales")
    assert (
        sales["amount"],
        sales["previous_amount"],
        sales["change_amount"],
        sales["change_percent"],
    ) == ("110.0000", "100.0000", "10.0000", "10.00%")
    overhead = next(row for row in rows if row.get("account_id") == "overhead")
    assert overhead["change_percent"] is None
    assert evidence["totals"]["NET_PROFIT"]["previous"] == "80.0000"


def test_inconsistent_totals_and_missing_comparison_fail_closed() -> None:
    rows = period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
    rows[-1]["amount"] = "99.0000"
    with pytest.raises(ConflictError):
        present(rows, comparison=False, show_zero=False)
    with pytest.raises(ConflictError):
        present(
            period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000"),
            comparison=True,
            show_zero=False,
        )
    with pytest.raises(ConflictError):
        present(
            period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
            + period("COMPARATIVE", "90.0000", "20.0000", "0.0000", "0.0000"),
            comparison=False,
            show_zero=False,
        )


def test_malformed_source_rows_fail_before_publication() -> None:
    source = period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
    with pytest.raises(ConflictError):
        present(
            [*source, {"period": "CURRENT", "row_kind": "UNKNOWN", "currency": "INR"}],
            comparison=False,
            show_zero=False,
        )
    source[0]["amount"] = "NaN"
    with pytest.raises(ConflictError):
        present(source, comparison=False, show_zero=False)


def test_comparison_rejects_changed_frozen_account_labels() -> None:
    source = period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
    prior = period("COMPARATIVE", "90.0000", "20.0000", "0.0000", "0.0000")
    prior[0]["group_code"] = "DIFFERENT"
    with pytest.raises(ConflictError):
        present(source + prior, comparison=True, show_zero=False)


def test_imported_ytd_is_disclosed_and_available_in_export_rows() -> None:
    source = period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
    source[0]["imported_ytd_amount"] = "40.0000"
    rows, evidence = present(source, comparison=False, show_zero=False)
    sales = next(row for row in rows if row.get("account_id") == "sales")
    assert sales["imported_ytd_amount"] == "40.0000"
    assert evidence["imported_ytd"]["CURRENT"] is True
    assert any(
        column.key == "imported_ytd_amount"
        for column in catalog().resolve("PROFIT_LOSS", 6).definition.views[0].columns
    )


def test_zero_net_account_retains_nonzero_imported_ytd_disclosure() -> None:
    source = period("CURRENT", "0.0000", "0.0000", "0.0000", "0.0000")
    source[0]["imported_ytd_amount"] = "40.0000"
    rows, _ = present(source, comparison=False, show_zero=False)
    assert any(row.get("account_id") == "sales" for row in rows)
    assert any(row["row_kind"] == "GROUP" and row["group_code"] == "INCOME-True" for row in rows)


def test_group_and_account_codes_share_export_column() -> None:
    rows, _ = present(
        period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000"),
        comparison=False,
        show_zero=False,
    )
    group = next(row for row in rows if row["row_kind"] == "GROUP")
    account_row = next(row for row in rows if row["row_kind"] == "ACCOUNT")
    assert group["code"] == group["group_code"]
    assert account_row["code"] == account_row["account_code"]
    assert any(
        column.key == "code"
        for column in catalog().resolve("PROFIT_LOSS", 6).definition.views[0].columns
    )


def test_offsetting_accounts_keep_their_zero_total_group_visible() -> None:
    source = period("CURRENT", "100.0000", "30.0000", "0.0000", "0.0000")
    source.insert(1, account("CURRENT", "refunds", "INCOME", "-100.0000"))
    for row in source:
        if row["row_kind"] in {"TOTAL_INCOME", "GROSS_PROFIT", "NET_PROFIT"}:
            row["amount"] = format(Decimal(row["amount"]) - Decimal("100.0000"), ".4f")
    rows, _ = present(source, comparison=False, show_zero=False)
    assert any(row["row_kind"] == "GROUP" and row["label"] == "Income group" for row in rows)
    assert any(row.get("account_id") == "refunds" for row in rows)


def test_comparison_drilldown_uses_previous_period_and_account_scope() -> None:
    parameters = {
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
    }
    account_id = "01990000-0000-7000-8000-000000000005"
    selected = parameters_for(
        "comparison_account_entries", parameters, {"account_id": account_id}, None
    )
    assert selected == {
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
        "account_id": account_id,
    }
    assert (
        parameters_for("comparison_account_entries", parameters, {"row_kind": "GROUP"}, None)
        is None
    )

"""Independent hierarchy assertions; parents retain gross account-side balances."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError
from financial_fixture import financial_dataset
from fixtures import source

from reports.domain.statements import Facts
from reports.domain.trial_balance import calculate
from reports.schemas.requests import RunRequest


def query(**changes):
    return RunRequest.model_validate(
        {
            "code": "TRIAL_BALANCE",
            "generation_id": str(uuid.uuid4()),
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            **changes,
        }
    )


def test_hierarchy_and_three_controls_use_leaves_once():
    facts, ids = financial_dataset()
    rows, evidence = calculate(Facts(facts), query(), dt.date(2026, 4, 1))
    summary = evidence["trial_balance"]["periods"]["CURRENT"]
    assert summary["account_count"] == 5
    assert summary["opening_debit"] == summary["opening_credit"] == "100.0000"
    assert summary["period_debit"] == summary["period_credit"] == "360.0000"
    assert summary["closing_debit"] == summary["closing_credit"] == "300.0000"
    cash = next(row for row in rows if row.get("account_id") == ids["cash"])
    assert cash["opening_debit"] == "100.0000"
    assert cash["period_debit"] == "120.0000"
    assert cash["period_credit"] == "40.0000"
    assert cash["closing_debit"] == "180.0000"
    assert [row["row_kind"] for row in rows[:3]] == ["HEAD", "GROUP", "ACCOUNT"]
    assert cash["depth"] == 2
    assert all(row["period"] == "CURRENT" for row in rows)
    assert rows[-1]["row_kind"] == "TRIAL_BALANCE_CONTROL"


def test_nested_mixed_side_group_does_not_net_and_keeps_inactive_history():
    facts, ids = financial_dataset()
    data = Facts(facts)
    cash_group = data.accounts[ids["cash"]]["group_id"]
    equity_group = data.accounts[ids["equity"]]["group_id"]
    nested = str(uuid.uuid4())
    data.groups[nested] = data.groups[cash_group] | {"code": "NESTED", "parent_id": cash_group}
    data.accounts[ids["cash"]] = data.accounts[ids["cash"]] | {
        "group_id": nested,
        "status": "INACTIVE",
    }
    data.accounts[ids["equity"]] = data.accounts[ids["equity"]] | {"group_id": nested}
    rows, evidence = calculate(data, query(), dt.date(2026, 4, 1))
    group = next(row for row in rows if row["node_key"] == "group:" + nested)
    assert group["closing_debit"] == "180.0000" and group["closing_credit"] == "100.0000"
    assert group["opening_debit"] == group["opening_credit"] == "100.0000"
    assert group["account_count"] == 2
    assert next(row for row in rows if row.get("account_id") == ids["cash"])["depth"] == 3
    assert evidence["trial_balance"]["periods"]["CURRENT"]["closing_difference"] == "0.0000"
    assert any(row["node_key"] == "group:" + equity_group for row in rows)


@pytest.mark.parametrize("bad", ["cycle", "missing", "cross_head"])
def test_invalid_classification_blocks_a_plausible_hierarchy(bad):
    facts, ids = financial_dataset()
    data = Facts(facts)
    group = data.accounts[ids["cash"]]["group_id"]
    data.groups[group] = data.groups[group] | {
        "parent_id": group
        if bad == "cycle"
        else str(uuid.uuid4())
        if bad == "missing"
        else data.accounts[ids["equity"]]["group_id"]
    }
    with pytest.raises(ConflictError):
        calculate(data, query(), dt.date(2026, 4, 1))


def test_quiet_rows_comparatives_history_and_capacity_are_explicit():
    facts, ids = financial_dataset()
    data = Facts(facts)
    zero = str(uuid.uuid4())
    data.accounts[zero] = data.accounts[ids["cash"]] | {"code": "UNUSED", "name": "Unused"}
    request = query(comparative_from="2027-04-01", comparative_to="2027-04-30")
    rows, evidence = calculate(data, request, dt.date(2026, 4, 1))
    assert set(evidence["trial_balance"]["periods"]) == {"CURRENT", "COMPARATIVE"}
    assert all(row["is_zero"] for row in rows if row.get("account_id") == zero)
    assert not any(row["is_zero"] for row in rows if row.get("account_id") == ids["cash"])
    with pytest.raises(ConflictError, match="capacity"):
        calculate(data, request, dt.date(2026, 4, 1), maximum=1)
    with pytest.raises(ConflictError, match="history"):
        calculate(data, query(date_from="2026-03-01"), dt.date(2026, 4, 1))


def test_opening_or_movement_imbalance_blocks_even_if_closing_balances():
    facts, ids = financial_dataset()
    opening = next(
        row for row in facts if row.entity == "journal" and row.data["kind"] == "OPENING"
    )
    facts = [
        source(row.entity, row.source_id, row.data | {"side": "DEBIT"})
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(opening.source_id)
        and row.data["side"] == "CREDIT"
        else row
        for row in facts
    ]
    with pytest.raises(ConflictError, match="opening"):
        calculate(Facts(facts), query(), dt.date(2026, 4, 1))


def test_amounts_are_exact_decimal_strings_and_every_node_bridge_holds():
    facts, _ = financial_dataset()
    rows, _ = calculate(Facts(facts), query(), dt.date(2026, 4, 1))
    for row in rows:
        amounts = {
            key: Decimal(row[key])
            for key in (
                "opening_debit",
                "opening_credit",
                "period_debit",
                "period_credit",
                "closing_debit",
                "closing_credit",
            )
        }
        assert all(isinstance(row[key], str) for key in amounts)
        assert (
            amounts["opening_debit"]
            - amounts["opening_credit"]
            + amounts["period_debit"]
            - amounts["period_credit"]
            == amounts["closing_debit"] - amounts["closing_credit"]
        )


def test_display_residual_uses_all_accounts_and_preserves_exact_financial_controls():
    from billing_platform.money import RoundingMode

    from reports.domain.trial_balance import AMOUNTS, display_residuals

    facts, _ = financial_dataset()
    rows, evidence = calculate(Facts(facts), query(), dt.date(2026, 4, 1))
    for row in rows:
        for key in AMOUNTS:
            row[key] = format(Decimal(row[key]) * Decimal("0.00002"), ".4f")
    exact = [{key: row[key] for key in AMOUNTS} for row in rows]
    display_residuals(rows, evidence, 2, RoundingMode.HALF_UP)
    assert rows[-1]["closing_debit"] == rows[-1]["closing_credit"] == "0.0060"
    assert rows[-1]["display_residual"]["closing_debit"] == "0.0100"
    assert rows[-1]["display_residual"]["closing_credit"] == "0.0100"
    assert (
        evidence["trial_balance"]["periods"]["CURRENT"]["display_residual"]
        == rows[-1]["display_residual"]
    )
    assert all(not row["display_residual"] for row in rows if row["row_kind"] == "ACCOUNT")
    assert exact == [{key: row[key] for key in AMOUNTS} for row in rows]
    display_residuals(rows, evidence, 4, RoundingMode.HALF_EVEN)
    assert all(not row["display_residual"] for row in rows)

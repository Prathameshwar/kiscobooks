from decimal import Decimal

import pytest

from reports.domain.reconcile import reconcile
from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest
from tools.framework_data import BEGIN, END, facts, identity, manifest


def test_streaming_fixture_is_deterministic_balanced_and_covers_two_years():
    data = list(facts(800))
    repeated = list(facts(800))
    assert data == repeated
    assert data == sorted(data, key=lambda row: (row.entity, str(row.source_id)))
    assert len({(row.entity, row.source_id) for row in data}) == len(data)
    evidence = manifest(800, tenant=identity(20), company=identity(21), snapshot=identity(22))
    lines, _totals, controls = reconcile(data, evidence.control)
    assert len(lines) == 1600
    assert controls["base_totals"]["INR"] == {"DEBIT": "80000.0000", "CREDIT": "80000.0000"}
    rows, _evidence = calculate(
        data,
        RunRequest(
            code="TRIAL_BALANCE",
            generation_id=identity(23),
            date_from=BEGIN,
            date_to=END,
        ),
        BEGIN,
    )
    assert rows[-1]["difference"] == "0.0000"
    assert Decimal(rows[-1]["debit"]) == Decimal("80000")
    assert Decimal(rows[-1]["credit"]) == Decimal("80000")


@pytest.mark.parametrize("count", [0, -1, 10_000_001])
def test_fixture_bounds(count):
    with pytest.raises(ValueError):
        next(facts(count))


@pytest.mark.parametrize("count", [1, 730, 731, 1600])
def test_daily_financial_oracle_matches_full_reference_without_materializing_large_histories(count):
    from tools.framework_query_capacity import financial_oracle

    compact = financial_oracle(count)
    assert len(compact) <= 2223
    for code in (
        "TRIAL_BALANCE",
        "BALANCE_SHEET",
        "PROFIT_LOSS",
        "INCOME_EXPENSE",
        "ACCOUNT_SUMMARY",
    ):
        query = RunRequest(code=code, generation_id=identity(23), date_from=BEGIN, date_to=END)
        assert calculate(compact, query, BEGIN)[0] == calculate(list(facts(count)), query, BEGIN)[0]

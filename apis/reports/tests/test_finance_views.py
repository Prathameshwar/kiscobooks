import pytest

from reports.domain.reporting.finance_views import FINANCE_VIEWS
from reports.tasks.report_catalog import catalog


@pytest.mark.parametrize("code", FINANCE_VIEWS)
def test_finance_business_projection(code):
    definition = catalog().resolve(code).definition
    assert 1 <= len(definition.views) <= 2
    view = definition.views[0]
    assert view.key == "default"
    assert tuple(column.key for column in view.columns) == FINANCE_VIEWS[code][1]
    keys = {column.key for column in view.columns}
    assert len(keys) == len(view.columns)
    for column in view.columns:
        if column.kind == "MONEY":
            assert column.currency_key in keys


def test_party_balance_projection_preserves_readable_account_labels():
    from reports.domain.reporting.views import party_balances

    source = {
        "party_id": "party",
        "account_id": "account",
        "role": "CUSTOMER",
        "report_currency": "INR",
        "direction": "DEBT",
        "report_amount": "2.0000",
        "account_code": "1101",
        "account_name": "Trade customer",
    }
    row = party_balances([source])[0]
    assert row["account_code"] == "1101"
    assert row["account_name"] == "Trade customer"

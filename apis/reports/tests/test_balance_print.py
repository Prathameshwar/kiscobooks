from copy import deepcopy

import pytest
from test_balance_views import period

from reports.domain.reporting.balance_views import present
from reports.rendering.balance_sheet import BalanceSheetWriter
from reports.rendering.tabular import Budget


class Capture:
    def __init__(self):
        self.rows = []
        self.count = 0
        self.finished = False

    def append(self, rows):
        self.rows.extend(rows)
        self.count = len(self.rows)

    def finish(self):
        self.finished = True

    def abort(self):
        self.rows.clear()


def test_print_aligns_grand_totals_and_preserves_source_count():
    rows, _ = present(period(), comparison=False, show_zero=False)
    target = Capture()
    writer = BalanceSheetWriter(target, Budget(100, 1000, 100000, 30))
    writer.append(rows[:3])
    writer.append(rows[3:])
    writer.finish()
    assert writer.count == len(rows)
    assert target.finished
    assert target.rows[-1]["left_amount"] == target.rows[-1]["right_amount"] == "100.0000"
    assert sum("left_label" in r for r in target.rows) + sum(
        "right_label" in r for r in target.rows
    ) == len(rows)


@pytest.mark.parametrize(
    "mutation", ["side", "missing_total", "duplicate_total", "currency", "imbalance"]
)
def test_print_rejects_incomplete_or_misclassified_rows(mutation):
    rows, _ = present(period(), comparison=False, show_zero=False)
    rows = deepcopy(rows)
    if mutation == "side":
        rows[0]["side"] = "UNKNOWN"
    elif mutation == "missing_total":
        rows.pop()
    elif mutation == "duplicate_total":
        rows.append(deepcopy(rows[-1]))
    elif mutation == "currency":
        rows[0]["currency"] = "USD"
    else:
        rows[-1]["amount"] = "99.0000"
    writer = BalanceSheetWriter(Capture(), Budget(100, 1000, 100000, 30))
    with pytest.raises(ValueError):
        writer.append(rows)
        writer.finish()


def test_print_enforces_budget_before_retaining_more_rows():
    rows, _ = present(period(), comparison=False, show_zero=False)
    writer = BalanceSheetWriter(Capture(), Budget(1, 1000, 100000, 30))
    with pytest.raises(ValueError):
        writer.append(rows)
    assert len(writer.rows) == 1

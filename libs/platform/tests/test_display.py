import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from billing_platform.display import DisplayConfiguration, date, number

FIXTURE = json.loads((Path(__file__).parent / "fixtures/report-display.json").read_text("utf-8"))


@pytest.mark.parametrize("case", FIXTURE["cases"])
def test_browser_and_server_share_exact_display_fixtures(case):
    config = DisplayConfiguration(**(FIXTURE["config"] | case.get("config", {})))
    if case["kind"] in {"number", "quantity"}:
        actual = number(case["value"], config, quantity=case["kind"] == "quantity")
    else:
        actual = date(case["value"], config, timestamp=case["kind"] == "datetime")
    assert actual == case["expected"]


@pytest.mark.parametrize("value", [True, 1.5, "NaN", "Infinity", "1e40", "invalid", "1" * 129])
def test_display_rejects_inexact_unbounded_values(value):
    with pytest.raises(ValueError):
        number(value, DisplayConfiguration(**FIXTURE["config"]))


def test_display_calendar_and_precision_contract():
    config = DisplayConfiguration(**(FIXTURE["config"] | {"amount_precision": 0}))
    assert number(Decimal("1.5"), config) == "2"
    assert number(2, config) == "2"
    assert date(dt.date(2026, 3, 5), config) == "05 Mar 2026"
    with pytest.raises(ValueError, match="timezone"):
        date(dt.datetime(2026, 3, 5), config)
    with pytest.raises(ValidationError):
        DisplayConfiguration(**(FIXTURE["config"] | {"amount_precision": 5}))
    with pytest.raises(ValidationError):
        DisplayConfiguration(**(FIXTURE["config"] | {"timezone": "invalid/timezone"}))

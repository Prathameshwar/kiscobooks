"""The same condition vectors are executed by the shared TypeScript renderer."""

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from billing_platform.custom_fields import condition_matches

CASES = json.loads((Path(__file__).parent / "fixtures/custom-field-conditions.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_shared_condition_contract(case: dict[str, Any]) -> None:
    values = dict(case["values"])
    if case["native_type"]:
        key = case["rule"]["field"]
        values[key] = (
            uuid.UUID(values[key])
            if case["native_type"] == "uuid"
            else dt.datetime.fromisoformat(values[key])
        )
    assert (
        condition_matches(case["rule"], values, numeric_fields=frozenset(case["numeric"]))
        is case["expected"]
    )

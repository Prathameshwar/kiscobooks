"""Reject filters whose meaning would otherwise differ from their displayed totals."""

import uuid

import pytest
from pydantic import ValidationError

from reports.schemas.requests import RunRequest


@pytest.mark.parametrize(
    "values",
    [
        {
            "code": "ACCOUNT_LEDGER",
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "currency": "USD",
        },
        {"code": "SOURCE_RECONCILIATION", "account_id": uuid.uuid4()},
        {"code": "SOURCE_RECONCILIATION", "date_to": "2026-04-30"},
    ],
)
def test_unused_filters_cannot_mislabel_complete_source_or_base_currency(values):
    with pytest.raises(ValidationError):
        RunRequest(generation_id=uuid.uuid4(), **values)


@pytest.mark.parametrize(
    "extra",
    [
        {"party_id": uuid.uuid4()},
        {"role": "CUSTOMER"},
        {"group_id": uuid.uuid4()},
    ],
)
def test_bank_reconciliation_cannot_filter_away_bank_movements(extra):
    with pytest.raises(ValidationError, match="complete selected bank ledger"):
        RunRequest(
            generation_id=uuid.uuid4(),
            code="BANK_RECONCILIATION",
            date_from="2026-04-01",
            date_to="2026-04-30",
            account_id=uuid.uuid4(),
            statement_balance="0",
            **extra,
        )

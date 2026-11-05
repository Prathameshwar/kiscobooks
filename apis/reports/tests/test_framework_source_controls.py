"""Negative source/control baselines that optimization must continue to reject."""

import datetime as dt
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from bank_evidence_fixture import evidence_dataset
from billing_platform.errors import ConflictError, ValidationFailedError
from financial_fixture import financial_manifest
from fixtures import source
from test_job_work_deadlines import evidence

from reports.domain.job_work_deadlines import assess
from reports.domain.reconcile import reconcile
from reports.domain.statements import calculate


def edit(facts, entity, changes):
    selected = next(row for row in facts if row.entity == entity)
    return [
        source(row.entity, row.source_id, row.data | changes) if row == selected else row
        for row in facts
    ]


def test_bank_fixture_reconciles_before_adversarial_mutation():
    facts, query, _ids = evidence_dataset()
    reconcile(facts, financial_manifest(facts).control)
    rows, _proof = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[-1]["book_balance"] == "180.0000"
    assert rows[-1]["closing_balance"] == "100"
    worklist = query.model_copy(update={"code": "BANK_RECONCILIATION_WORKLIST", "session_id": None})
    result, _proof = calculate(facts, worklist, dt.date(2026, 4, 1))
    statement = next(row for row in result if row["row_kind"] == "BANK_ACTIVITY")
    assert statement["status"] == "MATCHED"
    assert statement["residual"] == "0.0000"


@pytest.mark.parametrize(
    "entity,changes,pattern",
    [
        ("bank_instrument", {"currency": "USD"}, "instrument differs"),
        ("bank_instrument_event", {"event_date": "2020-01-01"}, "history precedes"),
        ("bank_statement_import", {"period_to": "2026-03-31"}, "valid bank period"),
        ("bank_statement_entry", {"currency": "USD"}, "owner import"),
        ("bank_match_event", {"bank_date": "2026-04-04"}, "evidence boundaries"),
        ("bank_match_event", {"reverses_id": str(uuid.uuid4())}, "reference"),
        ("bank_reconciliation_session", {"period_to": "2026-03-31"}, "invalid account or period"),
    ],
)
def test_invalid_bank_source_relationships_block_activation(entity, changes, pattern):
    facts, _query, _ids = evidence_dataset()
    facts = edit(facts, entity, changes)
    with pytest.raises(ConflictError, match=pattern):
        reconcile(facts, financial_manifest(facts).control)


@pytest.mark.parametrize(
    "entity,changes,pattern",
    [
        ("bank_reconciliation_session", {"status": "DRAFT"}, "selection differs"),
        (
            "bank_reconciliation_session",
            {"snapshot": {"balance_agrees": False}},
            "incomplete owner",
        ),
        ("bank_statement_import", {"status": "DRAFT"}, "absent or uncommitted"),
        ("bank_match_event", {"amount": "101"}, "overmatched"),
        ("bank_reconciliation_session", {"closing_balance": "101"}, "session closing"),
    ],
)
def test_invalid_frozen_bank_controls_block_calculation(entity, changes, pattern):
    facts, query, _ids = evidence_dataset()
    with pytest.raises(ConflictError, match=pattern):
        calculate(edit(facts, entity, changes), query, dt.date(2026, 4, 1))


def test_missing_bank_session_and_changed_control_totals_fail_closed():
    facts, query, _ids = evidence_dataset()
    with pytest.raises(ConflictError, match="session is absent"):
        calculate(
            [row for row in facts if row.entity != "bank_reconciliation_session"],
            query,
            dt.date(2026, 4, 1),
        )
    session = next(row for row in facts if row.entity == "bank_reconciliation_session")
    for key in ("book_balance", "outstanding_book_amount"):
        corrupted = edit(
            facts,
            "bank_reconciliation_session",
            {"snapshot": session.data["snapshot"] | {key: "999.0000"}},
        )
        with pytest.raises(ConflictError, match="do not agree"):
            calculate(corrupted, query, dt.date(2026, 4, 1))
    snapshot = session.data["snapshot"] | {"instrument_ids": [str(uuid.uuid4())]}
    with pytest.raises(ConflictError, match="membership"):
        calculate(
            edit(facts, "bank_reconciliation_session", {"snapshot": snapshot}),
            query,
            dt.date(2026, 4, 1),
        )


@pytest.mark.parametrize(
    "changes,pattern",
    [
        ({"material_category": "INVALID"}, "material category"),
        ({"origin_kind": "INVALID"}, "origin kind"),
        (
            {"remaining_quantity": Decimal(0), "final_clearance_date": dt.date(2020, 1, 1)},
            "observed interval",
        ),
        ({"final_clearance_date": dt.date(2025, 4, 1)}, "unresolved material"),
        ({"material_category": "EXEMPT_TOOL"}, "exempt tools"),
    ],
)
def test_deadline_evidence_cannot_hide_invalid_scope_or_clearance(changes, pattern):
    with pytest.raises(ValidationFailedError, match=pattern):
        assess(replace(evidence(), **changes))

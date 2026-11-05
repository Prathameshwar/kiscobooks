"""Regression coverage for dynamically emitted master and opening audit events."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from accounting.events.audit_contract import AUDIT_EVENTS
from accounting.models.financial_opening import FinancialOpeningChunk, FinancialOpeningEntry
from accounting.tasks.bank_reconciliation import audit as bank_audit
from accounting.tasks.financial_opening import audit as opening_audit

BANK_ACTIONS = {
    "bank_opening_item": ("review",),
    "bank_reconciliation_policy": ("publish",),
    "bank_statement_mapping": ("publish",),
    "bank_statement_import": ("preview", "commit", "reject"),
    "bank_statement_entry": ("duplicate_decision",),
    "bank_match_event": ("match", "unmatch"),
    "bank_adjustment_proposal": ("prepare", "resolved", "rejected"),
    "bank_reconciliation_session": ("draft", "finalize", "amend"),
}


def access():
    return SimpleNamespace(
        actor=SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4()),
        context=SimpleNamespace(company_id=uuid.uuid4(), base_currency="INR"),
    )


@pytest.mark.parametrize(
    "table,action",
    [(table, action) for table, actions in BANK_ACTIONS.items() for action in actions],
)
def test_bank_mutations_are_selected_by_publisher(table, action):
    current, db = access(), MagicMock()
    row = SimpleNamespace(__tablename__=table, id=uuid.uuid4(), status="ACTIVE")
    bank_audit(db, current, row, action)
    event = db.add.call_args.args[0]
    assert event.event_type in AUDIT_EVENTS
    assert event.payload["action"] == event.event_type
    assert event.payload["entity_type"] == "accounting." + table


def test_opening_entry_keeps_exact_money_and_references_without_document_content():
    current, db = access(), MagicMock()
    row = FinancialOpeningEntry(
        id=uuid.uuid4(),
        company_id=current.context.company_id,
        account_id=uuid.uuid4(),
        revision_id=uuid.uuid4(),
        ordinal=1,
        side="DEBIT",
        currency="INR",
        amount=Decimal("900719925474099.1234"),
        base_amount=Decimal("900719925474099.1234"),
        document_count=0,
        source_key="private source label",
        payload={"private": "secret"},
    )
    opening_audit(db, current, row, "create")
    payload = db.add.call_args.args[0].payload
    assert payload["changes"]["amount"] == {"from": None, "to": "900719925474099.1234"}
    assert payload["changes"]["currency"]["to"] == "INR"
    assert payload["changes"]["base_currency"]["to"] == "INR"
    assert payload["changes"]["account_id"]["to"] == str(row.account_id)
    assert payload["actor_type"] == "user"
    assert "private" not in str(payload) and "secret" not in str(payload)


def test_opening_chunk_records_assigned_journal_reference():
    current, db = access(), MagicMock()
    row = FinancialOpeningChunk(
        id=uuid.uuid4(),
        company_id=current.context.company_id,
        batch_id=uuid.uuid4(),
        revision_id=uuid.uuid4(),
        ordinal=1,
        journal_id=uuid.uuid4(),
        payload={},
    )
    opening_audit(db, current, row, "update", before={"journal_id": None})
    assert db.add.call_args.args[0].payload["changes"]["journal_id"] == {
        "from": None,
        "to": str(row.journal_id),
    }

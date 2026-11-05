"""Report lifecycle evidence cannot fall outside the publisher's contract."""

import uuid
from unittest.mock import MagicMock

import pytest

from reports.events.audit_contract import AUDIT_EVENTS
from reports.tasks.common import audit


@pytest.mark.parametrize("event", sorted(AUDIT_EVENTS))
def test_declared_report_activity_preserves_actor_and_source(event):
    db, tenant, company, record = MagicMock(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    action = event.removeprefix("reports.report.")
    audit(db, tenant, company, record, action)
    row = db.add.call_args.args[0]
    assert row.event_type == event and row.payload["action"] == event
    assert row.payload["actor_type"] == "system"
    assert row.payload["source_service"] == "reports"
    assert row.payload["company_id"] == str(company)
    assert row.payload["category"] == ("access" if action == "exported" else "admin")


def test_report_activity_preserves_authenticated_user():
    db, principal = MagicMock(), uuid.uuid4()
    audit(db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "requested", principal)
    assert db.add.call_args.args[0].payload["actor_user_id"] == str(principal)
    assert db.add.call_args.args[0].payload["actor_type"] == "user"


def test_undeclared_report_event_cannot_commit_undeliverable_evidence():
    db = MagicMock()
    with pytest.raises(ValueError, match="undeclared report audit event"):
        audit(db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "unknown_lifecycle")
    db.add.assert_not_called()

import json

from tools.export_audit_contract import document


def test_export_includes_private_execution_events_without_disclosing_command_evidence():
    rows = json.loads(document())
    assert rows["accounting.voucher_execution.record"]["category"] == "system"
    assert rows["accounting.voucher_money_intent.commit"]["category"] == "money"
    assert rows["accounting.voucher_money_intent.cancel"]["category"] == "system"
    assert rows["accounting.voucher_money_intent.commit"]["safe_fields"] == []
    for action in ("snapshot_requested", "snapshot_started", "snapshot_failed"):
        entry = rows[f"accounting.reporting.{action}"]
        assert entry["category"] == "system"
        assert entry["safe_fields"] == []

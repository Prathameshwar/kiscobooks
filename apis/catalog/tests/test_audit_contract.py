"""Publishable routes, stored evidence limits and the checked-in event matrix agree."""

import json
from pathlib import Path

from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.events.audit_policy import SAFE_FIELDS, category, safe_fields


def test_exact_event_matrix_covers_registry() -> None:
    matrix = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts/audit-events.json").read_text()
    )
    assert set(matrix) == AUDIT_EVENTS
    for event, entry in matrix.items():
        entity, action = event.rsplit(".", 1)
        assert len(event) <= 60 and len(entity) <= 80
        assert entry == {
            "entity_type": entity,
            "action": event,
            "category": category(entity, action),
            "safe_fields": sorted(safe_fields(entity)),
        }
    assert not {"name", "code", "description", "custom_fields", "reason", "address"} & SAFE_FIELDS
    assert category("catalog.item_price", "publish") == "money"
    assert category("catalog.tax_rate", "create") == "money"
    assert category("catalog.bulk_job", "export") == "access"
    assert category("catalog.field_rebuild_job", "failed", system=True) == "system"


def test_background_route_categories_match_emitted_work() -> None:
    assert category("catalog.import_job", "cleanup") == "system"
    assert category("catalog.field_rebuild_job", "cleanup") == "system"
    assert category("catalog.field_rebuild_job", "failed") == "system"
    assert category("catalog.field_rebuild_job", "chunk") == "admin"

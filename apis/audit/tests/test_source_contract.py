import uuid

import pytest
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.messages import MessageEnvelope

from audit.domain.source_contract import validate_source


@pytest.mark.parametrize("action", ["update", "accounting.party.update"])
def test_exact_legacy_and_current_accounting_actions(action: str) -> None:
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        occurred_at=utcnow(),
        event_type="accounting.party.update",
        schema_version=1,
        payload={"action": action, "entity_type": "accounting.party"},
    )
    validate_source(envelope, "accounting")
    assert envelope.payload["action"] == action


@pytest.mark.parametrize(
    "issuer,route,entity,action",
    [
        ("catalog", "catalog.item.update", "catalog.item_price", "catalog.item.update"),
        ("catalog", "accounting.party.update", "accounting.party", "accounting.party.update"),
        ("other", "accounting.party.update", "accounting.party", "update"),
        ("accounting", "accounting.party.update", "accounting.account", "update"),
        ("accounting", "accounting.party.update", "accounting.party", "create"),
        ("accounting", "accounting.party.unknown", "accounting.party", "unknown"),
        ("accounting", "accounting.party.update", "accounting.account", "accounting.party.update"),
        (
            "notification",
            "notification.provider_account.updated",
            "notification.notification_delivery",
            "notification.provider_account.updated",
        ),
    ],
)
def test_legacy_exception_does_not_relax_entity_route_or_source(
    issuer: str, route: str, entity: str, action: str
) -> None:
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        occurred_at=utcnow(),
        event_type=route,
        schema_version=1,
        payload={"action": action, "entity_type": entity},
    )
    with pytest.raises(ValidationFailedError):
        validate_source(envelope, issuer)

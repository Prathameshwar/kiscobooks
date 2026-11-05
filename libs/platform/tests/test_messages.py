from __future__ import annotations

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from billing_platform.messages import MessageEnvelope


def test_message_envelope_is_strict_and_requires_aware_time() -> None:
    values = {
        "message_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "event_type": "invoice.posted",
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC),
        "payload": {},
    }
    assert MessageEnvelope.model_validate(values).schema_version == 1
    with pytest.raises(ValidationError):
        MessageEnvelope.model_validate(values | {"occurred_at": dt.datetime.now()})
    with pytest.raises(ValidationError):
        MessageEnvelope.model_validate(values | {"unexpected": True})

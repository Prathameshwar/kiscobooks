"""Service-owned metadata view, excluding platform tables this service does not use.

Importing ``billing_platform.db.platform_models`` registers ``IdempotencyKey`` on the
shared ``Base.metadata`` as a side effect, but ``audit`` mutates no money and has no
idempotency-keyed endpoint — so it owns exactly ``outbox``, ``processed_message`` and
``audit_event``. The migration tests assert the chain reproduces *this* set, not the
shared registry.
"""

from __future__ import annotations

from billing_platform.db.base import NAMING_CONVENTION, Base
from sqlalchemy import MetaData

from audit import models  # noqa: F401  registers the models on Base.metadata

TABLES = frozenset(
    {
        "outbox",
        "processed_message",
        "audit_event",
    }
)


def service_metadata() -> MetaData:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    for name in TABLES:
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata

"""Model registry for `audit`.

Importing this module registers every model on ``Base.metadata`` — the alembic
``env.py`` and the test fixtures both rely on that side effect. The platform-mechanism
tables (``outbox``, ``processed_message``) are real tables in this service's own
database and are re-exported so autogenerate and ``create_all`` include them.
"""

from __future__ import annotations

from billing_platform.db.platform_models import Outbox, ProcessedMessage

from audit.models.audit_event import AuditEvent
from audit.models.integration_log import IntegrationLog

__all__ = [
    "AuditEvent",
    "IntegrationLog",
    "Outbox",
    "ProcessedMessage",
]

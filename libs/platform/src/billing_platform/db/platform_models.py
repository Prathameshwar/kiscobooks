"""Platform-mechanism tables.

Defined here so every service gets an identical shape, but they are **real
tables in each service's own database** and need a migration in that service's
``dbs/<service>/`` tree like anything else.

None of the three is exempt from review just because it is infrastructure:
``processed_message``'s primary key and ``idempotency_key.request_hash`` are
both correctness bugs waiting to happen if got wrong.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import JSON, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow


class Outbox(IdMixin, Base):
    """Transactional outbox: an event and its business change commit atomically.

    Not tenant-filtered, deliberately. ``tenant_id`` is nullable for
    platform-level events, and the poller reads across every tenant by design —
    so this table is on the filter-exemption whitelist and the poller runs
    under ``unfiltered()``.

    Published rows are archived by a retention job, never deleted inline:
    deleting on publish makes a consumer bug undiagnosable and a lost event
    unrepublishable.
    """

    __tablename__ = "outbox"
    __table_args__ = (
        # The poller's only query. Covering both columns keeps it off the table.
        Index("ix_outbox_published_at_available_at", "published_at", "available_at"),
        Index("ix_outbox_aggregate_type_aggregate_id", "aggregate_type", "aggregate_id"),
        UniqueConstraint("message_id", name="uq_outbox_message_id"),
        MARIADB_TABLE_ARGS,
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    available_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessedMessage(Base):
    """Consumer-side dedupe. Redelivery must produce one effect (rule 4.4).

    **The primary key must be composite.** Keyed on ``message_id`` alone, the
    second consumer of a fan-out event silently skips it — a data-loss bug that
    only appears once a second consumer exists.

    No ``tenant_id``: dedupe is infrastructure, and the message may arrive
    before a tenant is resolved. On the filter-exemption whitelist.
    """

    __tablename__ = "processed_message"
    __table_args__ = (
        Index("ix_processed_message_processed_at", "processed_at"),
        MARIADB_TABLE_ARGS,
    )

    consumer_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, primary_key=True)
    processed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)


class IdempotencyKey(IdMixin, TenantMixin, Base):
    """A replayed money-mutating request produces one effect (invariant 2)."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "endpoint",
            "key_value",
            name="uq_idempotency_key_tenant_id_endpoint_key_value",
        ),
        Index("ix_idempotency_key_expires_at", "expires_at"),
        MARIADB_TABLE_ARGS,
    )

    key_value: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    #: SHA-256 of the canonicalized body. Same key with a *different* body is a
    #: client bug and must return 422, never a replay of the first response.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    locked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


#: Shared reason for the local provider's tables: a sign-up exists before any tenant does.
_LOCAL_AUTH = "installation-global local sign-in state (docs/local-auth.md §5)"

#: Tables legitimately outside the session-level tenant filter, with the reason.
#: An **explicit whitelist**, not exemption by omission: a new table without
#: ``TenantMixin`` that is not listed here is a review failure.
#: docs/identity-schema.md §0.3.
TENANT_FILTER_EXEMPT: dict[str, str] = {
    "reference_cache_generation": "Identity-owned global non-personal reference cache generation",
    "reference_revision": "global reference provenance; platform operator or authenticated source only",
    "reference_sync_state": "global service-local reference synchronization checkpoint",
    "reference_change": "Identity-owned immutable global reference source journal",
    "country": "ISO reference data, no tenant_id, natural-code PK",
    "state": "ISO reference data, no tenant_id, natural-code PK",
    "currency": "ISO reference data, no tenant_id, natural-code PK",
    "language": "ISO reference data, no tenant_id, natural-code PK",
    "processed_message": "infrastructure dedupe; message may precede tenant resolution",
    "outbox": "nullable tenant_id for platform events; the poller reads all tenants",
    "local_identity": _LOCAL_AUTH,
    "local_credential": _LOCAL_AUTH,
    "local_recovery_token": _LOCAL_AUTH,
    "local_signing_key": _LOCAL_AUTH,
    "local_authorization": _LOCAL_AUTH,
    "local_refresh_token": _LOCAL_AUTH,
}

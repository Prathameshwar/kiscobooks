"""``impersonation_session`` — a support actor acting as another user, time-bound.

docs/identity-schema.md §4.8. Support access is impersonation, not a cross-tenant read
path (docs/roles-permissions.md §1.6): every session is bounded by ``expires_at`` and
audited at both start and end. **An expired session is refused even when ``ended_at`` is
still null** — the sweeper closes it eventually, but the hard ceiling is enforced on use,
in ``domain/impersonation``.

``actor_user_id`` and ``target_user_id`` carry no foreign key (§4.8 Keys): they are user
references this table does not constrain, resolved before the row is written.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

#: How a session ended. Validated in ``domain``, never a MySQL ``ENUM``.
IMPERSONATION_END_REASONS: Final[frozenset[str]] = frozenset({"manual", "expired", "revoked"})


class ImpersonationSession(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §4.8."""

    __tablename__ = "impersonation_session"
    __table_args__ = (
        Index("ix_impersonation_session_target_user_id_ended_at", "target_user_id", "ended_at"),
        # The sweeper's query — active sessions past their expiry. Cross-cutting, run
        # under ``unfiltered()``, so it leads with neither tenant_id nor a FK column.
        Index("ix_impersonation_session_ended_at_expires_at", "ended_at", "expires_at"),
        MARIADB_TABLE_ARGS,
    )

    #: No FK (§4.8): a user reference, resolved before the row is written.
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    target_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: Mandatory and surfaced to the impersonated tenant — support access is never silent.
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    ticket_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    #: The hard ceiling, enforced on use regardless of ``ended_at``.
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    #: NULL means still open (subject to the expiry check).
    ended_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

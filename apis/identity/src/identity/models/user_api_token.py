"""``user_api_token`` — a personal access token for programmatic API use.

docs/identity-schema.md §4.4. **The raw token is never stored** (CLAUDE.md §5.9): it is
shown once at creation, and the row keeps only ``token_hash`` (SHA-256) for verification
and ``token_prefix`` for display. ``scopes`` may only *narrow* the user's resolved
permissions — a token that widened them would be a privilege-escalation path.

Lifecycle is ``revoked_at`` + ``expires_at`` (rule 4.12), not ``is_active``: revocation
is immediate and dated, and a token is never deleted while any audit row references it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import CHAR, JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserApiToken(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §4.4."""

    __tablename__ = "user_api_token"
    __table_args__ = (
        # Global: login/verification resolves a presented token by its hash alone.
        UniqueConstraint("token_hash", name="uq_user_api_token_token_hash"),
        Index("ix_user_api_token_user_id", "user_id"),
        MARIADB_TABLE_ARGS,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("user.id", name="fk_user_api_token_user_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: First characters, shown in the UI so a user can tell their tokens apart.
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    #: SHA-256 of the raw token. The raw value is shown once and never persisted.
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    #: Narrowing only — never widens the user's resolved permissions.
    scopes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Written asynchronously, never on the auth path (a write per request is a hot row).
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: No FK (a ``_by`` column, §1.5).
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)

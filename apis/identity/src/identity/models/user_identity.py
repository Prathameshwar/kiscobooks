"""``user_identity`` — additional IdP links for one user.

docs/identity-schema.md §4.2. ``user.authentik_sub`` is the primary link; this table
is how the same person signs in through Google or Microsoft as well without a second
``user`` row and a second set of role assignments.

It stores a **subject, never a credential**: no token, no refresh token, no secret.
The subject is a public identifier at the provider, so a leak of this table does not
authenticate anybody. Anything issued *by* us belongs in ``user_api_token`` (§4.4)
and is stored hashed.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

#: docs/identity-schema.md §4.2. Extended by adding a provider here and configuring
#: it in Authentik — never by accepting whatever string a client sends, which would
#: let a caller invent a provider namespace and collide with a real one.
IDENTITY_PROVIDERS: Final[frozenset[str]] = frozenset({"authentik", "google", "microsoft"})


class UserIdentity(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §4.2."""

    __tablename__ = "user_identity"
    __table_args__ = (
        # Global and NOT NULL — the security-critical constraint here. Login arrives
        # as `(provider, provider_sub)` and resolves to a user, so two rows sharing a
        # pair would make one person's login resolve to either of two accounts,
        # across tenants. Per-tenant uniqueness would permit exactly that.
        UniqueConstraint("provider", "provider_sub", name="uq_user_identity_provider_provider_sub"),
        Index("ix_user_identity_user_id", "user_id"),
        MARIADB_TABLE_ARGS,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("user.id", name="fk_user_identity_user_id"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    #: 255 because a provider's subject is opaque and some are long. Compared whole,
    #: never prefixed or truncated: a truncated subject could match another user's.
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    #: A mirror of the provider's state, for display and dormant-account review.
    #: Never read as an authorization input — a stale value here must not extend or
    #: curtail access.
    last_login_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)

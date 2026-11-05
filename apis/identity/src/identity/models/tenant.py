"""``tenant`` — the root isolation and subscription boundary.

The paying customer. Everything else in the platform is scoped to one of these
rows, which is why this table is the one place where getting the isolation
mechanism wrong is unrecoverable rather than merely a bug.

**It carries no ``tenant_id``; it *is* the tenant.** ``SelfTenantMixin`` puts it
inside the session-level filter anyway, matched on ``id`` — see that mixin for
why route-level checks were not considered sufficient here. Provisioning a tenant
and any platform-admin listing therefore run under ``unfiltered()``.

Lifecycle is ``status``, not ``is_active`` (rule 4.12): a tenant is ``active``,
``suspended`` or ``closed``, and suspension is not the same thing as
deactivation — a suspended tenant still logs in to see why. The two mechanisms
are never combined.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, SelfTenantMixin, StatusMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import CHAR, Date, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

#: The lifecycle values, validated in ``domain/`` rather than by a MySQL ``ENUM``
#: (CLAUDE.md §4 — altering an ENUM rebuilds the table).
TENANT_STATUSES: frozenset[str] = frozenset({"active", "suspended", "closed"})


class Tenant(SelfTenantMixin, StatusMixin, AuditMixin, Base):
    """docs/identity-schema.md §3.1."""

    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        # Both declared explicitly. InnoDB creates an index to support a foreign
        # key when none exists, names it after the constraint, and that invisible
        # index then reads as autogenerate drift on every later revision.
        Index("ix_tenant_default_country_code", "default_country_code"),
        Index("ix_tenant_default_country_state", "default_country_code", "default_state_code"),
        ForeignKeyConstraint(
            ["default_country_code", "default_state_code"],
            ["state.country_code", "state.code"],
            name="fk_tenant_default_country_state",
        ),
        Index("ix_tenant_default_currency_code", "default_currency_code"),
        Index("ix_tenant_name_id", "name", "id"),
        Index("ix_tenant_status_name_id", "status", "name", "id"),
        Index("ix_tenant_created_id", "created_at", "id"),
        Index("ix_tenant_status_created_id", "status", "created_at", "id"),
        Index("ix_tenant_status_slug_id", "status", "slug", "id"),
        MARIADB_TABLE_ARGS,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Immutable after creation. It appears in URLs, webhook targets and saved
    #: bookmarks, so a rename silently breaks integrations — enforced in
    #: ``domain/`` for every actor, not as a permission.
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    #: No foreign key: ``plan`` is deferred pending the open question of whether we
    #: bill our own tenants here (docs/identity-schema.md §3.2). Nullable until it
    #: exists; the FK is added with the table, in its own revision.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    primary_contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    #: Pre-selects on company creation only. The company's own values are what
    #: post, and they are immutable once anything has posted (invariant 16) — so a
    #: later change here never reaches a document.
    default_country_code: Mapped[str] = mapped_column(
        CHAR(2), ForeignKey("country.code", name="fk_tenant_default_country_code"), nullable=False
    )
    default_currency_code: Mapped[str] = mapped_column(
        CHAR(3), ForeignKey("currency.code", name="fk_tenant_default_currency_code"), nullable=False
    )
    default_state_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    #: BCP-47. Feeds the resolved display config, never read from client headers
    #: (docs/identity-schema.md §0.4).
    default_locale: Mapped[str] = mapped_column(String(8), nullable=False)
    #: IANA name — ``Asia/Kolkata``. Never a UTC offset, which is wrong twice a
    #: year wherever DST applies.
    default_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_ends_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    suspended_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: Shown to tenant admins, so it is written for them to read. No internal
    #: identifiers and no PII beyond the actor reference the audit row holds.
    suspended_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

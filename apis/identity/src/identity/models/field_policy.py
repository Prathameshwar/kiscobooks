"""``field_policy`` — field-level allow/deny layered on role permissions.

docs/identity-schema.md §5.4, docs/field-permissions.md. Mastered here and replicated
read-only to every service. It **narrows, never widens** (default allow), and it is
*access control*, distinct from ``field_config`` (form layout). Resolution lives in
``domain/field_policy``.

``scope_id`` is NOT NULL and stores ``SCOPE_ALL`` at tenant scope (db-plan §2); the API
speaks ``null``. ``subject_id`` and ``scope_id`` carry no FK — each is polymorphic
(``subject_type`` decides user vs group vs role; ``scope_id`` names a company/department
or the sentinel).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

FIELD_POLICY_SUBJECT_TYPES: Final[frozenset[str]] = frozenset({"role", "user_group", "user"})
FIELD_ACCESS: Final[frozenset[str]] = frozenset({"read", "write"})
FIELD_EFFECTS: Final[frozenset[str]] = frozenset({"deny", "allow"})


class FieldPolicy(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §5.4."""

    __tablename__ = "field_policy"
    __table_args__ = (
        # Full name would exceed 64 chars; shortened by dropping the `_type`/`_id`
        # detail, asserted by a test (§1.3).
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "entity_type",
            "field_key",
            "access",
            "scope_type",
            "scope_id",
            name="uq_field_policy_subject_entity_field_access_scope",
        ),
        Index("ix_field_policy_tenant_id_subject", "tenant_id", "subject_type", "subject_id"),
        MARIADB_TABLE_ARGS,
    )

    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    #: No FK — polymorphic (``subject_type`` decides the target table).
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: `[CODE]` — e.g. ``billing.invoice``. Registered field owner, not a table.
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    #: A registered native field, or ``custom_field:<key>``.
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    access: Mapped[str] = mapped_column(String(10), nullable=False)
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False)
    #: ``SCOPE_ALL`` at tenant scope; no FK (polymorphic company/department).
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: Optional rule tree — evaluated per record, so kept rare.
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Surfaced in the 403 and the audit event.
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

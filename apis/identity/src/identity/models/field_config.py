"""``field_config`` — per-tenant/company form layout for native and custom fields.

docs/identity-schema.md §6.2. **Layout, not authorization** (that is ``field_policy``): it
shows/hides/reorders/relabels and may only *tighten* requiredness. A ``null`` on any
override column means "inherit". ``company_id`` is NOT NULL and stores ``SCOPE_ALL`` for a
tenant-wide config (db-plan §2); launch config is tenant-only (build decision), the column
supports company overrides later without a migration.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class FieldConfig(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §6.2."""

    __tablename__ = "field_config"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            name="uq_field_config_scope_entity_field",
        ),
        Index("ix_field_config_tenant_id_entity_type", "tenant_id", "entity_type"),
        # FK-supporting index leading with the FK column (§1.7 first exception).
        Index("ix_field_config_definition_id", "definition_id"),
        MARIADB_TABLE_ARGS,
    )

    #: ``SCOPE_ALL`` = tenant-wide; no FK (the sentinel names no row).
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    #: ``native`` (a registry key) or ``custom`` (a definition key).
    field_source: Mapped[str] = mapped_column(String(10), nullable=False)
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Non-null iff ``field_source = 'custom'``. FK — the definition is a real row.
    definition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey("custom_field_definition.id", name="fk_field_config_definition_id"),
        nullable=True,
    )
    is_visible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    display_order: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    display_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    label_override: Mapped[str | None] = mapped_column(String(150), nullable=True)
    help_text_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(500), nullable=True)

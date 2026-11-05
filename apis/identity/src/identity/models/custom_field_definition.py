"""``custom_field_definition`` — a runtime-configurable field on an entity.

docs/identity-schema.md §6.1, docs/custom-fields.md. *Types and entities are code; fields
are data.* ``identity`` is master and publishes ``custom_field_definition.changed``; every
service holds a read-only replica for its own entity types.

``key`` is **immutable after create** (it is how values are stored). ``company_id`` is NOT
NULL and stores ``SCOPE_ALL`` for a tenant-wide definition (db-plan §2). ``option_source_key``
is a security boundary — a code-registered resolver key, never a URL or query
(docs/custom-fields.md §7). **No domain logic ever reads a custom field's value**
(CLAUDE.md invariant 14).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, Boolean, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

#: The code catalogue of value types. A genuinely new type needs code (a validator and a
#: coercer), never a runtime addition (docs/custom-fields.md).
CUSTOM_FIELD_DATA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "text",
        "long_text",
        "integer",
        "decimal",
        "date",
        "datetime",
        "boolean",
        "currency_amount",
        "select",
        "multi_select",
        "dynamic_select",
        "auto_number",
    }
)


class CustomFieldDefinition(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §6.1."""

    __tablename__ = "custom_field_definition"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "entity_type", "key", name="uq_custom_field_def_scope_key"
        ),
        # The resolution query: definitions for an entity type in a company, active ones.
        Index("ix_custom_field_def_tenant_entity_active", "tenant_id", "entity_type", "is_active"),
        MARIADB_TABLE_ARGS,
    )

    #: ``SCOPE_ALL`` = every company in the tenant; no FK (the sentinel names no row).
    requires_adoption: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Immutable after create — values are keyed by it.
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    help_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    data_type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    display_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_immutable_after_create: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_feature: Mapped[str | None] = mapped_column(String(60), nullable=True)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: A registered resolver key — never a URL or query (the feature's security boundary).
    option_source_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    depends_on_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    visibility: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sequence_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(500), nullable=True)

"""``custom_field_value_index`` — the searchable projection of custom-field values.

docs/identity-schema.md §6.3, docs/custom-fields.md. MariaDB JSON is not natively
indexable, so a searchable custom field's value is dual-written: into the entity's
``custom_fields`` JSON (for display, no join) and into a typed row here (for filter, sort
and uniqueness). Written in the entity's own transaction, only for ``is_searchable``
definitions. Derived data — **no ``id`` and no audit columns**; the natural key
``(entity_type, entity_id, definition_id)`` is the primary key.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import TenantMixin
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import Mapped, mapped_column


class CustomFieldValueIndex(TenantMixin, Base):
    """docs/identity-schema.md §6.3."""

    __tablename__ = "custom_field_value_index"
    __table_args__ = (
        # Value-lookup indexes: given a definition, find rows by value. These are the
        # search/filter path, so they lead with `definition_id`, not `tenant_id`.
        Index("ix_cfvi_definition_id_value_text", "definition_id", "value_text"),
        Index("ix_cfvi_definition_id_value_number", "definition_id", "value_number"),
        Index("ix_cfvi_definition_id_value_date", "definition_id", "value_date"),
        MARIADB_TABLE_ARGS,
    )

    entity_type: Mapped[str] = mapped_column(String(80), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, primary_key=True)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    value_text: Mapped[str | None] = mapped_column(
        String(255).with_variant(VARCHAR(255, collation="utf8mb4_bin"), "mysql", "mariadb"),
        nullable=True,
    )
    #: DECIMAL(19,4) via the platform ``Money`` type — the fixed storage scale for every
    #: amount and quantity (CLAUDE.md §4), applied to numeric custom values too.
    value_number: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    #: Holds both ``date`` and ``datetime`` custom values as a datetime (schema §6.3).
    value_date: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

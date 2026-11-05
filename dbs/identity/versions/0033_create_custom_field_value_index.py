"""create custom_field_value_index

Revision ID: 0033
Revises: 0032

The searchable projection of custom-field values (docs/identity-schema.md §6.3). MariaDB
JSON is not natively indexable, so a searchable value is dual-written here as a typed row.
**Natural-key PK** ``(entity_type, entity_id, definition_id)`` — no surrogate id and no
audit columns (derived data). ``value_date`` is ``DATETIME(6)`` and holds both ``date`` and
``datetime`` custom values: it is a polymorphic *value* column, not a business date or a
timestamp, so the ``_date``→DATE / DATETIME→``_at`` naming convention does not apply — the
convention test exempts this table.

PK key length: 80*4 + 16 + 16 = 352 bytes, under the 3072 DYNAMIC limit (§1.6).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT (``value_number`` is DECIMAL(19,4)) · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE custom_field_value_index (
    tenant_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    value_text VARCHAR(255) NULL,
    value_number DECIMAL(19,4) NULL,
    value_date DATETIME(6) NULL,
    value_bool TINYINT(1) NULL,
    CONSTRAINT pk_custom_field_value_index PRIMARY KEY (entity_type, entity_id, definition_id),
    KEY ix_custom_field_value_index_tenant_id (tenant_id),
    KEY ix_cfvi_definition_id_value_text (definition_id, value_text),
    KEY ix_cfvi_definition_id_value_number (definition_id, value_number),
    KEY ix_cfvi_definition_id_value_date (definition_id, value_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_value_index")

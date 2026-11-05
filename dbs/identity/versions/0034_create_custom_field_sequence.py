"""create custom_field_sequence

Revision ID: 0034
Revises: 0033

Allocation state for ``auto_number`` custom fields (docs/identity-schema.md §6.4).
Allocated via ``SELECT … FOR UPDATE`` in the entity's transaction; **not gap-free** (a
rolled-back create consumes a number — gap-free statutory numbering is ``document_sequence``
in ``billing``). ``definition_id``/``company_id`` carry no FK (allocation state).

This is the final revision of the identity chain (34 of 34).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT (``BIGINT`` is an integer) · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE custom_field_sequence (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    cycle_key VARCHAR(40) NOT NULL,
    next_value BIGINT NOT NULL,
    CONSTRAINT pk_custom_field_sequence PRIMARY KEY (id),
    CONSTRAINT uq_custom_field_sequence_def_company_cycle
        UNIQUE (definition_id, company_id, cycle_key),
    KEY ix_custom_field_sequence_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_sequence")

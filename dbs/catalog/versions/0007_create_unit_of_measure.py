"""Catalog unit_of_measure: frozen single-DDL migration paired with its model."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE unit_of_measure (
    company_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    dimension VARCHAR(20) NOT NULL,
    decimal_places INTEGER NOT NULL,
    quantity_increment NUMERIC(19,4) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT pk_unit_of_measure PRIMARY KEY (id),
    CONSTRAINT uq_unit_of_measure_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT ck_unit_of_measure_unit_precision
        CHECK (decimal_places >= 0 AND decimal_places <= 4),
    CONSTRAINT uq_unit_of_measure_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_unit_of_measure_unit_increment CHECK (quantity_increment > 0),
    CONSTRAINT ck_unit_of_measure_unit_row_version CHECK (row_version > 0),
    KEY ix_unit_of_measure_scope_dimension_code (tenant_id, company_id, dimension, code, id),
    KEY ix_unit_of_measure_scope_name_id (tenant_id, company_id, name, id),
    KEY ix_unit_of_measure_tenant_id (tenant_id)
) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE unit_of_measure")

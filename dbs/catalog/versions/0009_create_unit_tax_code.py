"""Catalog unit_tax_code: frozen single-DDL migration paired with its model."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE unit_tax_code (
    company_id BINARY(16) NOT NULL,
    unit_id BINARY(16) NOT NULL,
    jurisdiction VARCHAR(30) NOT NULL,
    official_code VARCHAR(30) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_unit_tax_code PRIMARY KEY (id),
    CONSTRAINT ck_unit_tax_code_unit_tax_code_dates
        CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT fk_unit_tax_code_unit
        FOREIGN KEY(tenant_id, company_id, unit_id)
        REFERENCES unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT uq_unit_tax_code_start
        UNIQUE (tenant_id, company_id, unit_id, jurisdiction, valid_from),
    KEY ix_unit_tax_code_tenant_id (tenant_id)
) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE unit_tax_code")

"""Catalog unit_conversion: frozen single-DDL migration paired with its model."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE unit_conversion (
    company_id BINARY(16) NOT NULL,
    from_unit_id BINARY(16) NOT NULL,
    canonical_unit_id BINARY(16) NOT NULL,
    numerator BIGINT NOT NULL,
    denominator BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_unit_conversion PRIMARY KEY (id),
    CONSTRAINT fk_unit_conversion_source
        FOREIGN KEY(tenant_id, company_id, from_unit_id)
        REFERENCES unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT ck_unit_conversion_unit_conversion_positive
        CHECK (numerator > 0 AND denominator > 0),
    CONSTRAINT uq_unit_conversion_source UNIQUE (tenant_id, company_id, from_unit_id),
    CONSTRAINT fk_unit_conversion_canonical
        FOREIGN KEY(tenant_id, company_id, canonical_unit_id)
        REFERENCES unit_of_measure (tenant_id, company_id, id),
    KEY ix_unit_conversion_canonical (tenant_id, company_id, canonical_unit_id),
    KEY ix_unit_conversion_tenant_id (tenant_id)
) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE unit_conversion")

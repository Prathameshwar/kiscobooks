"""Create brand_manufacturer; one atomic DDL, with a paired model."""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE brand_manufacturer (
    company_id BINARY(16) NOT NULL,
    brand_id BINARY(16) NOT NULL,
    manufacturer_id BINARY(16) NOT NULL,
    production_role VARCHAR(30) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_brand_manufacturer_brand_manufacturer_dates CHECK (valid_from >= '1000-01-01' AND
        (valid_to IS NULL OR valid_to >= valid_from)),
    CONSTRAINT ck_brand_manufacturer_brand_manufacturer_role CHECK (production_role IN ('OEM',
        'CONTRACT_MANUFACTURER', 'ASSEMBLER')),
    CONSTRAINT ck_brand_manufacturer_brand_manufacturer_version CHECK (row_version >= 1),
    CONSTRAINT fk_brand_manufacturer_brand FOREIGN KEY(tenant_id, company_id, brand_id) REFERENCES
        brand (tenant_id, company_id, id),
    CONSTRAINT fk_brand_manufacturer_manufacturer FOREIGN KEY(tenant_id, company_id,
        manufacturer_id) REFERENCES manufacturer (tenant_id, company_id, id),
    CONSTRAINT pk_brand_manufacturer PRIMARY KEY (id),
    CONSTRAINT uq_brand_manufacturer_start UNIQUE (tenant_id, company_id, brand_id, manufacturer_id,
        production_role, valid_from),
    KEY ix_brand_manufacturer_company (tenant_id, company_id, valid_from, id),
    KEY ix_brand_manufacturer_source (tenant_id, company_id, manufacturer_id, id),
    KEY ix_brand_manufacturer_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE brand_manufacturer")

"""Create product_family; one atomic DDL paired with its native model."""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_family (
    company_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    kind VARCHAR(10) NOT NULL,
    structure_mode VARCHAR(10) NOT NULL,
    product_type_revision_id BINARY(16) NOT NULL,
    brand_id BINARY(16) NULL,
    series_id BINARY(16) NULL,
    model_code VARCHAR(100) NULL,
    description VARCHAR(2000) NULL,
    status VARCHAR(20) NOT NULL,
    row_version INTEGER NOT NULL,
    custom_fields JSON NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_family PRIMARY KEY (id),
    CONSTRAINT uq_product_family_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_product_family_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT fk_product_family_type FOREIGN KEY(tenant_id, company_id, product_type_revision_id) REFERENCES product_type_revision (tenant_id, company_id, id),
    CONSTRAINT fk_product_family_brand FOREIGN KEY(tenant_id, company_id, brand_id) REFERENCES brand (tenant_id, company_id, id),
    CONSTRAINT fk_product_family_series FOREIGN KEY(tenant_id, company_id, brand_id, series_id) REFERENCES brand_series (tenant_id, company_id, brand_id, id),
    CONSTRAINT ck_product_family_product_family_kind CHECK (kind IN ('GOODS', 'SERVICE')),
    CONSTRAINT ck_product_family_product_family_structure CHECK (structure_mode IN ('SIMPLE', 'VARIANT')),
    CONSTRAINT ck_product_family_product_family_status CHECK (status IN ('DRAFT', 'ACTIVE', 'DISCONTINUED')),
    CONSTRAINT ck_product_family_product_family_series_brand CHECK (series_id IS NULL OR brand_id IS NOT NULL),
    CONSTRAINT ck_product_family_product_family_version CHECK (row_version >= 1),
    KEY ix_product_family_brand (tenant_id, company_id, brand_id, series_id),
    KEY ix_product_family_kind (tenant_id, company_id, kind, code, id),
    KEY ix_product_family_name (tenant_id, company_id, name, id),
    KEY ix_product_family_tenant_id (tenant_id),
    KEY ix_product_family_type (tenant_id, company_id, product_type_revision_id, id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_family")

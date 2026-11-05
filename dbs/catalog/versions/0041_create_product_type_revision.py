"""Create product_type_revision; one atomic DDL, with a paired model."""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_type_revision (
    company_id BINARY(16) NOT NULL,
    product_type_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    kind VARCHAR(10) NOT NULL,
    inventory_modes JSON NOT NULL,
    tracking_modes JSON NOT NULL,
    unit_dimensions JSON NOT NULL,
    allow_variants BOOL NOT NULL,
    require_brand BOOL NOT NULL,
    require_manufacturer BOOL NOT NULL,
    require_expiry BOOL NOT NULL,
    published_at DATETIME(6) NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_product_type_revision_product_type_revision_flags CHECK (allow_variants IN (0,1)
        AND require_brand IN (0,1) AND require_manufacturer IN (0,1) AND require_expiry IN (0,1)),
    CONSTRAINT ck_product_type_revision_product_type_revision_kind CHECK (kind IN ('GOODS',
        'SERVICE', 'BOTH')),
    CONSTRAINT ck_product_type_revision_product_type_revision_version CHECK (revision >= 1 AND
        row_version >= 1),
    CONSTRAINT fk_product_type_revision_type FOREIGN KEY(tenant_id, company_id, product_type_id)
        REFERENCES product_type (tenant_id, company_id, id),
    CONSTRAINT pk_product_type_revision PRIMARY KEY (id),
    CONSTRAINT uq_product_type_revision_number UNIQUE (tenant_id, company_id, product_type_id,
        revision),
    CONSTRAINT uq_product_type_revision_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_product_type_revision_published (tenant_id, company_id, product_type_id, published_at,
        revision, id),
    KEY ix_product_type_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_type_revision")

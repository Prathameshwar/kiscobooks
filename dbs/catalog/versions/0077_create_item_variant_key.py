"""Create item_variant_key; one reversible DDL."""
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_variant_key (
    family_id BINARY(16) NOT NULL,
    item_id BINARY(16) NOT NULL,
    combination_hash BINARY(32) NOT NULL,
    canonical_combination VARBINARY(2048) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_variant_key PRIMARY KEY (id),
    CONSTRAINT uq_p77_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p77_1 UNIQUE (tenant_id, company_id, family_id, combination_hash),
    CONSTRAINT uq_p77_2 UNIQUE (tenant_id, company_id, item_id),
    CONSTRAINT fk_p77_0 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family
        (tenant_id, company_id, id),
    CONSTRAINT fk_p77_1 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id,
        company_id, id),
    CONSTRAINT ck_item_variant_key_p77_check_0 CHECK (row_version >= 1),
    INDEX ix_item_variant_key_tenant_id (tenant_id),
    INDEX ix_p77_0 (tenant_id, company_id, family_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_variant_key")

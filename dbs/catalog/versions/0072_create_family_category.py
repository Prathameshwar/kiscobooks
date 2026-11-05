"""Create family_category; one reversible DDL."""
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE family_category (
    family_id BINARY(16) NOT NULL,
    scheme_id BINARY(16) NOT NULL,
    category_id BINARY(16) NOT NULL,
    is_primary BOOL NOT NULL,
    primary_slot INTEGER NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_family_category PRIMARY KEY (id),
    CONSTRAINT uq_p72_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p72_1 UNIQUE (tenant_id, company_id, family_id, category_id),
    CONSTRAINT uq_p72_2 UNIQUE (tenant_id, company_id, family_id, scheme_id, primary_slot),
    CONSTRAINT fk_p72_0 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family
        (tenant_id, company_id, id),
    CONSTRAINT fk_p72_1 FOREIGN KEY(tenant_id, company_id, scheme_id) REFERENCES category_scheme
        (tenant_id, company_id, id),
    CONSTRAINT fk_p72_2 FOREIGN KEY(tenant_id, company_id, scheme_id, category_id) REFERENCES
        item_category (tenant_id, company_id, scheme_id, id),
    CONSTRAINT ck_family_category_p72_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_family_category_p72_check_1 CHECK ((is_primary = 1 AND primary_slot IS NOT
        NULL AND primary_slot = 1) OR (is_primary = 0 AND primary_slot IS NULL)),
    INDEX ix_family_category_tenant_id (tenant_id),
    INDEX ix_p72_0 (tenant_id, company_id, family_id, id),
    INDEX ix_p72_1 (tenant_id, company_id, category_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE family_category")

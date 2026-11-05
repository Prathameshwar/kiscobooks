"""Create product_configuration_adoption_source; one reversible DDL."""
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_configuration_adoption_source (
    adoption_id BINARY(16) NOT NULL,
    scope_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_configuration_adoption_source PRIMARY KEY (id),
    CONSTRAINT uq_p82_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p82_1 UNIQUE (tenant_id, company_id, adoption_id, scope_id),
    CONSTRAINT fk_p82_0 FOREIGN KEY(tenant_id, company_id, adoption_id) REFERENCES
        product_configuration_adoption (tenant_id, company_id, id),
    CONSTRAINT fk_p82_1 FOREIGN KEY(tenant_id, company_id, scope_id) REFERENCES
        product_configuration_scope (tenant_id, company_id, id),
    CONSTRAINT fk_p82_2 FOREIGN KEY(tenant_id, company_id, scope_id, revision_id) REFERENCES
        product_configuration_revision (tenant_id, company_id, scope_id, id),
    CONSTRAINT ck_product_configuration_adoption_source_p82_check_0 CHECK (row_version >= 1),
    INDEX ix_p82_0 (tenant_id, company_id, adoption_id, id),
    INDEX ix_p82_1 (tenant_id, company_id, revision_id, id),
    INDEX ix_product_configuration_adoption_source_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE product_configuration_adoption_source")

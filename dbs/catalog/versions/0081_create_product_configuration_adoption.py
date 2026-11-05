"""Create product_configuration_adoption; one reversible DDL."""
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_configuration_adoption (
    item_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    effective_on DATE NOT NULL,
    product_type_revision_id BINARY(16) NOT NULL,
    group_assignment_id BINARY(16) NULL,
    source_version BIGINT NOT NULL,
    policy_generation BIGINT NOT NULL,
    preview_hash BINARY(32) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_configuration_adoption PRIMARY KEY (id),
    CONSTRAINT uq_p81_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p81_1 UNIQUE (tenant_id, company_id, item_id, revision),
    CONSTRAINT fk_p81_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id,
        company_id, id),
    CONSTRAINT fk_p81_1 FOREIGN KEY(tenant_id, company_id, product_type_revision_id) REFERENCES
        product_type_revision (tenant_id, company_id, id),
    CONSTRAINT fk_p81_2 FOREIGN KEY(tenant_id, company_id, group_assignment_id) REFERENCES
        family_group_assignment (tenant_id, company_id, id),
    CONSTRAINT ck_product_configuration_adoption_p81_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_product_configuration_adoption_p81_check_1 CHECK (revision >= 1 AND
        source_version >= 1 AND policy_generation >= 1),
    CONSTRAINT ck_product_configuration_adoption_p81_check_2 CHECK (effective_on >= '1000-01-01'),
    INDEX ix_p81_0 (tenant_id, company_id, item_id, effective_on, id),
    INDEX ix_product_configuration_adoption_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE product_configuration_adoption")

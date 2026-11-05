"""Create product_pricing_policy; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_pricing_policy (
    purchase_reference_mode VARCHAR(10) NOT NULL,
    sale_price_mode VARCHAR(10) NOT NULL,
    mrp_mode VARCHAR(10) NOT NULL,
    sale_level_count INTEGER NULL,
    draft_id BINARY(16) NULL,
    revision_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_pricing_policy PRIMARY KEY (id),
    CONSTRAINT uq_pricing_policy_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_pricing_policy_draft UNIQUE (tenant_id, company_id, draft_id),
    CONSTRAINT uq_pricing_policy_revision UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_pricing_policy_draft FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES
        product_configuration_draft (tenant_id, company_id, id),
    CONSTRAINT fk_pricing_policy_revision FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES product_configuration_revision (tenant_id, company_id, id),
    CONSTRAINT ck_product_pricing_policy_pricing_policy_owner CHECK ((draft_id IS NULL) <>
        (revision_id IS NULL)),
    CONSTRAINT ck_product_pricing_policy_pricing_purchase_reference_mode CHECK
        (purchase_reference_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED')),
    CONSTRAINT ck_product_pricing_policy_pricing_sale_price_mode CHECK (sale_price_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED')),
    CONSTRAINT ck_product_pricing_policy_pricing_mrp_mode CHECK (mrp_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED')),
    CONSTRAINT ck_product_pricing_policy_pricing_level_count CHECK (sale_level_count IS NULL OR
        sale_level_count BETWEEN 1 AND 64),
    INDEX ix_product_pricing_policy_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_pricing_policy")

"""Create product_configuration_draft; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_configuration_draft (
    scope_id BINARY(16) NOT NULL,
    status VARCHAR(12) NOT NULL,
    row_version INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    change_reason VARCHAR(250) NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_configuration_draft PRIMARY KEY (id),
    CONSTRAINT uq_configuration_draft_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_configuration_draft_scope_id UNIQUE (tenant_id, company_id, scope_id, id),
    CONSTRAINT fk_configuration_draft_scope FOREIGN KEY(tenant_id, company_id, scope_id)
        REFERENCES product_configuration_scope (tenant_id, company_id, id),
    CONSTRAINT ck_product_configuration_draft_configuration_draft_status CHECK (status IN
        ('DRAFT','PUBLISHED') AND row_version >= 1),
    CONSTRAINT ck_product_configuration_draft_configuration_draft_date CHECK (effective_from >=
        '1000-01-01'),
    INDEX ix_configuration_draft_scope (tenant_id, company_id, scope_id, id),
    INDEX ix_configuration_draft_status (tenant_id, company_id, scope_id, status, id),
    INDEX ix_product_configuration_draft_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_configuration_draft")

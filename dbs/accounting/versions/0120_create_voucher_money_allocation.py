"""voucher_money_allocation; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE voucher_money_allocation (
    intent_id BINARY(16) NOT NULL,
    allocation_id BINARY(16) NOT NULL,
    allocation_key BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_voucher_money_allocation PRIMARY KEY (id),
    CONSTRAINT uq_voucher_money_allocation_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_money_allocation_tenant_id_company_id_intent__4977 UNIQUE (tenant_id, company_id, intent_id, allocation_key),
    CONSTRAINT uq_voucher_money_allocation_tenant_id_company_id_allocation_id UNIQUE (tenant_id, company_id, allocation_id),
    CONSTRAINT fk_money_allocation_intent FOREIGN KEY(tenant_id, company_id, intent_id) REFERENCES voucher_money_intent (tenant_id, company_id, id),
    CONSTRAINT fk_money_allocation_effect FOREIGN KEY(tenant_id, company_id, allocation_id) REFERENCES allocation (tenant_id, company_id, id),
    INDEX ix_voucher_money_allocation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_money_allocation")

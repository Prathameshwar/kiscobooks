"""Create item_commercial_policy; one reversible DDL."""
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_commercial_policy (
    item_id BINARY(16) NOT NULL,
    free_sale_allowed BOOL NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_commercial_policy PRIMARY KEY (id),
    CONSTRAINT uq_v99_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v99_1 UNIQUE (tenant_id, company_id, item_id, valid_from),
    CONSTRAINT fk_v99_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT ck_item_commercial_policy_v99_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_commercial_policy_v99_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_item_commercial_policy_v99_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    INDEX ix_item_commercial_policy_tenant_id (tenant_id),
    INDEX ix_v99_0 (tenant_id, company_id, item_id, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_commercial_policy")

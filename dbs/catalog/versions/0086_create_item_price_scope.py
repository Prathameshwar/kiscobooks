"""Create item_price_scope; one reversible DDL."""
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_scope (
    item_id BINARY(16) NOT NULL,
    subject_kind VARCHAR(3) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_price_scope PRIMARY KEY (id),
    CONSTRAINT uq_v86_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v86_1 UNIQUE (tenant_id, company_id, item_id),
    CONSTRAINT uq_v86_2 UNIQUE (tenant_id, company_id, item_id, id),
    CONSTRAINT fk_v86_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT ck_item_price_scope_v86_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_scope_v86_1 CHECK (subject_kind = 'SKU'),
    INDEX ix_item_price_scope_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_scope")

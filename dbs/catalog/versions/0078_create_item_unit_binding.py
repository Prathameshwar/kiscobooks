"""Create item_unit_binding; one reversible DDL."""
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_unit_binding (
    item_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    unit_id BINARY(16) NOT NULL,
    usage_role VARCHAR(12) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_unit_binding PRIMARY KEY (id),
    CONSTRAINT uq_p78_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p78_item UNIQUE (tenant_id, company_id, item_id, id),
    CONSTRAINT uq_p78_1 UNIQUE (tenant_id, company_id, item_id, code),
    CONSTRAINT fk_p78_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id,
        company_id, id),
    CONSTRAINT fk_p78_1 FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES unit_of_measure
        (tenant_id, company_id, id),
    CONSTRAINT ck_item_unit_binding_p78_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_unit_binding_p78_check_1 CHECK (usage_role IN
        ('BASE','SALE','PURCHASE','BOTH','PACK','MEASURED')),
    INDEX ix_item_unit_binding_tenant_id (tenant_id),
    INDEX ix_p78_0 (tenant_id, company_id, item_id, id),
    INDEX ix_p78_1 (tenant_id, company_id, unit_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_unit_binding")

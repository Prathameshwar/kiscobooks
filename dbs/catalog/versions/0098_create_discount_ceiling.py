"""Create discount_ceiling; one reversible DDL."""
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE discount_ceiling (
    scope_id BINARY(16) NOT NULL,
    max_discount_pct NUMERIC(19,4) NOT NULL,
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
    CONSTRAINT pk_discount_ceiling PRIMARY KEY (id),
    CONSTRAINT uq_v98_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v98_1 UNIQUE (tenant_id, company_id, scope_id, valid_from),
    CONSTRAINT fk_v98_0 FOREIGN KEY(tenant_id, company_id, scope_id) REFERENCES commercial_policy_scope (tenant_id, company_id, id),
    CONSTRAINT ck_discount_ceiling_v98_0 CHECK (row_version >= 1),
    CONSTRAINT ck_discount_ceiling_v98_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_discount_ceiling_v98_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_discount_ceiling_v98_3 CHECK (max_discount_pct BETWEEN 0 AND 100),
    INDEX ix_discount_ceiling_tenant_id (tenant_id),
    INDEX ix_v98_0 (tenant_id, company_id, scope_id, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE discount_ceiling")

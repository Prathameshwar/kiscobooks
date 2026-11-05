"""Create price_level; one reversible DDL."""
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE price_level (
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    ordinal INTEGER NOT NULL,
    is_active BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_price_level PRIMARY KEY (id),
    CONSTRAINT uq_v83_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v83_1 UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_v83_2 UNIQUE (tenant_id, company_id, ordinal),
    CONSTRAINT ck_price_level_v83_0 CHECK (row_version >= 1),
    CONSTRAINT ck_price_level_v83_1 CHECK (ordinal BETWEEN 1 AND 64),
    INDEX ix_price_level_tenant_id (tenant_id),
    INDEX ix_v83_0 (tenant_id, company_id, name, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE price_level")

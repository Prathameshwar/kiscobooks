"""Create tax_release; one reversible DDL."""
from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_release (
	change_reason VARCHAR(500) NOT NULL,
	business_date DATE NOT NULL,
	input_digest VARCHAR(64) NOT NULL,
	change_count INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_release PRIMARY KEY (id),
	CONSTRAINT uq_tax_release_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_release_version CHECK (row_version >= 1),
	CONSTRAINT ck_tax_release_size CHECK (change_count BETWEEN 1 AND 100),
    INDEX ix_tax_release_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tax_release")

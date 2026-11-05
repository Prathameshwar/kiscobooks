"""report_tenant_quota; one atomic CREATE with tenant/company constraints."""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_tenant_quota (
	revision INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	CONSTRAINT pk_report_tenant_quota PRIMARY KEY (id),
	CONSTRAINT uq_report_tenant_quota_tenant UNIQUE (tenant_id),
	INDEX ix_report_tenant_quota_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_tenant_quota")

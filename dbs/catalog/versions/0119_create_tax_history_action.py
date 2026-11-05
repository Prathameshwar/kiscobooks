"""Create tax_history_action; one reversible DDL."""
from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_history_action (
	resource VARCHAR(30) NOT NULL,
	target_id BINARY(16) NOT NULL,
	action VARCHAR(10) NOT NULL,
	previous_id BINARY(16) NULL,
	previous_valid_to DATE NULL,
	release_id BINARY(16) NULL,
	reason VARCHAR(500) NOT NULL,
	business_date DATE NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_history_action PRIMARY KEY (id),
	CONSTRAINT uq_tax_history_action_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_history_action_version CHECK (row_version >= 1),
	CONSTRAINT fk_tax_history_release_id FOREIGN KEY(tenant_id, company_id, release_id) REFERENCES tax_release (tenant_id, company_id, id),
	CONSTRAINT uq_tax_history_action UNIQUE (tenant_id, company_id, resource, target_id, action),
	CONSTRAINT ck_tax_history_action_resource CHECK (resource IN ('tax_classification','tax_rate','catalog_tax_binding')),
	CONSTRAINT ck_tax_history_action_action CHECK (action IN ('PUBLISH','SUPERSEDE','WITHDRAW')),
    INDEX ix_tax_history_action_tenant_id (tenant_id),
    INDEX ix_tax_history_previous (tenant_id, company_id, resource, previous_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tax_history_action")

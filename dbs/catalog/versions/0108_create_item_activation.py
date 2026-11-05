"""Create item_activation; one reversible DDL."""
from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_activation (
	item_id BINARY(16) NOT NULL,
	adoption_id BINARY(16) NOT NULL,
	activated_on DATE NOT NULL,
	source_version BIGINT NOT NULL,
	policy_generation BIGINT NOT NULL,
	preview_hash VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_item_activation PRIMARY KEY (id),
	CONSTRAINT uq_item_activation_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_item_activation_version CHECK (row_version >= 1),
	CONSTRAINT uq_item_activation_item UNIQUE (tenant_id, company_id, item_id),
	CONSTRAINT fk_item_activation_item_id FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
	CONSTRAINT fk_item_activation_adoption_id FOREIGN KEY(tenant_id, company_id, adoption_id) REFERENCES product_configuration_adoption (tenant_id, company_id, id),
	CONSTRAINT ck_item_activation_versions CHECK (source_version >= 1 AND policy_generation >= 1),
    INDEX ix_item_activation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_activation")

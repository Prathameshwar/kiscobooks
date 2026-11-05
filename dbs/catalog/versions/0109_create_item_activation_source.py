"""Create item_activation_source; one reversible DDL."""
from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_activation_source (
	activation_id BINARY(16) NOT NULL,
	entity_type VARCHAR(80) NOT NULL,
	entity_id BINARY(16) NOT NULL,
	entity_version INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_item_activation_source PRIMARY KEY (id),
	CONSTRAINT uq_item_activation_source_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_item_activation_source_version CHECK (row_version >= 1),
	CONSTRAINT fk_activation_source_activation_id FOREIGN KEY(tenant_id, company_id, activation_id) REFERENCES item_activation (tenant_id, company_id, id),
	CONSTRAINT uq_activation_source_entity UNIQUE (tenant_id, company_id, activation_id, entity_type, entity_id),
	CONSTRAINT ck_item_activation_source_entity_version CHECK (entity_version >= 1),
    INDEX ix_item_activation_source_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_activation_source")

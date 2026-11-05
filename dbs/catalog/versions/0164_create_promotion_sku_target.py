"""Create promotion_sku_target; one DDL statement."""

from alembic import op

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_sku_target (
	revision_id BINARY(16) NOT NULL,
	item_id BINARY(16) NOT NULL,
	company_id BINARY(16) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_sku_target PRIMARY KEY (id),
	CONSTRAINT uq_promotion_sku_target_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_promotion_sku_target_item UNIQUE (tenant_id, company_id, revision_id, item_id),
    CONSTRAINT fk_promotion_sku_target_revision FOREIGN KEY(tenant_id, company_id,
        revision_id) REFERENCES promotion_revision (tenant_id, company_id, id),
    CONSTRAINT fk_promotion_sku_target_item FOREIGN KEY(tenant_id, company_id, item_id)
        REFERENCES item (tenant_id, company_id, id),
	KEY ix_promotion_sku_target_item (tenant_id, company_id, item_id, revision_id),
	KEY ix_promotion_sku_target_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_sku_target")

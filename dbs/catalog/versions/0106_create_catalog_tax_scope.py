"""Create catalog_tax_scope; one reversible DDL."""
from alembic import op

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_tax_scope (
	owner_kind VARCHAR(7) NOT NULL,
	owner_id BINARY(16) NOT NULL,
	group_id BINARY(16) NULL,
	family_id BINARY(16) NULL,
	item_id BINARY(16) NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_catalog_tax_scope PRIMARY KEY (id),
	CONSTRAINT uq_catalog_tax_scope_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_catalog_tax_scope_version CHECK (row_version >= 1),
	CONSTRAINT uq_catalog_tax_scope_owner UNIQUE (tenant_id, company_id, owner_kind, owner_id),
	CONSTRAINT fk_tax_scope_group_id FOREIGN KEY(tenant_id, company_id, group_id) REFERENCES item_group (tenant_id, company_id, id),
	CONSTRAINT fk_tax_scope_family_id FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family (tenant_id, company_id, id),
	CONSTRAINT fk_tax_scope_item_id FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
	CONSTRAINT ck_catalog_tax_scope_owner CHECK ((owner_kind = 'COMPANY' AND owner_id = company_id AND group_id IS NULL AND family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'GROUP' AND owner_id = group_id AND group_id IS NOT NULL AND family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'FAMILY' AND owner_id = family_id AND family_id IS NOT NULL AND group_id IS NULL AND item_id IS NULL) OR (owner_kind = 'SKU' AND owner_id = item_id AND item_id IS NOT NULL AND group_id IS NULL AND family_id IS NULL)),
    INDEX ix_catalog_tax_scope_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE catalog_tax_scope")

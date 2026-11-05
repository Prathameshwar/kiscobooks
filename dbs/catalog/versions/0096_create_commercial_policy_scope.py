"""Create commercial_policy_scope; one reversible DDL."""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE commercial_policy_scope (
    owner_kind VARCHAR(10) NOT NULL,
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
    CONSTRAINT pk_commercial_policy_scope PRIMARY KEY (id),
    CONSTRAINT uq_v96_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v96_1 UNIQUE (tenant_id, company_id, owner_kind, owner_id),
    CONSTRAINT fk_v96_0 FOREIGN KEY(tenant_id, company_id, group_id) REFERENCES item_group (tenant_id, company_id, id),
    CONSTRAINT fk_v96_1 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family (tenant_id, company_id, id),
    CONSTRAINT fk_v96_2 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT ck_commercial_policy_scope_v96_0 CHECK (row_version >= 1),
    CONSTRAINT ck_commercial_policy_scope_v96_1 CHECK ((owner_kind = 'COMPANY' AND owner_id = company_id AND group_id IS NULL AND family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'GROUP' AND owner_id = group_id AND group_id IS NOT NULL AND family_id IS NULL AND item_id IS NULL) OR (owner_kind = 'FAMILY' AND owner_id = family_id AND family_id IS NOT NULL AND group_id IS NULL AND item_id IS NULL) OR (owner_kind = 'SKU' AND owner_id = item_id AND item_id IS NOT NULL AND group_id IS NULL AND family_id IS NULL)),
    INDEX ix_commercial_policy_scope_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE commercial_policy_scope")

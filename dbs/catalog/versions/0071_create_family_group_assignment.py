"""Create family_group_assignment; one reversible DDL."""
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE family_group_assignment (
    family_id BINARY(16) NOT NULL,
    group_id BINARY(16) NOT NULL,
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
    CONSTRAINT pk_family_group_assignment PRIMARY KEY (id),
    CONSTRAINT uq_p71_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p71_1 UNIQUE (tenant_id, company_id, family_id, valid_from),
    CONSTRAINT fk_p71_0 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family
        (tenant_id, company_id, id),
    CONSTRAINT fk_p71_1 FOREIGN KEY(tenant_id, company_id, group_id) REFERENCES item_group
        (tenant_id, company_id, id),
    CONSTRAINT ck_family_group_assignment_p71_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_family_group_assignment_p71_check_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_family_group_assignment_p71_check_2 CHECK (valid_to IS NULL OR valid_to >=
        valid_from),
    INDEX ix_family_group_assignment_tenant_id (tenant_id),
    INDEX ix_p71_0 (tenant_id, company_id, family_id, valid_from, id),
    INDEX ix_p71_1 (tenant_id, company_id, group_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE family_group_assignment")

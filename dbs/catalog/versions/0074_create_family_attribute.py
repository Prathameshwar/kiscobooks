"""Create family_attribute; one reversible DDL."""
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE family_attribute (
    family_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    is_axis BOOL NOT NULL,
    is_required BOOL NOT NULL,
    position INTEGER NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_family_attribute PRIMARY KEY (id),
    CONSTRAINT uq_p74_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p74_1 UNIQUE (tenant_id, company_id, family_id, definition_id),
    CONSTRAINT uq_p74_2 UNIQUE (tenant_id, company_id, family_id, position),
    CONSTRAINT fk_p74_0 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family
        (tenant_id, company_id, id),
    CONSTRAINT fk_p74_1 FOREIGN KEY(tenant_id, company_id, definition_id) REFERENCES
        attribute_definition (tenant_id, company_id, id),
    CONSTRAINT ck_family_attribute_p74_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_family_attribute_p74_check_1 CHECK (position BETWEEN 0 AND 127),
    CONSTRAINT ck_family_attribute_p74_check_2 CHECK (is_axis = 0 OR is_required = 1),
    INDEX ix_family_attribute_tenant_id (tenant_id),
    INDEX ix_p74_0 (tenant_id, company_id, family_id, id),
    INDEX ix_p74_1 (tenant_id, company_id, definition_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE family_attribute")

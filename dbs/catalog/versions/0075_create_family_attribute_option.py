"""Create family_attribute_option; one reversible DDL."""
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE family_attribute_option (
    family_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    option_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_family_attribute_option PRIMARY KEY (id),
    CONSTRAINT uq_p75_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p75_1 UNIQUE (tenant_id, company_id, family_id, definition_id, option_id),
    CONSTRAINT fk_p75_0 FOREIGN KEY(tenant_id, company_id, family_id, definition_id) REFERENCES
        family_attribute (tenant_id, company_id, family_id, definition_id),
    CONSTRAINT fk_p75_1 FOREIGN KEY(tenant_id, company_id, definition_id, option_id) REFERENCES
        attribute_option (tenant_id, company_id, definition_id, id),
    CONSTRAINT ck_family_attribute_option_p75_check_0 CHECK (row_version >= 1),
    INDEX ix_family_attribute_option_tenant_id (tenant_id),
    INDEX ix_p75_0 (tenant_id, company_id, family_id, id),
    INDEX ix_p75_1 (tenant_id, company_id, option_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE family_attribute_option")

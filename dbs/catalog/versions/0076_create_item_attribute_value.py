"""Create item_attribute_value; one reversible DDL."""
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_attribute_value (
    item_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    option_id BINARY(16) NULL,
    value_type VARCHAR(10) NOT NULL,
    value_text VARCHAR(200) NULL,
    value_integer BIGINT NULL,
    value_decimal NUMERIC(19,4) NULL,
    value_boolean BOOL NULL,
    value_date DATE NULL,
    unit_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_attribute_value PRIMARY KEY (id),
    CONSTRAINT uq_p76_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p76_1 UNIQUE (tenant_id, company_id, item_id, definition_id),
    CONSTRAINT fk_p76_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id,
        company_id, id),
    CONSTRAINT fk_p76_1 FOREIGN KEY(tenant_id, company_id, definition_id) REFERENCES
        attribute_definition (tenant_id, company_id, id),
    CONSTRAINT fk_p76_2 FOREIGN KEY(tenant_id, company_id, definition_id, option_id) REFERENCES
        attribute_option (tenant_id, company_id, definition_id, id),
    CONSTRAINT fk_p76_3 FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES unit_of_measure
        (tenant_id, company_id, id),
    CONSTRAINT ck_item_attribute_value_p76_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_attribute_value_p76_check_1 CHECK (value_type IN
        ('TEXT','INTEGER','DECIMAL','BOOLEAN','DATE')),
    CONSTRAINT ck_item_attribute_value_p76_check_2 CHECK ((option_id IS NOT NULL AND value_text
        IS NULL AND value_integer IS NULL AND value_decimal IS NULL AND value_boolean IS NULL
        AND value_date IS NULL AND unit_id IS NULL) OR (option_id IS NULL AND ((value_text IS
        NOT NULL) + (value_integer IS NOT NULL) + (value_decimal IS NOT NULL) + (value_boolean
        IS NOT NULL) + (value_date IS NOT NULL)) = 1)),
    CONSTRAINT ck_item_attribute_value_p76_check_3 CHECK (value_date IS NULL OR value_date >=
        '1000-01-01'),
    CONSTRAINT ck_item_attribute_value_p76_scalar_type CHECK (option_id IS NOT NULL OR
        ((value_type = 'TEXT' AND value_text IS NOT NULL AND unit_id IS NULL) OR (value_type =
        'INTEGER' AND value_integer IS NOT NULL AND unit_id IS NULL) OR (value_type = 'DECIMAL'
        AND value_decimal IS NOT NULL) OR (value_type = 'BOOLEAN' AND value_boolean IS NOT NULL
        AND unit_id IS NULL) OR (value_type = 'DATE' AND value_date IS NOT NULL AND unit_id IS
        NULL))),
    INDEX ix_item_attribute_value_tenant_id (tenant_id),
    INDEX ix_p76_0 (tenant_id, company_id, item_id, id),
    INDEX ix_p76_1 (tenant_id, company_id, definition_id, id),
    INDEX ix_p76_2 (tenant_id, company_id, option_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_attribute_value")

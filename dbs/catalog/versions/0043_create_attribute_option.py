"""Create attribute_option; one atomic DDL with its paired model."""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE attribute_option (
    definition_id BINARY(16) NOT NULL,
    value_type VARCHAR(10) NOT NULL,
    value_text VARCHAR(200) NULL,
    value_integer BIGINT NULL,
    value_decimal NUMERIC(19,4) NULL,
    value_boolean BOOL NULL,
    value_date DATE NULL,
    unit_id BINARY(16) NULL,
    value_hash BINARY(32) NOT NULL,
    canonical_value VARBINARY(1024) NOT NULL,
    company_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT ck_attribute_option_attribute_option_boolean CHECK (value_boolean IS NULL OR
        value_boolean IN (0,1)),
    CONSTRAINT ck_attribute_option_attribute_option_date CHECK (value_date IS NULL OR value_date >=
        '1000-01-01'),
    CONSTRAINT ck_attribute_option_attribute_option_representation CHECK ((value_type='TEXT' AND
        value_text IS NOT NULL AND value_integer IS NULL AND value_decimal IS NULL AND value_boolean
        IS NULL AND value_date IS NULL AND unit_id IS NULL) OR (value_type='INTEGER' AND value_text
        IS NULL AND value_integer IS NOT NULL AND value_decimal IS NULL AND value_boolean IS NULL
        AND value_date IS NULL) OR (value_type='DECIMAL' AND value_text IS NULL AND value_integer IS
        NULL AND value_decimal IS NOT NULL AND value_boolean IS NULL AND value_date IS NULL) OR
        (value_type='BOOLEAN' AND value_text IS NULL AND value_integer IS NULL AND value_decimal IS
        NULL AND value_boolean IS NOT NULL AND value_date IS NULL AND unit_id IS NULL) OR
        (value_type='DATE' AND value_text IS NULL AND value_integer IS NULL AND value_decimal IS
        NULL AND value_boolean IS NULL AND value_date IS NOT NULL AND unit_id IS NULL)),
    CONSTRAINT ck_attribute_option_attribute_option_version CHECK (row_version >= 1),
    CONSTRAINT fk_attribute_option_definition FOREIGN KEY(tenant_id, company_id, definition_id,
        value_type) REFERENCES attribute_definition (tenant_id, company_id, id, value_type),
    CONSTRAINT fk_attribute_option_unit FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES
        unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT pk_attribute_option PRIMARY KEY (id),
    CONSTRAINT uq_attribute_option_parent_id UNIQUE (tenant_id, company_id, definition_id, id),
    CONSTRAINT uq_attribute_option_scope_code UNIQUE (tenant_id, company_id, definition_id, code),
    CONSTRAINT uq_attribute_option_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_attribute_option_value UNIQUE (tenant_id, company_id, definition_id, value_hash),
    KEY ix_attribute_option_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_attribute_option_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_attribute_option_code (tenant_id, company_id, code, id),
    KEY ix_attribute_option_definition_type (tenant_id, company_id, definition_id, value_type),
    KEY ix_attribute_option_name (tenant_id, company_id, name, id),
    KEY ix_attribute_option_parent_name (tenant_id, company_id, definition_id, name, id),
    KEY ix_attribute_option_tenant_id (tenant_id),
    KEY ix_attribute_option_unit (tenant_id, company_id, unit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE attribute_option")

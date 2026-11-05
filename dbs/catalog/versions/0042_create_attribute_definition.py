"""Create attribute_definition; one atomic DDL with its paired model."""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE attribute_definition (
    value_type VARCHAR(10) NOT NULL,
    measurement_dimension VARCHAR(20) NULL,
    is_variant_capable BOOL NOT NULL,
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
    CONSTRAINT ck_attribute_definition_attribute_definition_dimension CHECK (measurement_dimension
        IS NULL OR (value_type IN ('INTEGER','DECIMAL') AND measurement_dimension IN
        ('COUNT','MASS','VOLUME','LENGTH','AREA','TIME','JOB'))),
    CONSTRAINT ck_attribute_definition_attribute_definition_type CHECK (value_type IN
        ('TEXT','INTEGER','DECIMAL','BOOLEAN','DATE')),
    CONSTRAINT ck_attribute_definition_attribute_definition_variant CHECK (is_variant_capable IN
        (0,1)),
    CONSTRAINT ck_attribute_definition_attribute_definition_version CHECK (row_version >= 1),
    CONSTRAINT pk_attribute_definition PRIMARY KEY (id),
    CONSTRAINT uq_attribute_definition_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_attribute_definition_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_attribute_definition_type UNIQUE (tenant_id, company_id, id, value_type),
    KEY ix_attribute_definition_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_attribute_definition_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_attribute_definition_name (tenant_id, company_id, name, id),
    KEY ix_attribute_definition_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE attribute_definition")

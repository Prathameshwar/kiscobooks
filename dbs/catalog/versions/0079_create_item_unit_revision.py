"""Create item_unit_revision; one reversible DDL."""
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_unit_revision (
    binding_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    pack_type_id BINARY(16) NULL,
    conversion_mode VARCHAR(10) NOT NULL,
    numerator BIGINT NULL,
    denominator BIGINT NULL,
    nominal_ratio NUMERIC(19,4) NULL,
    secondary_unit_id BINARY(16) NULL,
    quantity_decimal_places INTEGER NOT NULL,
    quantity_increment NUMERIC(19,4) NOT NULL,
    fractional_entry BOOL NOT NULL,
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
    CONSTRAINT pk_item_unit_revision PRIMARY KEY (id),
    CONSTRAINT uq_p79_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p79_1 UNIQUE (tenant_id, company_id, binding_id, revision),
    CONSTRAINT uq_p79_2 UNIQUE (tenant_id, company_id, binding_id, valid_from),
    CONSTRAINT fk_p79_0 FOREIGN KEY(tenant_id, company_id, binding_id) REFERENCES
        item_unit_binding (tenant_id, company_id, id),
    CONSTRAINT fk_p79_1 FOREIGN KEY(tenant_id, company_id, pack_type_id) REFERENCES pack_type
        (tenant_id, company_id, id),
    CONSTRAINT fk_p79_2 FOREIGN KEY(tenant_id, company_id, secondary_unit_id) REFERENCES
        unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT ck_item_unit_revision_p79_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_unit_revision_p79_check_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_item_unit_revision_p79_check_2 CHECK (valid_to IS NULL OR valid_to >=
        valid_from),
    CONSTRAINT ck_item_unit_revision_p79_check_3 CHECK (revision >= 1),
    CONSTRAINT ck_item_unit_revision_p79_check_4 CHECK (quantity_decimal_places BETWEEN 0 AND 4
        AND quantity_increment > 0),
    CONSTRAINT ck_item_unit_revision_p79_check_5 CHECK ((conversion_mode = 'FIXED' AND numerator
        > 0 AND denominator > 0 AND numerator IS NOT NULL AND denominator IS NOT NULL AND
        nominal_ratio IS NULL AND secondary_unit_id IS NULL) OR (conversion_mode = 'MEASURED'
        AND numerator IS NULL AND denominator IS NULL AND nominal_ratio > 0 AND nominal_ratio IS
        NOT NULL AND secondary_unit_id IS NOT NULL)),
    INDEX ix_item_unit_revision_tenant_id (tenant_id),
    INDEX ix_p79_0 (tenant_id, company_id, binding_id, valid_from, id),
    INDEX ix_p79_1 (tenant_id, company_id, pack_type_id, id),
    INDEX ix_p79_2 (tenant_id, company_id, secondary_unit_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_unit_revision")

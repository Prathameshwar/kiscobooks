"""Create product_entry_option_policy; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_entry_option_policy (
    variants_mode VARCHAR(10) NOT NULL,
    variants_default BOOL NULL,
    barcode_mode VARCHAR(10) NOT NULL,
    barcode_default BOOL NULL,
    brand_mode VARCHAR(10) NOT NULL,
    brand_default BOOL NULL,
    category_mode VARCHAR(10) NOT NULL,
    category_default BOOL NULL,
    manufacturer_mode VARCHAR(10) NOT NULL,
    manufacturer_default BOOL NULL,
    alternate_units_mode VARCHAR(10) NOT NULL,
    alternate_units_default BOOL NULL,
    compound_units_mode VARCHAR(10) NOT NULL,
    compound_units_default BOOL NULL,
    measured_units_mode VARCHAR(10) NOT NULL,
    measured_units_default BOOL NULL,
    draft_id BINARY(16) NULL,
    revision_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_entry_option_policy PRIMARY KEY (id),
    CONSTRAINT uq_entry_option_policy_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_entry_option_policy_draft UNIQUE (tenant_id, company_id, draft_id),
    CONSTRAINT uq_entry_option_policy_revision UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_entry_option_policy_draft FOREIGN KEY(tenant_id, company_id, draft_id)
        REFERENCES product_configuration_draft (tenant_id, company_id, id),
    CONSTRAINT fk_entry_option_policy_revision FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES product_configuration_revision (tenant_id, company_id, id),
    CONSTRAINT ck_product_entry_option_policy_entry_option_policy_owner CHECK ((draft_id IS
        NULL) <> (revision_id IS NULL)),
    CONSTRAINT ck_product_entry_option_policy_entry_variants_mode CHECK (variants_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND ((variants_mode = 'OPTIONAL' AND
        variants_default IS NOT NULL) OR (variants_mode <> 'OPTIONAL' AND variants_default IS
        NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_barcode_mode CHECK (barcode_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND ((barcode_mode = 'OPTIONAL' AND
        barcode_default IS NOT NULL) OR (barcode_mode <> 'OPTIONAL' AND barcode_default IS
        NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_brand_mode CHECK (brand_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND ((brand_mode = 'OPTIONAL' AND
        brand_default IS NOT NULL) OR (brand_mode <> 'OPTIONAL' AND brand_default IS NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_category_mode CHECK (category_mode IN
        ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND ((category_mode = 'OPTIONAL' AND
        category_default IS NOT NULL) OR (category_mode <> 'OPTIONAL' AND category_default IS
        NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_manufacturer_mode CHECK (manufacturer_mode
        IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND ((manufacturer_mode = 'OPTIONAL' AND
        manufacturer_default IS NOT NULL) OR (manufacturer_mode <> 'OPTIONAL' AND
        manufacturer_default IS NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_alternate_units_mode CHECK
        (alternate_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND
        ((alternate_units_mode = 'OPTIONAL' AND alternate_units_default IS NOT NULL) OR
        (alternate_units_mode <> 'OPTIONAL' AND alternate_units_default IS NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_compound_units_mode CHECK
        (compound_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND
        ((compound_units_mode = 'OPTIONAL' AND compound_units_default IS NOT NULL) OR
        (compound_units_mode <> 'OPTIONAL' AND compound_units_default IS NULL))),
    CONSTRAINT ck_product_entry_option_policy_entry_measured_units_mode CHECK
        (measured_units_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND
        ((measured_units_mode = 'OPTIONAL' AND measured_units_default IS NOT NULL) OR
        (measured_units_mode <> 'OPTIONAL' AND measured_units_default IS NULL))),
    INDEX ix_product_entry_option_policy_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_entry_option_policy")

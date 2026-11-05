"""Create family_manufacturer; one reversible DDL."""
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE family_manufacturer (
    family_id BINARY(16) NOT NULL,
    manufacturer_id BINARY(16) NOT NULL,
    site_id BINARY(16) NULL,
    production_role VARCHAR(20) NOT NULL,
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
    CONSTRAINT pk_family_manufacturer PRIMARY KEY (id),
    CONSTRAINT uq_p73_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p73_1 UNIQUE (tenant_id, company_id, family_id, manufacturer_id,
        production_role, valid_from),
    CONSTRAINT fk_p73_0 FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family
        (tenant_id, company_id, id),
    CONSTRAINT fk_p73_1 FOREIGN KEY(tenant_id, company_id, manufacturer_id) REFERENCES
        manufacturer (tenant_id, company_id, id),
    CONSTRAINT fk_p73_2 FOREIGN KEY(tenant_id, company_id, manufacturer_id, site_id) REFERENCES
        manufacturer_site (tenant_id, company_id, manufacturer_id, id),
    CONSTRAINT ck_family_manufacturer_p73_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_family_manufacturer_p73_check_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_family_manufacturer_p73_check_2 CHECK (valid_to IS NULL OR valid_to >=
        valid_from),
    CONSTRAINT ck_family_manufacturer_p73_check_3 CHECK (production_role IN
        ('MANUFACTURER','ASSEMBLER','IMPORTER')),
    INDEX ix_family_manufacturer_tenant_id (tenant_id),
    INDEX ix_p73_0 (tenant_id, company_id, family_id, id),
    INDEX ix_p73_1 (tenant_id, company_id, manufacturer_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE family_manufacturer")

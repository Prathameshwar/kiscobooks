"""Live company product authoring control; compatibility data is seeded separately."""

from alembic import op

revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE company_product_authoring_configuration (
        product_family_sku_enabled BOOL NOT NULL,
        row_version INTEGER NOT NULL,
        change_reason VARCHAR(250) NOT NULL,
        company_id BINARY(16) NOT NULL,
        id BINARY(16) NOT NULL,
        tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL,
        created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL,
        updated_by BINARY(16),
        CONSTRAINT pk_company_product_authoring_configuration PRIMARY KEY (id),
        CONSTRAINT uq_company_product_authoring_company UNIQUE (tenant_id, company_id),
        CONSTRAINT ck_company_product_authoring_configuration_product_autho_e07d
            CHECK (row_version >= 1),
        KEY ix_company_product_authoring_configuration_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE company_product_authoring_configuration")

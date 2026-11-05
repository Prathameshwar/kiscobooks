"""Create product_numeric_default; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_numeric_default (
    dimension VARCHAR(10) NOT NULL,
    quantity_decimal_places INTEGER NULL,
    quantity_increment NUMERIC(19,4) NULL,
    price_decimal_places INTEGER NULL,
    price_increment NUMERIC(19,4) NULL,
    currency VARCHAR(3) NULL,
    price_basis_quantity NUMERIC(19,4) NULL,
    draft_id BINARY(16) NULL,
    revision_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_numeric_default PRIMARY KEY (id),
    CONSTRAINT uq_numeric_default_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_numeric_default_draft UNIQUE (tenant_id, company_id, draft_id, dimension),
    CONSTRAINT uq_numeric_default_revision UNIQUE (tenant_id, company_id, revision_id, dimension),
    CONSTRAINT fk_numeric_default_draft FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES
        product_configuration_draft (tenant_id, company_id, id),
    CONSTRAINT fk_numeric_default_revision FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES product_configuration_revision (tenant_id, company_id, id),
    CONSTRAINT ck_product_numeric_default_numeric_default_owner CHECK ((draft_id IS NULL) <>
        (revision_id IS NULL)),
    CONSTRAINT ck_product_numeric_default_numeric_default_dimension CHECK (dimension IN
        ('COUNT','MASS','VOLUME','LENGTH','AREA','TIME','JOB')),
    CONSTRAINT ck_product_numeric_default_numeric_default_quantity CHECK
        ((quantity_decimal_places IS NULL AND quantity_increment IS NULL) OR
        (quantity_decimal_places IS NOT NULL AND quantity_increment IS NOT NULL AND
        quantity_decimal_places BETWEEN 0 AND 4 AND quantity_increment > 0)),
    CONSTRAINT ck_product_numeric_default_numeric_default_price CHECK ((price_decimal_places IS
        NULL AND currency IS NULL AND price_increment IS NULL) OR (price_decimal_places IS NOT
        NULL AND currency IS NOT NULL AND price_decimal_places BETWEEN 0 AND 4 AND
        (price_increment IS NULL OR price_increment > 0))),
    CONSTRAINT ck_product_numeric_default_numeric_default_basis CHECK (price_basis_quantity IS
        NULL OR price_basis_quantity > 0),
    INDEX ix_product_numeric_default_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_numeric_default")

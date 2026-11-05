"""Index signed Catalog drug revisions by item and effective date; one DDL."""

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE voucher_item_regulatory_projection (
    classification_id BINARY(16) NOT NULL,
    item_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    product_kind VARCHAR(10) NOT NULL,
    licence_class VARCHAR(24) NULL,
    prescription_schedule VARCHAR(4) NULL,
    source_version BIGINT NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    reviewed_by BINARY(16) NOT NULL,
    reviewed_at DATETIME(6) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_voucher_item_regulatory_projection PRIMARY KEY (id),
    CONSTRAINT uq_voucher_item_reg_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_item_reg_source UNIQUE (tenant_id, company_id, classification_id),
    CONSTRAINT ck_voucher_item_reg_version CHECK (row_version >= 1),
    CONSTRAINT ck_voucher_item_reg_source_version CHECK (source_version >= 1),
    CONSTRAINT ck_voucher_item_reg_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_voucher_item_reg_kind CHECK (product_kind IN ('NON_DRUG','MEDICINE')),
    CONSTRAINT ck_voucher_item_reg_class_shape CHECK (
        (product_kind = 'NON_DRUG' AND licence_class IS NULL AND prescription_schedule IS NULL)
        OR (product_kind = 'MEDICINE' AND licence_class IN
            ('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X')
            AND prescription_schedule IN ('NONE','H','H1','X'))
    ),
    KEY ix_voucher_item_reg_asof (tenant_id, company_id, item_id, valid_from, id),
    KEY ix_voucher_item_regulatory_projection_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_item_regulatory_projection")

"""Create reviewed item regulatory history; one DDL statement."""

from alembic import op

revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_regulatory_classification (
    item_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    product_kind VARCHAR(10) NOT NULL,
    licence_class VARCHAR(24) NULL,
    prescription_schedule VARCHAR(4) NULL,
    source_reference VARCHAR(500) NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    review_reason VARCHAR(1000) NOT NULL,
    reviewed_at DATETIME(6) NOT NULL,
    reviewed_by BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_regulatory_classification PRIMARY KEY (id),
    CONSTRAINT uq_item_regulatory_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_item_regulatory_start UNIQUE (tenant_id, company_id, item_id, valid_from),
    CONSTRAINT fk_item_regulatory_item FOREIGN KEY (tenant_id, company_id, item_id)
        REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT ck_item_regulatory_version CHECK (row_version >= 1),
    CONSTRAINT ck_item_regulatory_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_item_regulatory_kind CHECK (product_kind IN ('NON_DRUG','MEDICINE')),
    CONSTRAINT ck_item_regulatory_class_shape CHECK (
        (product_kind = 'NON_DRUG' AND licence_class IS NULL AND prescription_schedule IS NULL)
        OR (product_kind = 'MEDICINE' AND licence_class IN
            ('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X')
            AND prescription_schedule IN ('NONE','H','H1','X'))
    ),
    KEY ix_item_regulatory_effective (tenant_id, company_id, item_id, valid_from, id),
    KEY ix_item_regulatory_classification_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_regulatory_classification")

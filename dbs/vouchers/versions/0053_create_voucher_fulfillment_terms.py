"""Shared non-posting fulfillment terms; one DDL statement."""

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE voucher_fulfillment_terms (
    revision_id BINARY(16) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    valid_until DATE NULL,
    required_by DATE NULL,
    destination_reference VARCHAR(120) NULL,
    delivery_terms VARCHAR(1000) NOT NULL,
    payment_terms VARCHAR(1000) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_voucher_fulfillment_terms PRIMARY KEY (id),
    CONSTRAINT uq_voucher_fulfillment_terms_tenant_id_company_id_id
        UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_fulfillment_terms_tenant_id_company_id_revision_id
        UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_voucher_fulfillment_terms_revision FOREIGN KEY
        (tenant_id, company_id, revision_id)
        REFERENCES voucher_revision (tenant_id, company_id, id),
    CONSTRAINT ck_voucher_fulfillment_terms_purpose CHECK
        (purpose IN ('PROCURE','INTERNAL_ISSUE','SALE','PURCHASE','QUOTE')),
    KEY ix_voucher_fulfillment_terms_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_fulfillment_terms")

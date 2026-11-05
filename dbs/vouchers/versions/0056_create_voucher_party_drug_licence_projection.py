"""Index signed Accounting licence revisions by party and premises; one DDL."""

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE voucher_party_drug_licence_projection (
    licence_id BINARY(16) NOT NULL,
    party_id BINARY(16) NOT NULL,
    address_id BINARY(16) NOT NULL,
    licence_form VARCHAR(4) NOT NULL,
    licence_number VARCHAR(80) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
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
    CONSTRAINT pk_voucher_party_drug_licence_projection PRIMARY KEY (id),
    CONSTRAINT uq_voucher_party_drug_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_party_drug_source UNIQUE (tenant_id, company_id, licence_id),
    CONSTRAINT ck_voucher_party_drug_version CHECK (row_version >= 1),
    CONSTRAINT ck_voucher_party_drug_source_version CHECK (source_version >= 1),
    CONSTRAINT ck_voucher_party_drug_form CHECK (licence_form IN ('20','20B','21','21B')),
    CONSTRAINT ck_voucher_party_drug_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    KEY ix_voucher_party_drug_asof
        (tenant_id, company_id, party_id, address_id, licence_form, valid_from, id),
    KEY ix_voucher_party_drug_licence_projection_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_party_drug_licence_projection")

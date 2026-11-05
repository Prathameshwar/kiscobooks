"""Create reviewed counterparty drug licences by premises; one DDL statement."""

from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE party_drug_licence (
    party_id BINARY(16) NOT NULL,
    address_id BINARY(16) NOT NULL,
    licence_form VARCHAR(4) NOT NULL,
    licence_number VARCHAR(80) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    source_reference VARCHAR(500) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    reviewed_at DATETIME(6) NOT NULL,
    reviewed_by BINARY(16) NOT NULL,
    closure_reason VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_party_drug_licence PRIMARY KEY (id),
    CONSTRAINT uq_party_drug_licence_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_party_drug_licence_start UNIQUE
        (tenant_id, company_id, address_id, licence_number, valid_from),
    CONSTRAINT fk_party_drug_licence_party FOREIGN KEY (tenant_id, company_id, party_id)
        REFERENCES party (tenant_id, company_id, id),
    CONSTRAINT fk_party_drug_licence_address FOREIGN KEY (tenant_id, company_id, address_id)
        REFERENCES party_address (tenant_id, company_id, id),
    CONSTRAINT ck_party_drug_licence_version CHECK (row_version >= 1),
    CONSTRAINT ck_party_drug_licence_form CHECK (licence_form IN ('20','20B','21','21B')),
    CONSTRAINT ck_party_drug_licence_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    KEY ix_party_drug_licence_asof
        (tenant_id, company_id, party_id, address_id, valid_from, id),
    KEY ix_party_drug_licence_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE party_drug_licence")

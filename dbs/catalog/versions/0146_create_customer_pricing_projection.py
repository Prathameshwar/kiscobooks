"""Catalog customer_pricing_projection: dated customer/customer-type binding; one DDL."""

from alembic import op

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE customer_pricing_projection (
    party_id BINARY(16) NOT NULL,
    customer_type_code VARCHAR(40) NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    is_active TINYINT(1) NOT NULL,
    company_id BINARY(16) NOT NULL,
    source_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_customer_pricing_projection PRIMARY KEY (id),
    CONSTRAINT uq_customer_pricing_projection_source UNIQUE (tenant_id, company_id, source_id),
    CONSTRAINT ck_customer_pricing_projection_source_version CHECK (source_version > 0),
    CONSTRAINT ck_customer_pricing_projection_dates
        CHECK (valid_to IS NULL OR valid_to >= valid_from),
    KEY ix_customer_pricing_projection_tenant_id (tenant_id),
    KEY ix_customer_pricing_projection_lookup_0
        (tenant_id, company_id, party_id, valid_from)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE customer_pricing_projection")

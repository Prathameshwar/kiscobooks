"""Catalog party_projection: minimal Billing-sourced party identity; one DDL."""

from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE party_projection (
    party_kind VARCHAR(20) NOT NULL,
    code VARCHAR(60) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    country_code VARCHAR(2) NULL,
    company_id BINARY(16) NOT NULL,
    source_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_party_projection PRIMARY KEY (id),
    CONSTRAINT uq_party_projection_source UNIQUE (tenant_id, company_id, source_id),
    CONSTRAINT ck_party_projection_source_version CHECK (source_version > 0),
    KEY ix_party_projection_tenant_id (tenant_id),
    KEY ix_party_projection_lookup_0 (tenant_id, company_id, party_kind, code)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE party_projection")

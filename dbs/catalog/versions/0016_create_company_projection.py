"""Catalog company_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_projection (
    code VARCHAR(20) NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    country_code VARCHAR(2) NOT NULL, 
    state_code VARCHAR(6) NOT NULL, 
    base_currency VARCHAR(3) NOT NULL, 
    reporting_currency VARCHAR(3) NULL,
    fiscal_year_start_month SMALLINT NOT NULL, 
    fiscal_year_start_day SMALLINT NOT NULL, 
    amount_precision SMALLINT NOT NULL, 
    quantity_precision SMALLINT NOT NULL, 
    rounding_mode VARCHAR(20) NOT NULL, 
    default_tax_system VARCHAR(20) NOT NULL, 
    timezone VARCHAR(64) NOT NULL, 
    first_posted_at DATETIME(6) NULL,
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_company_projection PRIMARY KEY (id), 
    CONSTRAINT uq_company_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_company_projection_company_source_version CHECK (source_version > 0),
    KEY ix_company_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_projection")

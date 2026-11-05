"""Replicate company-approved transaction currencies for foreign price authoring."""

from alembic import op

revision = "0176"
down_revision = "0175"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_currency_allowance_projection (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    source_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    source_company_id BINARY(16) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    is_active BOOL NOT NULL,
    CONSTRAINT pk_company_currency_allowance_projection PRIMARY KEY (id),
    CONSTRAINT uq_currency_allowance_projection_source
        UNIQUE (tenant_id, company_id, source_id),
    KEY ix_currency_allowance_projection_lookup
        (tenant_id, company_id, currency_code, is_active),
    KEY ix_company_currency_allowance_projection_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_currency_allowance_projection")

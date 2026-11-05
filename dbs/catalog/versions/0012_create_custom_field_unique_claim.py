"""Catalog-owned custom_field_unique_claim; one DDL, no source definitions."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE custom_field_unique_claim (
    company_id BINARY(16) NOT NULL, 
    scope_company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    entity_id BINARY(16) NOT NULL, 
    field_key VARCHAR(64) NOT NULL, 
    value_hash BINARY(32) NOT NULL, 
    canonical_value VARBINARY(4096) NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_custom_field_unique_claim PRIMARY KEY (id), 
        CONSTRAINT uq_custom_field_claim_value UNIQUE (tenant_id, scope_company_id, entity_type,
        field_key, value_hash),
    KEY ix_custom_field_claim_owner (tenant_id, company_id, entity_type, entity_id),
    KEY ix_custom_field_unique_claim_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_unique_claim")

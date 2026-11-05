"""Catalog-owned custom_field_sequence; one DDL, no source definitions."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE custom_field_sequence (
    company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    field_key VARCHAR(64) NOT NULL, 
    cycle_key VARCHAR(40) NOT NULL, 
    next_value BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_custom_field_sequence PRIMARY KEY (id), 
        CONSTRAINT uq_custom_field_sequence_scope UNIQUE (tenant_id, company_id, entity_type,
        field_key, cycle_key),
    CONSTRAINT ck_custom_field_sequence_custom_field_sequence_positive CHECK (next_value >= 1),
    KEY ix_custom_field_sequence_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_sequence")

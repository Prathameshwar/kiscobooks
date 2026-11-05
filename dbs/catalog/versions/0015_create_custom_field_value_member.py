"""Catalog-owned custom_field_value_member; one DDL, no source definitions."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE custom_field_value_member (
    company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    entity_id BINARY(16) NOT NULL, 
    field_key VARCHAR(64) NOT NULL, 
    generation BIGINT NOT NULL, 
    member_value VARCHAR(200) COLLATE utf8mb4_bin NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_custom_field_value_member PRIMARY KEY (id), 
        CONSTRAINT uq_custom_field_member_owner UNIQUE (tenant_id, company_id, entity_type,
        entity_id, field_key, generation, member_value),
    CONSTRAINT ck_custom_field_value_member_custom_member_generation CHECK (generation >= 1),
    KEY ix_custom_field_value_member_tenant_id (tenant_id),
        KEY ix_custom_member_lookup (tenant_id, company_id, entity_type, field_key, generation,
        member_value, entity_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_value_member")

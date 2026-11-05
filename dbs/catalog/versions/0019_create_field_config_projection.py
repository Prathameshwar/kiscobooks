"""Catalog field_config_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE field_config_projection (
    source_company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    field_source VARCHAR(10) NOT NULL, 
    field_key VARCHAR(120) NOT NULL, 
    definition_id BINARY(16) NULL,
    is_visible BOOL NULL,
    is_required BOOL NULL,
    display_order SMALLINT NULL,
    display_group VARCHAR(100) NULL,
    label_override VARCHAR(150) NULL,
    help_text_override VARCHAR(500) NULL,
    default_value VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_field_config_projection PRIMARY KEY (id), 
    CONSTRAINT uq_field_config_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_field_config_projection_field_config_source_version CHECK (source_version > 0),
        KEY ix_field_config_projection_lookup_0 (tenant_id, company_id, source_company_id,
        entity_type, field_key),
    KEY ix_field_config_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_config_projection")

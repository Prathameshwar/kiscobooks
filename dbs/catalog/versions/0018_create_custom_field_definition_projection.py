"""Catalog custom_field_definition_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE custom_field_definition_projection (
    source_company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    definition_key VARCHAR(60) NOT NULL, 
    label VARCHAR(150) NOT NULL, 
    help_text VARCHAR(500) NULL,
    placeholder VARCHAR(150) NULL,
    data_type VARCHAR(30) NOT NULL, 
    display_order SMALLINT NOT NULL, 
    display_group VARCHAR(100) NULL,
    is_active BOOL NOT NULL, 
    is_searchable BOOL NOT NULL, 
    is_immutable_after_create BOOL NOT NULL, 
    requires_feature VARCHAR(60) NULL,
    validation JSON NULL,
    options JSON NULL,
    option_source_key VARCHAR(80) NULL,
    depends_on_key VARCHAR(60) NULL,
    visibility JSON NULL,
    sequence_config JSON NULL,
    default_value VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_custom_field_definition_projection PRIMARY KEY (id), 
    CONSTRAINT uq_cf_definition_projection_source UNIQUE (tenant_id, company_id, source_id), 
        CONSTRAINT ck_custom_field_definition_projection_cf_definition_sour_4ee9 CHECK
        (source_version > 0),
        KEY ix_cf_definition_projection_lookup_0 (tenant_id, company_id, source_company_id,
        entity_type, definition_key),
    KEY ix_custom_field_definition_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_definition_projection")

"""Catalog field_policy_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE field_policy_projection (
    subject_type VARCHAR(12) NOT NULL, 
    subject_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    field_key VARCHAR(120) NOT NULL, 
    access VARCHAR(10) NOT NULL, 
    effect VARCHAR(10) NOT NULL, 
    scope_type VARCHAR(12) NOT NULL, 
    scope_id BINARY(16) NOT NULL, 
    predicate_json JSON NULL,
    is_active BOOL NOT NULL, 
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_field_policy_projection PRIMARY KEY (id), 
    CONSTRAINT uq_field_policy_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_field_policy_projection_field_policy_source_version CHECK (source_version > 0),
        KEY ix_field_policy_projection_lookup_0 (tenant_id, company_id, entity_type,
        subject_type, subject_id),
    KEY ix_field_policy_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_policy_projection")

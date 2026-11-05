"""Catalog role_assignment_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE role_assignment_projection (
    subject_type VARCHAR(12) NOT NULL, 
    subject_id BINARY(16) NOT NULL, 
    role_id BINARY(16) NOT NULL, 
    scope_type VARCHAR(12) NOT NULL, 
    scope_id BINARY(16) NOT NULL, 
    is_active BOOL NOT NULL, 
    valid_from DATE NOT NULL, 
    valid_to DATE NULL,
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_role_assignment_projection PRIMARY KEY (id), 
    CONSTRAINT uq_role_assignment_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_role_assignment_projection_role_assignment_source_version CHECK
        (source_version > 0),
    KEY ix_role_assignment_projection_lookup_0 (tenant_id, company_id, subject_type, subject_id),
    KEY ix_role_assignment_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE role_assignment_projection")

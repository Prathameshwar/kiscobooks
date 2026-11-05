"""Accepted product contracts and tenant uniqueness serialization."""

from alembic import op

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None
_CREATE = """CREATE TABLE custom_field_adoption (
    company_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    definitions JSON NOT NULL,
    row_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_custom_field_adoption PRIMARY KEY (id),
    CONSTRAINT uq_custom_adoption_scope UNIQUE (tenant_id, company_id, entity_type),
    CONSTRAINT ck_custom_field_adoption_custom_adoption_version CHECK (row_version >= 1),
    KEY ix_custom_field_adoption_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    raise RuntimeError("Accepted contracts and global uniqueness must be retained")

"""Create attribute_set_revision; one atomic DDL with its paired model."""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE attribute_set_revision (
    company_id BINARY(16) NOT NULL,
    attribute_set_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    published_at DATETIME(6) NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_attribute_set_revision_attribute_set_revision_version CHECK (revision >= 1 AND
        row_version >= 1),
    CONSTRAINT fk_attribute_set_revision_parent FOREIGN KEY(tenant_id, company_id, attribute_set_id)
        REFERENCES attribute_set (tenant_id, company_id, id),
    CONSTRAINT pk_attribute_set_revision PRIMARY KEY (id),
    CONSTRAINT uq_attribute_set_revision_number UNIQUE (tenant_id, company_id, attribute_set_id,
        revision),
    CONSTRAINT uq_attribute_set_revision_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_attribute_set_revision_published (tenant_id, company_id, attribute_set_id, published_at,
        revision, id),
    KEY ix_attribute_set_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE attribute_set_revision")

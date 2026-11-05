"""Create catalog_policy_release; one atomic DDL, with a paired model."""

from alembic import op

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_policy_release (
    revision INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    published_at DATETIME(6) NOT NULL,
    change_reason VARCHAR(500) NOT NULL,
    policy_generation BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    location_count INTEGER NOT NULL,
    default_count INTEGER NOT NULL,
    manifest_digest VARCHAR(64) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_catalog_policy_release_expectations CHECK (policy_generation >= 1
        AND source_version > 0),
    CONSTRAINT ck_catalog_policy_release_manifest CHECK (location_count BETWEEN 1 AND 500
        AND default_count BETWEEN 0 AND 4),
    CONSTRAINT ck_catalog_policy_release_revision CHECK (revision >= 1),
    CONSTRAINT ck_catalog_policy_release_version CHECK (row_version >= 1),
    CONSTRAINT pk_catalog_policy_release PRIMARY KEY (id),
    CONSTRAINT uq_catalog_policy_release_number UNIQUE (tenant_id, company_id, revision),
    CONSTRAINT uq_catalog_policy_release_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_catalog_policy_release_order (tenant_id, company_id, revision, effective_date, id),
    KEY ix_catalog_policy_release_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_policy_release")

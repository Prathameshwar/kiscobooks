"""Create return_policy_revision; one DDL paired with its native model."""

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE return_policy_revision (
    company_id BINARY(16) NOT NULL,
    policy_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    published_at DATETIME(6) NULL,
    returns_allowed BOOL NOT NULL,
    window_days INTEGER NULL,
    condition_count INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_return_policy_revision_return_policy_rev_count CHECK (condition_count BETWEEN 0
        AND 5),
    CONSTRAINT ck_return_policy_revision_return_policy_rev_version CHECK (revision >= 1 AND
        row_version >= 1),
    CONSTRAINT ck_return_policy_revision_return_policy_rev_window CHECK ((returns_allowed = 1 AND
        window_days IS NOT NULL AND window_days BETWEEN 0 AND 36500) OR (returns_allowed = 0 AND
        window_days IS NULL AND condition_count = 0)),
    CONSTRAINT fk_return_policy_rev_parent FOREIGN KEY(tenant_id, company_id, policy_id)
        REFERENCES return_policy (tenant_id, company_id, id),
    CONSTRAINT pk_return_policy_revision PRIMARY KEY (id),
    CONSTRAINT uq_return_policy_rev_number UNIQUE (tenant_id, company_id, policy_id, revision),
    CONSTRAINT uq_return_policy_rev_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_return_policy_rev_published (tenant_id, company_id, policy_id, published_at, revision,
        id),
    KEY ix_return_policy_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE return_policy_revision")

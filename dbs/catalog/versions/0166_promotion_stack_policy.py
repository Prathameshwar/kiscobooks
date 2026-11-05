"""Create immutable promotion stack policy revisions; one DDL statement."""

from alembic import op

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_policy (
    code VARCHAR(30) NOT NULL,
    version INTEGER NOT NULL,
    maximum_applied INTEGER NOT NULL,
    published_at DATETIME(6) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_promotion_stack_policy PRIMARY KEY (id),
    CONSTRAINT uq_promotion_stack_policy_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_promotion_stack_policy_version UNIQUE (tenant_id, company_id, code, version),
    CONSTRAINT ck_promotion_stack_policy_bounds CHECK
        (version >= 1 AND maximum_applied BETWEEN 1 AND 10),
    CONSTRAINT ck_promotion_stack_policy_hash CHECK (LENGTH(source_sha256) = 64),
    KEY ix_promotion_stack_policy_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_policy")

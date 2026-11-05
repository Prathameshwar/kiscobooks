"""Retain private, bounded advanced-product wizard drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0222"
down_revision = "0221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE advanced_product_draft (
    id BINARY(16) NOT NULL PRIMARY KEY,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    owner_user_id BINARY(16) NOT NULL,
    create_key VARCHAR(64) NOT NULL,
    create_hash VARCHAR(64) NOT NULL,
    row_version INTEGER NOT NULL,
    mode_version INTEGER NOT NULL,
    policy_generation BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    family_field_version BIGINT NOT NULL,
    sku_field_version BIGINT NOT NULL,
    step INTEGER NOT NULL,
    payload JSON NOT NULL,
    CONSTRAINT uq_advanced_product_draft_key
        UNIQUE (tenant_id, company_id, owner_user_id, create_key),
    INDEX ix_advanced_product_draft_tenant_id (tenant_id),
    INDEX ix_advanced_product_draft_owner
        (tenant_id, company_id, owner_user_id, updated_at, id),
    CONSTRAINT ck_advanced_product_draft_advanced_product_draft_version
        CHECK (row_version >= 1),
    CONSTRAINT ck_advanced_product_draft_advanced_product_draft_step
        CHECK (step BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    # Drafts contain no posted effects, but do not silently erase user work.
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM advanced_product_draft")
    ):
        raise RuntimeError("export or delete advanced product drafts before downgrade")
    op.execute("DROP TABLE advanced_product_draft")

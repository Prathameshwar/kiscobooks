"""Catalog-owned catalog_policy_state; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_policy_state (
    company_id BINARY(16) NOT NULL,
    generation BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_catalog_policy_state PRIMARY KEY (id),
    CONSTRAINT uq_catalog_policy_state_company UNIQUE (tenant_id, company_id),
    CONSTRAINT ck_catalog_policy_state_catalog_policy_generation CHECK (generation >= 1),
    KEY ix_catalog_policy_state_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_policy_state")

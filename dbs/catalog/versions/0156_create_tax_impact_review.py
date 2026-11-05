"""Catalog tax_impact_review: chunked background impact reports for tax releases; one DDL.

A release whose affected products exceed the synchronous preview bound is reviewed by the tax
review worker in bounded chunks. Publication references a COMPLETE report whose policy
generation, source version, business date and input digest still match.
"""

from alembic import op

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_impact_review (
    actor_user_id BINARY(16) NOT NULL,
    change_reason VARCHAR(500) NOT NULL,
    input_digest VARCHAR(64) NOT NULL,
    request JSON NOT NULL,
    change_count INT NOT NULL,
    policy_generation BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    business_date DATE NOT NULL,
    status VARCHAR(8) NOT NULL,
    checkpoint_id BINARY(16) NULL,
    item_count INT NOT NULL,
    checked_count INT NOT NULL,
    finding_count INT NOT NULL,
    blocking_count INT NOT NULL,
    reason_code VARCHAR(40) NULL,
    completed_at DATETIME(6) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_tax_impact_review PRIMARY KEY (id),
    CONSTRAINT uq_tax_impact_review_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_tax_impact_review_version CHECK (row_version >= 1),
    CONSTRAINT ck_tax_impact_review_status CHECK
        (status IN ('PENDING','COMPLETE','STALE','FAILED')),
    CONSTRAINT ck_tax_impact_review_size CHECK (change_count BETWEEN 1 AND 100),
    CONSTRAINT ck_tax_impact_review_counts CHECK (item_count >= 0 AND checked_count >= 0
        AND finding_count >= 0 AND blocking_count >= 0),
    KEY ix_tax_impact_review_poll (tenant_id, company_id, status, id),
    KEY ix_tax_impact_review_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tax_impact_review")

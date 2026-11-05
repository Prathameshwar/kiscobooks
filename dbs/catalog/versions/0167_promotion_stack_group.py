"""Create ordered promotion stack groups; one DDL statement."""

from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_group (
    policy_revision_id BINARY(16) NOT NULL,
    position INTEGER NOT NULL,
    stage VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    changes_basket BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_promotion_stack_group PRIMARY KEY (id),
    CONSTRAINT uq_promotion_stack_group_scope UNIQUE
        (tenant_id, company_id, policy_revision_id, id),
    CONSTRAINT uq_promotion_stack_group_position UNIQUE
        (tenant_id, company_id, policy_revision_id, position),
    CONSTRAINT fk_promotion_stack_group_policy FOREIGN KEY
        (tenant_id, company_id, policy_revision_id)
        REFERENCES promotion_stack_policy (tenant_id, company_id, id),
    CONSTRAINT ck_promotion_stack_group_position CHECK (position BETWEEN 0 AND 19),
    CONSTRAINT ck_promotion_stack_group_stage CHECK
        (stage IN ('PRODUCT_SCHEME','BASKET','MANUAL')),
    CONSTRAINT ck_promotion_stack_group_selection CHECK
        (selection IN ('PRIORITY','BEST_SINGLE','CUSTOMER_CHOICE')),
    KEY ix_promotion_stack_group_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_group")

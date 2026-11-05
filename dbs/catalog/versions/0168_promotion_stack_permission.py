"""Create promotion stack permission pairs; one DDL statement."""

from alembic import op

revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_permission (
    policy_revision_id BINARY(16) NOT NULL,
    earlier_group_id BINARY(16) NOT NULL,
    later_group_id BINARY(16) NOT NULL,
    include_reward_units BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_promotion_stack_permission PRIMARY KEY (id),
    CONSTRAINT uq_promotion_stack_permission_pair UNIQUE
        (tenant_id, company_id, policy_revision_id, earlier_group_id, later_group_id),
    CONSTRAINT fk_promotion_stack_permission_policy FOREIGN KEY
        (tenant_id, company_id, policy_revision_id)
        REFERENCES promotion_stack_policy (tenant_id, company_id, id),
    CONSTRAINT fk_promotion_stack_permission_earlier FOREIGN KEY
        (tenant_id, company_id, policy_revision_id, earlier_group_id)
        REFERENCES promotion_stack_group (tenant_id, company_id, policy_revision_id, id),
    CONSTRAINT fk_promotion_stack_permission_later FOREIGN KEY
        (tenant_id, company_id, policy_revision_id, later_group_id)
        REFERENCES promotion_stack_group (tenant_id, company_id, policy_revision_id, id),
    CONSTRAINT ck_promotion_stack_permission_different_groups CHECK
        (earlier_group_id <> later_group_id),
    KEY ix_promotion_stack_permission_tenant_id (tenant_id),
    KEY ix_promotion_stack_permission_later
        (tenant_id, company_id, policy_revision_id, later_group_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_permission")

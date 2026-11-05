"""Require a group in the selected stack policy; one DDL statement."""

from alembic import op

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE promotion_revision
    ADD CONSTRAINT fk_promotion_revision_stack_group FOREIGN KEY
        (tenant_id, company_id, stack_policy_revision_id, stack_group_id)
        REFERENCES promotion_stack_group (tenant_id, company_id, policy_revision_id, id)
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE promotion_revision DROP FOREIGN KEY fk_promotion_revision_stack_group"
    )

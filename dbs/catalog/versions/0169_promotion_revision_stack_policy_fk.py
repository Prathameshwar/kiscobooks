"""Require a same-company stack policy revision; one DDL statement."""

from alembic import op

revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE promotion_revision
    ADD CONSTRAINT fk_promotion_revision_stack_policy FOREIGN KEY
        (tenant_id, company_id, stack_policy_revision_id)
        REFERENCES promotion_stack_policy (tenant_id, company_id, id)
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE promotion_revision DROP FOREIGN KEY fk_promotion_revision_stack_policy"
    )

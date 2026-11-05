"""Native posting states for master openings; one atomic ALTER."""

import sqlalchemy as sa
from alembic import op

revision = "0234"
down_revision = "0233"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE master_opening_balance DROP CHECK ck_master_opening_balance_master_opening_status, "
        "ADD CONSTRAINT ck_master_opening_balance_master_opening_status "
        "CHECK (status IN ('PENDING','WITHDRAWN','POSTING','POSTED','REVERSED'))"
    )


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM master_opening_balance WHERE status IN ('POSTING','POSTED','REVERSED')"
        )
    ):
        raise RuntimeError("Cannot downgrade while automatic master opening evidence exists")
    op.execute(
        "ALTER TABLE master_opening_balance DROP CHECK ck_master_opening_balance_master_opening_status, "
        "ADD CONSTRAINT ck_master_opening_balance_master_opening_status "
        "CHECK (status IN ('PENDING','WITHDRAWN'))"
    )

"""Match inventory evidence table options to its owner model; one reversible DDL."""

from alembic import op

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE inventory_report_record "
        "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci, ROW_FORMAT=DYNAMIC"
    )


def downgrade() -> None:
    # Revision 0155 inherited the server's default row format.
    op.execute(
        "ALTER TABLE inventory_report_record "
        "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci, ROW_FORMAT=DEFAULT"
    )

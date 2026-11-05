"""Local access revocation timestamp; one atomic DDL per direction."""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE user
        ADD COLUMN tokens_valid_after_at DATETIME(6) NULL""")


def downgrade() -> None:
    op.execute("ALTER TABLE user DROP COLUMN tokens_valid_after_at")

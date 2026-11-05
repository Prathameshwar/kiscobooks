"""Persist the workspace selected for a registration approval.

Revision ID: 0087
Revises: 0086
"""

from alembic import op
import sqlalchemy as sa

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account_review_command", sa.Column("workspace_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("account_review_command", "workspace_name")

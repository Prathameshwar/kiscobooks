"""Preserve custom text case/accent identity; normalization belongs to its definition."""
from alembic import op
revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE custom_field_value_index MODIFY value_text VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE custom_field_value_index MODIFY value_text VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL")

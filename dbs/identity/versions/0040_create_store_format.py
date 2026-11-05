"""Seeded reference table; no tenant CRUD, one DDL per direction."""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE store_format (
    code VARCHAR(32) NOT NULL,
    label VARCHAR(100) NOT NULL,
    sort_order SMALLINT NOT NULL,
    is_active BOOL NOT NULL,
    CONSTRAINT pk_store_format PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
""")


def downgrade() -> None:
    op.execute("DROP TABLE store_format")

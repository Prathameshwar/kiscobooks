"""Seeded reference table; no tenant CRUD, one DDL per direction."""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE business_category (
    code VARCHAR(32) NOT NULL,
    label VARCHAR(100) NOT NULL,
    sort_order SMALLINT NOT NULL,
    is_active BOOL NOT NULL,
    CONSTRAINT pk_business_category PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
""")


def downgrade() -> None:
    op.execute("DROP TABLE business_category")

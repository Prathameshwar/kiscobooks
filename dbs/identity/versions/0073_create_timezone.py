"""Materialize the Identity IANA catalogue; exactly one DDL per direction."""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE timezone (
            code VARCHAR(64) NOT NULL,
            name VARCHAR(128) NOT NULL,
            is_active BOOL NOT NULL,
            CONSTRAINT pk_timezone PRIMARY KEY (code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE timezone")

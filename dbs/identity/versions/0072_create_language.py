"""Materialize the existing shared language reference; contents are seeded separately."""

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE language (
            code CHAR(2) NOT NULL,
            iso3 CHAR(3) NOT NULL,
            name VARCHAR(128) NOT NULL,
            native_name VARCHAR(128) NULL,
            is_active BOOL NOT NULL,
            CONSTRAINT pk_language PRIMARY KEY (code),
            CONSTRAINT uq_language_iso3 UNIQUE (iso3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE language")

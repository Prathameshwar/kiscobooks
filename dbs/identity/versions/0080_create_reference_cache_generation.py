"""Global cache generation; one atomic DDL per direction, data created by writers."""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE reference_cache_generation (
id BINARY(16) NOT NULL,
`key` VARCHAR(16) NOT NULL,
token BINARY(16) NOT NULL,
PRIMARY KEY (id),
UNIQUE KEY uq_reference_cache_generation_key (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE reference_cache_generation")

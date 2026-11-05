"""Global reference management; one atomic DDL per direction."""
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE reference_change (
id BINARY(16) NOT NULL,
kind VARCHAR(16) NOT NULL,
code VARCHAR(6) NOT NULL,
version INT NOT NULL,
payload JSON NOT NULL,
PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")

def downgrade() -> None:
    op.execute("DROP TABLE reference_change")

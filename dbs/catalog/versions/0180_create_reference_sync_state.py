"""Global reference management; one atomic DDL per direction."""
from alembic import op

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE reference_sync_state (
id BINARY(16) NOT NULL,
service VARCHAR(32) NOT NULL,
`cursor` BINARY(16) NULL,
PRIMARY KEY (id),
UNIQUE KEY uq_reference_sync_state_service (service)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")

def downgrade() -> None:
    op.execute("DROP TABLE reference_sync_state")

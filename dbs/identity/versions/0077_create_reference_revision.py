"""Global reference management; one atomic DDL per direction."""
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE reference_revision (
id BINARY(16) NOT NULL,
kind VARCHAR(16) NOT NULL,
code VARCHAR(6) NOT NULL,
name VARCHAR(128) NOT NULL,
parent_code VARCHAR(3) NULL,
is_active BOOL NOT NULL,
source VARCHAR(16) NOT NULL,
is_custom BOOL NOT NULL,
version INT NOT NULL,
change_id BINARY(16) NULL,
payload JSON NOT NULL,
created_at DATETIME(6) NOT NULL,
created_by BINARY(16) NULL,
updated_at DATETIME(6) NOT NULL,
updated_by BINARY(16) NULL,
PRIMARY KEY (id),
UNIQUE KEY uq_reference_revision_kind_code (kind, code),
KEY ix_reference_revision_kind_name_code (kind, name, code),
KEY ix_reference_revision_kind_active_name_code (kind, is_active, name, code),
KEY ix_reference_revision_kind_parent_name_code (kind, parent_code, name, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")

def downgrade() -> None:
    op.execute("DROP TABLE reference_revision")

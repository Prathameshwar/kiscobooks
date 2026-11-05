"""Create the local passwords and their lockout state; one reversible DDL."""
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_credential (
	identity_seq INT NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	password_changed_at DATETIME(6) NOT NULL,
	failed_attempts SMALLINT NOT NULL,
	lock_ends_at DATETIME(6) NULL,
	updated_at DATETIME(6) NOT NULL,
	CONSTRAINT pk_local_credential PRIMARY KEY (identity_seq),
	CONSTRAINT fk_local_credential_identity FOREIGN KEY(identity_seq) REFERENCES local_identity (seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_credential")

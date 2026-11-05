"""Create one-time password-recovery tokens (hash only); one reversible DDL."""
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_recovery_token (
	id BINARY(16) NOT NULL,
	identity_seq INT NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	issued_by BINARY(16) NULL,
	created_at DATETIME(6) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	used_at DATETIME(6) NULL,
	CONSTRAINT pk_local_recovery_token PRIMARY KEY (id),
	CONSTRAINT uq_local_recovery_token_hash UNIQUE (token_hash),
	CONSTRAINT fk_local_recovery_identity FOREIGN KEY(identity_seq) REFERENCES local_identity (seq),
	KEY ix_local_recovery_token_identity (identity_seq, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_recovery_token")

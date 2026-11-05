"""Create rotating refresh tokens (hash only); one reversible DDL."""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_refresh_token (
	id BINARY(16) NOT NULL,
	family_id BINARY(16) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	identity_seq INT NOT NULL,
	client_id VARCHAR(64) NOT NULL,
	scope VARCHAR(512) NOT NULL,
	authenticated_at DATETIME(6) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	rotated_at DATETIME(6) NULL,
	revoked_at DATETIME(6) NULL,
	CONSTRAINT pk_local_refresh_token PRIMARY KEY (id),
	CONSTRAINT uq_local_refresh_token_hash UNIQUE (token_hash),
	CONSTRAINT fk_local_refresh_identity FOREIGN KEY(identity_seq) REFERENCES local_identity (seq),
	KEY ix_local_refresh_token_family (family_id),
	KEY ix_local_refresh_token_identity (identity_seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_refresh_token")

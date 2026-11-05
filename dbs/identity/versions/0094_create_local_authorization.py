"""Create authorization requests and one-use codes (hash only); one reversible DDL."""
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_authorization (
	request_hash VARCHAR(64) NOT NULL,
	client_id VARCHAR(64) NOT NULL,
	redirect_uri VARCHAR(2048) NOT NULL,
	scope VARCHAR(512) NOT NULL,
	state VARCHAR(512) NOT NULL,
	nonce VARCHAR(255) NOT NULL,
	code_challenge VARCHAR(43) NOT NULL,
	max_age INT NULL,
	created_at DATETIME(6) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	identity_seq INT NULL,
	code_hash VARCHAR(64) NULL,
	authenticated_at DATETIME(6) NULL,
	consumed_at DATETIME(6) NULL,
	family_id BINARY(16) NULL,
	CONSTRAINT pk_local_authorization PRIMARY KEY (request_hash),
	CONSTRAINT uq_local_authorization_code UNIQUE (code_hash),
	CONSTRAINT fk_local_authorization_identity FOREIGN KEY(identity_seq) REFERENCES local_identity (seq),
	KEY ix_local_authorization_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_authorization")

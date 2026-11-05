"""Create the local provider's signing keys (private half encrypted); one reversible DDL."""
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_signing_key (
	kid VARCHAR(64) NOT NULL,
	status VARCHAR(12) NOT NULL,
	public_jwk TEXT NOT NULL,
	private_jwk_ciphertext TEXT NOT NULL,
	created_at DATETIME(6) NOT NULL,
	retired_at DATETIME(6) NULL,
	CONSTRAINT pk_local_signing_key PRIMARY KEY (kid),
	CONSTRAINT ck_local_signing_key_status CHECK (status IN ('active','retiring','retired'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_signing_key")

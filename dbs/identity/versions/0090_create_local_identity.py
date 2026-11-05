"""Create the local authentication identities; one reversible DDL."""
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE local_identity (
	seq INT NOT NULL AUTO_INCREMENT,
	uid BINARY(16) NOT NULL,
	sub VARCHAR(64) NOT NULL,
	email VARCHAR(320) NOT NULL,
	name VARCHAR(200) NOT NULL,
	username VARCHAR(150) NOT NULL,
	country_code VARCHAR(2) NOT NULL,
	state_code VARCHAR(6) NOT NULL,
	workspace_name VARCHAR(200) NULL,
	path VARCHAR(40) NOT NULL,
	status VARCHAR(16) NOT NULL,
	email_verified_at DATETIME(6) NULL,
	review_command VARCHAR(36) NULL,
	provision_command VARCHAR(36) NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	last_login_at DATETIME(6) NULL,
	CONSTRAINT pk_local_identity PRIMARY KEY (seq),
	CONSTRAINT uq_local_identity_uid UNIQUE (uid),
	CONSTRAINT uq_local_identity_sub UNIQUE (sub),
	CONSTRAINT uq_local_identity_email UNIQUE (email),
	CONSTRAINT uq_local_identity_username UNIQUE (username),
	CONSTRAINT ck_local_identity_status CHECK (status IN ('pending','active','disabled')),
	KEY ix_local_identity_path_status (path, status, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE local_identity")

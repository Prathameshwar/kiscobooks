"""Single-use invitation state. One atomic DDL per direction."""
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE user_invitation (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    accepted_at DATETIME(6) NULL,
    cancelled_at DATETIME(6) NULL,
    pending_user_id BINARY(16) GENERATED ALWAYS AS
        (CASE WHEN status = 'pending' THEN user_id ELSE NULL END) STORED,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_user_invitation PRIMARY KEY (id),
    KEY ix_user_invitation_tenant_id (tenant_id),
    KEY ix_user_invitation_user_owner (tenant_id, user_id),
    CONSTRAINT uq_user_invitation_pending UNIQUE (pending_user_id),
    CONSTRAINT fk_user_invitation_user_owner FOREIGN KEY (tenant_id, user_id)
        REFERENCES user (tenant_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
""")


def downgrade() -> None:
    op.execute("DROP TABLE user_invitation")

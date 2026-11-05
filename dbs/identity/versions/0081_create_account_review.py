"""Platform applicant projection; one atomic CREATE TABLE, reversible."""
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE account_review (
id BINARY(16) NOT NULL,
tenant_id BINARY(16) NOT NULL,
provider_uuid BINARY(16) NOT NULL,
provider_id INTEGER NOT NULL,
name VARCHAR(200) NOT NULL,
username VARCHAR(150) NOT NULL,
email VARCHAR(320) NOT NULL,
country_code VARCHAR(2) NOT NULL,
state_code VARCHAR(6) NOT NULL,
status VARCHAR(20) NOT NULL,
provider_active BOOLEAN NOT NULL,
provider_verified BOOLEAN NOT NULL,
fingerprint VARCHAR(64) NOT NULL,
version INTEGER NOT NULL,
needs_attention BOOLEAN NOT NULL,
created_at DATETIME(6) NOT NULL,
created_by BINARY(16),
updated_at DATETIME(6) NOT NULL,
updated_by BINARY(16),
PRIMARY KEY (id), UNIQUE KEY uq_account_review_owner (tenant_id,id),
UNIQUE KEY uq_account_review_provider (tenant_id,provider_uuid), KEY ix_account_review_tenant_id (tenant_id),
KEY ix_account_review_name (tenant_id,name,id), KEY ix_account_review_email (tenant_id,email,id),
KEY ix_account_review_username (tenant_id,username,id), KEY ix_account_review_status (tenant_id,status,created_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE account_review")

"""Private Purchase file registrations; one atomic CREATE statement."""

from alembic import op
from sqlalchemy import text

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE purchase_supporting_file (
        voucher_id BINARY(16) NOT NULL, object_key VARCHAR(200) NOT NULL,
        content_hash VARCHAR(64) NOT NULL, media_type VARCHAR(60) NOT NULL,
        size_bytes INTEGER NOT NULL, filename VARCHAR(160) NOT NULL,
        company_id BINARY(16) NOT NULL, row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_purchase_supporting_file PRIMARY KEY (id),
        CONSTRAINT ck_purchase_supporting_file_size CHECK (size_bytes > 0 AND size_bytes <= 10485760),
        CONSTRAINT ck_purchase_supporting_file_hash CHECK (LENGTH(content_hash) = 64),
        CONSTRAINT uq_purchase_file_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT uq_purchase_file_content
            UNIQUE (tenant_id, company_id, voucher_id, content_hash),
        CONSTRAINT fk_purchase_supporting_file_voucher FOREIGN KEY (tenant_id, company_id, voucher_id)
            REFERENCES voucher (tenant_id, company_id, id),
        KEY ix_purchase_supporting_file_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM purchase_supporting_file LIMIT 1")).first():
        raise RuntimeError("retain Purchase supporting files before downgrade")
    op.execute("DROP TABLE purchase_supporting_file")

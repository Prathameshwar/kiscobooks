"""Indexed dated unit admission evidence; one CREATE statement."""

from alembic import op
from sqlalchemy import text

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE voucher_item_unit_projection (
        source_id BINARY(16) NOT NULL, item_id BINARY(16) NOT NULL,
        unit_id BINARY(16) NOT NULL, valid_from DATE NOT NULL, valid_to DATE,
        source_version BIGINT NOT NULL, facts JSON NOT NULL, content_hash VARCHAR(64) NOT NULL,
        company_id BINARY(16) NOT NULL, row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_voucher_item_unit_projection PRIMARY KEY (id),
        CONSTRAINT uq_voucher_item_unit_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT uq_voucher_item_unit_source UNIQUE (tenant_id, company_id, source_id),
        CONSTRAINT ck_voucher_item_unit_projection_item_unit_source_version CHECK (source_version > 0),
        CONSTRAINT ck_voucher_item_unit_projection_item_unit_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
        KEY ix_voucher_item_unit_date (tenant_id, company_id, item_id, unit_id, valid_from, id),
        KEY ix_voucher_item_unit_projection_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM voucher_item_unit_projection LIMIT 1")).first():
        raise RuntimeError("archive retained unit source evidence before downgrade")
    op.execute("DROP TABLE voucher_item_unit_projection")

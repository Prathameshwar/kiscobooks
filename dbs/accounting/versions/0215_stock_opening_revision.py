"""Retain immutable reviewed manifest revisions; one atomic CREATE TABLE."""

from alembic import op
from sqlalchemy import text

revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_revision (
        control_id BINARY(16) NOT NULL, revision INTEGER NOT NULL,
        manifest JSON NOT NULL, manifest_hash VARCHAR(64) NOT NULL,
        currency VARCHAR(3) NOT NULL, company_id BINARY(16) NOT NULL,
        row_version INTEGER NOT NULL, id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_stock_opening_revision PRIMARY KEY (id),
        CONSTRAINT uq_stock_opening_revision_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT ck_stock_opening_revision_stock_opening_revision_version CHECK (row_version > 0),
        CONSTRAINT fk_opening_revision_control FOREIGN KEY (tenant_id, company_id, control_id)
            REFERENCES stock_opening_control (tenant_id, company_id, id),
        CONSTRAINT uq_opening_revision_number UNIQUE (tenant_id, company_id, control_id, revision),
        KEY ix_stock_opening_revision_page (tenant_id, company_id, id),
        KEY ix_stock_opening_revision_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_opening_revision LIMIT 1")).first():
        raise RuntimeError("archive retained manifest revisions before downgrade")
    op.execute("DROP TABLE stock_opening_revision")

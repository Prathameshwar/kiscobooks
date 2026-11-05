"""Pin the product's optional batch choice; one CREATE TABLE."""

import sqlalchemy as sa
from alembic import op

revision = "0220"
down_revision = "0219"
branch_labels = None
depends_on = None


_CREATE = """
CREATE TABLE item_stock_choice (
 id BINARY(16) NOT NULL PRIMARY KEY,
 tenant_id BINARY(16) NOT NULL,
 company_id BINARY(16) NOT NULL,
 item_id BINARY(16) NOT NULL,
 batch_enabled BOOLEAN NOT NULL,
 row_version INTEGER NOT NULL,
 created_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 created_by BINARY(16) NULL,
 updated_by BINARY(16) NULL,
 CONSTRAINT uq_stock_choice_scope UNIQUE (tenant_id, company_id, id),
 CONSTRAINT uq_stock_choice_item UNIQUE (tenant_id, company_id, item_id),
 CONSTRAINT fk_stock_choice_item FOREIGN KEY (tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
 CONSTRAINT ck_item_stock_choice_stock_choice_version CHECK (row_version >= 1),
 INDEX ix_item_stock_choice_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM item_stock_choice")):
        raise RuntimeError("retain product tracking choices after use")
    op.execute("DROP TABLE item_stock_choice")

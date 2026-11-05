"""Create platform_price_revision; commercial defaults are deployment seeds."""

from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE platform_price_revision (
	price_id BINARY(16) NOT NULL,
	version INTEGER NOT NULL,
	snapshot JSON NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	id BINARY(16) NOT NULL,
	CONSTRAINT pk_platform_price_revision PRIMARY KEY (id),
	CONSTRAINT uq_platform_price_revision_version UNIQUE (price_id, version),
	CONSTRAINT fk_platform_price_revision_price_id FOREIGN KEY(price_id) REFERENCES platform_price (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE platform_price_revision")

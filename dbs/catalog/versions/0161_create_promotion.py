"""Create promotion; one DDL statement."""

from alembic import op

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion (
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	row_version INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion PRIMARY KEY (id),
	CONSTRAINT uq_promotion_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_promotion_code UNIQUE (tenant_id, company_id, code),
	CONSTRAINT ck_promotion_version CHECK (row_version >= 1),
	KEY ix_promotion_name (tenant_id, company_id, name, id),
	KEY ix_promotion_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion")

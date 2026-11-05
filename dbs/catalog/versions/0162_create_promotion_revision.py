"""Create promotion_revision; one DDL statement."""

from alembic import op

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_revision (
	promotion_id BINARY(16) NOT NULL,
	version INTEGER NOT NULL,
	trigger_mode VARCHAR(12) NOT NULL,
	selection_mode VARCHAR(24) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	starts_at DATETIME(6) NOT NULL,
	ends_at DATETIME(6) NOT NULL,
	timezone VARCHAR(64) NOT NULL,
	stack_policy_revision_id BINARY(16) NOT NULL,
	stack_group_id BINARY(16) NOT NULL,
	return_policy_revision_id BINARY(16) NOT NULL,
	priority INTEGER NOT NULL,
	policy_generation BIGINT NOT NULL,
	source_version BIGINT NOT NULL,
	published_at DATETIME(6) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_revision PRIMARY KEY (id),
	CONSTRAINT uq_promotion_revision_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_promotion_revision_number UNIQUE (tenant_id, company_id, promotion_id, version),
    CONSTRAINT fk_promotion_revision_parent FOREIGN KEY(tenant_id, company_id, promotion_id)
        REFERENCES promotion (tenant_id, company_id, id),
    CONSTRAINT fk_promotion_revision_return_policy FOREIGN KEY(tenant_id, company_id,
        return_policy_revision_id) REFERENCES return_policy_revision (tenant_id, company_id, id),
	CONSTRAINT ck_promotion_revision_version CHECK (version >= 1),
	CONSTRAINT ck_promotion_revision_trigger CHECK (trigger_mode = 'AUTOMATIC'),
	CONSTRAINT ck_promotion_revision_selection CHECK (selection_mode = 'SNAPSHOT_ON_PUBLISH'),
	CONSTRAINT ck_promotion_revision_window CHECK (starts_at < ends_at),
	CONSTRAINT ck_promotion_revision_priority CHECK (priority BETWEEN 0 AND 32767),
	CONSTRAINT ck_promotion_revision_lineage CHECK (policy_generation >= 1 AND source_version >= 1),
	CONSTRAINT ck_promotion_revision_hash CHECK (LENGTH(source_sha256) = 64),
	KEY ix_promotion_revision_tenant_id (tenant_id),
	KEY ix_promotion_revision_window (tenant_id, company_id, starts_at, ends_at, id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_revision")

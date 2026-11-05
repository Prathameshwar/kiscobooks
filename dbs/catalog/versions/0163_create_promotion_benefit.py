"""Create promotion_benefit; one DDL statement."""

from alembic import op

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_benefit (
	revision_id BINARY(16) NOT NULL,
	kind VARCHAR(20) NOT NULL,
	pool VARCHAR(20) NOT NULL,
	unit_revision_id BINARY(16) NOT NULL,
	qualifying_quantity NUMERIC(19,4) NOT NULL,
	reward_quantity NUMERIC(19,4) NOT NULL,
	reward_percent NUMERIC(19,8) NOT NULL,
	maximum_repeats INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_benefit PRIMARY KEY (id),
	CONSTRAINT uq_promotion_benefit_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_promotion_benefit_revision UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_promotion_benefit_revision FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES promotion_revision (tenant_id, company_id, id),
    CONSTRAINT fk_promotion_benefit_unit FOREIGN KEY(tenant_id, company_id, unit_revision_id)
        REFERENCES item_unit_revision (tenant_id, company_id, id),
	CONSTRAINT ck_promotion_benefit_kind CHECK (kind = 'BUY_GET' AND pool = 'SAME_ITEM'),
    CONSTRAINT ck_promotion_benefit_amounts CHECK (qualifying_quantity > 0 AND
        reward_quantity > 0 AND reward_percent = 100 AND maximum_repeats BETWEEN 1 AND 1000),
	KEY ix_promotion_benefit_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE promotion_benefit")

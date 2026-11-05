"""Import effect claims written with each draft; one DDL statement."""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

CREATE = """
CREATE TABLE voucher_import_effect (
	job_id BINARY(16) NOT NULL,
	import_key VARCHAR(64) NOT NULL,
	voucher_id BINARY(16) NOT NULL,
	revision_id BINARY(16) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_voucher_import_effect PRIMARY KEY (id),
	CONSTRAINT fk_voucher_import_effect_job FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES voucher_import_job (tenant_id, company_id, id),
	CONSTRAINT uq_voucher_import_effect_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_voucher_import_effect_voucher FOREIGN KEY(tenant_id, company_id, voucher_id) REFERENCES voucher (tenant_id, company_id, id),
	CONSTRAINT uq_voucher_import_effect_key UNIQUE (tenant_id, company_id, job_id, import_key),
	KEY ix_voucher_import_effect_tenant_id (tenant_id),
	KEY ix_voucher_import_effect_voucher (tenant_id, company_id, voucher_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_import_effect")

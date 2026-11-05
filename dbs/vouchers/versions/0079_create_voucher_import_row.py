"""Staged import vouchers and their validation results; one DDL statement."""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

CREATE = """
CREATE TABLE voucher_import_row (
	job_id BINARY(16) NOT NULL,
	import_key VARCHAR(64) NOT NULL,
	ordinal INTEGER NOT NULL,
	state VARCHAR(20) NOT NULL,
	source_input JSON NOT NULL,
	source_rows JSON NOT NULL,
	errors JSON NOT NULL,
	prepared_input JSON,
	configuration_hash VARCHAR(64),
	currency VARCHAR(3),
	declared_total NUMERIC(19, 4),
	computed_payable NUMERIC(19, 4),
	computed_tax_total NUMERIC(19, 4),
	supplier_difference NUMERIC(19, 4),
	voucher_id BINARY(16),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_voucher_import_row PRIMARY KEY (id),
	CONSTRAINT ck_voucher_import_row_state CHECK (state IN ('STAGED', 'VALID', 'WARNING', 'INVALID', 'BLOCKED', 'CREATED', 'FAILED', 'NOT_SELECTED')),
	CONSTRAINT fk_voucher_import_row_job FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES voucher_import_job (tenant_id, company_id, id),
	CONSTRAINT uq_voucher_import_row_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_voucher_import_row_ordinal CHECK (ordinal BETWEEN 1 AND 500),
	CONSTRAINT uq_voucher_import_row_key UNIQUE (tenant_id, company_id, job_id, import_key),
	KEY ix_voucher_import_row_page (tenant_id, company_id, job_id, ordinal, id),
	KEY ix_voucher_import_row_tenant_id (tenant_id),
	KEY ix_voucher_import_row_work (tenant_id, company_id, job_id, state, ordinal)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_import_row")

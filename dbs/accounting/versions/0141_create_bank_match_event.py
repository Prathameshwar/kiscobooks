"""Create bank_match_event as one DDL statement."""

from alembic import op

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_match_event (
	statement_entry_id BINARY(16) NOT NULL,
	instrument_id BINARY(16) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	bank_date DATE NOT NULL,
	group_id BINARY(16) NOT NULL,
	reverses_id BINARY(16),
	reason VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_match_event PRIMARY KEY (id),
	CONSTRAINT uq_bank_match_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bank_match_entry FOREIGN KEY(tenant_id, company_id, statement_entry_id) REFERENCES bank_statement_entry (tenant_id, company_id, id),
	CONSTRAINT fk_bank_match_instrument FOREIGN KEY(tenant_id, company_id, instrument_id) REFERENCES bank_instrument (tenant_id, company_id, id),
	CONSTRAINT fk_bank_match_reversal FOREIGN KEY(tenant_id, company_id, reverses_id) REFERENCES bank_match_event (tenant_id, company_id, id),
	CONSTRAINT uq_bank_match_reversal UNIQUE (tenant_id, company_id, reverses_id),
	CONSTRAINT ck_bank_match_event_bank_match_amount CHECK (amount > 0)
,
	KEY ix_bank_match_event_tenant_id (tenant_id),
	KEY ix_match_instrument (tenant_id, company_id, instrument_id, id),
	KEY ix_match_statement (tenant_id, company_id, statement_entry_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_match_event")

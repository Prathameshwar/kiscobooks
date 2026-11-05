"""bank_instrument_event; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE bank_instrument_event (
    instrument_id BINARY(16) NOT NULL,
    action VARCHAR(20) NOT NULL,
    event_date DATE NOT NULL,
    reference VARCHAR(120),
    reason VARCHAR(500) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_bank_instrument_event PRIMARY KEY (id),
    CONSTRAINT uq_bank_instrument_event_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT fk_bank_event_instrument FOREIGN KEY(tenant_id, company_id, instrument_id) REFERENCES bank_instrument (tenant_id, company_id, id),
    CONSTRAINT ck_bank_instrument_event_bank_event_action CHECK (action IN ('BOOKED', 'PRESENTED', 'CLEARED', 'DISHONOURED', 'RECONCILED', 'UNRECONCILED', 'REVERSED')),
    INDEX ix_bank_event_history (tenant_id, company_id, instrument_id, event_date, id),
    INDEX ix_bank_instrument_event_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_instrument_event")

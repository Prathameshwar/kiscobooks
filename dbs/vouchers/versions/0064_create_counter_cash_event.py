"""Append-only physical drawer movements; one DDL statement."""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE counter_cash_event (
    session_id BINARY(16) NOT NULL,
    source_voucher_id BINARY(16) NOT NULL,
    source_revision_id BINARY(16) NOT NULL,
    event_key BINARY(16) NOT NULL,
    direction VARCHAR(3) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    amount DECIMAL(19,4) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    operator_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_counter_cash_event PRIMARY KEY (id),
    CONSTRAINT uq_counter_cash_event_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_counter_cash_event_key UNIQUE (tenant_id, company_id, session_id, event_key),
    CONSTRAINT uq_counter_cash_source UNIQUE (tenant_id, company_id, source_revision_id),
    CONSTRAINT fk_counter_cash_event_session FOREIGN KEY (tenant_id, company_id, session_id)
        REFERENCES counter_session (tenant_id, company_id, id),
    CONSTRAINT fk_counter_cash_event_voucher FOREIGN KEY (tenant_id, company_id, source_voucher_id)
        REFERENCES voucher (tenant_id, company_id, id),
    CONSTRAINT fk_counter_cash_event_revision FOREIGN KEY (tenant_id, company_id, source_revision_id)
        REFERENCES voucher_revision (tenant_id, company_id, id),
    CONSTRAINT ck_counter_cash_event_counter_cash_event_amount CHECK (amount > 0),
    CONSTRAINT ck_counter_cash_event_counter_cash_event_direction CHECK (direction IN ('IN','OUT')),
    KEY ix_counter_cash_event_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE counter_cash_event")

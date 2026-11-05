"""One open session per counter enforced by a nullable generated unique key."""

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE counter_session (
    counter_id BINARY(16) NOT NULL,
    status VARCHAR(20) NOT NULL,
    open_counter_id BINARY(16) GENERATED ALWAYS AS
        (CASE WHEN status = 'OPEN' THEN counter_id ELSE NULL END) STORED,
    currency VARCHAR(3) NOT NULL,
    opened_at DATETIME(6) NOT NULL,
    opened_by BINARY(16) NOT NULL,
    opening_cash DECIMAL(19,4) NOT NULL,
    closed_at DATETIME(6) NULL,
    closed_by BINARY(16) NULL,
    counted_cash DECIMAL(19,4) NULL,
    expected_cash DECIMAL(19,4) NULL,
    variance DECIMAL(19,4) NULL,
    close_reason VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_counter_session PRIMARY KEY (id),
    CONSTRAINT uq_counter_session_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_counter_open UNIQUE (tenant_id, company_id, open_counter_id),
    CONSTRAINT fk_counter_session_counter FOREIGN KEY (tenant_id, company_id, counter_id)
        REFERENCES checkout_counter (tenant_id, company_id, id),
    CONSTRAINT ck_counter_session_counter_session_status CHECK (status IN ('OPEN','CLOSED')),
    KEY ix_counter_session_counter (tenant_id, company_id, counter_id, id),
    KEY ix_counter_session_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE counter_session")

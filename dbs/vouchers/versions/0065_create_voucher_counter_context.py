"""Immutable revision-to-counter context; one DDL statement."""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE voucher_counter_context (
    revision_id BINARY(16) NOT NULL,
    counter_id BINARY(16) NOT NULL,
    session_id BINARY(16) NULL,
    cashier_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_voucher_counter_context PRIMARY KEY (id),
    CONSTRAINT uq_voucher_counter_context_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_counter_context_revision UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_voucher_counter_context_revision FOREIGN KEY (tenant_id, company_id, revision_id)
        REFERENCES voucher_revision (tenant_id, company_id, id),
    CONSTRAINT fk_voucher_counter_context_counter FOREIGN KEY (tenant_id, company_id, counter_id)
        REFERENCES checkout_counter (tenant_id, company_id, id),
    CONSTRAINT fk_voucher_counter_context_session FOREIGN KEY (tenant_id, company_id, session_id)
        REFERENCES counter_session (tenant_id, company_id, id),
    KEY ix_voucher_counter_context_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE voucher_counter_context")

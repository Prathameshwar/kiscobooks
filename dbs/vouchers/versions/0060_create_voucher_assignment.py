"""Optional commercial assignments on shared voucher revisions."""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE voucher_assignment (
    revision_id BINARY(16) NOT NULL,
    role VARCHAR(20) NOT NULL,
    line_key BINARY(16) NULL,
    principal_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    share DECIMAL(7,4) NOT NULL,
    source_revision_id BINARY(16) NULL,
    override_reason VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_voucher_assignment PRIMARY KEY (id),
    CONSTRAINT uq_voucher_assignment_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_assignment_person UNIQUE
        (tenant_id, company_id, revision_id, role, line_key, principal_id),
    CONSTRAINT fk_voucher_assignment_revision FOREIGN KEY
        (tenant_id, company_id, revision_id)
        REFERENCES voucher_revision (tenant_id, company_id, id),
    CONSTRAINT ck_voucher_assignment_voucher_assignment_share CHECK (share > 0 AND share <= 100),
    CONSTRAINT ck_voucher_assignment_voucher_assignment_role CHECK
        (role IN ('SELLER','BROKER','COLLECTOR','RETURN_HANDLER','PAYMENT_HANDLER')),
    KEY ix_voucher_assignment_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE voucher_assignment")

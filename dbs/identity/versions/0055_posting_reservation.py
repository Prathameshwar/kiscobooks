"""Durable company freeze before a Billing transaction. One DDL per direction."""
from alembic import op
from sqlalchemy import text
revision="0055"
down_revision="0054"
branch_labels=None
depends_on=None

def upgrade() -> None:
    op.execute("""CREATE TABLE posting_reservation (
        id BINARY(16) NOT NULL,
        tenant_id BINARY(16) NOT NULL,
        company_id BINARY(16) NOT NULL,
        operation_id BINARY(16) NOT NULL,
        actor_user_id BINARY(16) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        configuration_hash VARCHAR(64) NOT NULL,
        features JSON NOT NULL,
        status VARCHAR(20) NOT NULL,
        confirmed_at DATETIME(6) NULL,
        aborted_at DATETIME(6) NULL,
        terminal_reference VARCHAR(120) NULL,
        created_at DATETIME(6) NOT NULL,
        created_by BINARY(16) NULL,
        updated_at DATETIME(6) NOT NULL,
        updated_by BINARY(16) NULL,
        CONSTRAINT pk_posting_reservation PRIMARY KEY (id),
        KEY ix_posting_reservation_tenant_id (tenant_id),
        UNIQUE KEY uq_posting_reservation_operation (tenant_id,company_id,operation_id),
        KEY ix_posting_reservation_pending (tenant_id,company_id,status),
        CONSTRAINT fk_posting_reservation_company_owner FOREIGN KEY (tenant_id,company_id) REFERENCES company(tenant_id,id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")

def downgrade() -> None:
    # An operator must reconcile every pending freeze before removing this safety state.
    if op.get_bind().execute(text("SELECT id FROM posting_reservation LIMIT 1")).first():
        raise RuntimeError("reconcile and archive posting reservations before a reviewed downgrade")
    op.execute("DROP TABLE posting_reservation")

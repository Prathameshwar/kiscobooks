"""Separate delegated stock authority on the common reservation; one atomic ALTER."""

from alembic import op
import sqlalchemy as sa

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE posting_reservation
    ADD COLUMN authority_kind VARCHAR(16) NOT NULL DEFAULT 'GENERAL',
    ADD COLUMN source_execution_id BINARY(16) NULL,
    ADD COLUMN source_command_hash VARCHAR(64) NULL,
    ADD COLUMN source_action VARCHAR(10) NULL,
    ADD CONSTRAINT uq_posting_reservation_stock_execution UNIQUE (tenant_id, company_id, source_execution_id),
    ADD CONSTRAINT ck_posting_reservation_posting_reservation_authority CHECK (
        (authority_kind = 'GENERAL' AND source_execution_id IS NULL AND source_command_hash IS NULL AND source_action IS NULL)
        OR (authority_kind = 'STOCK' AND source_execution_id IS NOT NULL AND source_command_hash IS NOT NULL AND source_action IS NOT NULL AND source_action IN ('POST','REVERSE'))
    )""")


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT 1 FROM posting_reservation WHERE authority_kind = 'STOCK' LIMIT 1"
        )
    ):
        raise RuntimeError("Retained stock reservation authority prevents downgrade")
    op.execute("""ALTER TABLE posting_reservation
    DROP CHECK ck_posting_reservation_posting_reservation_authority,
    DROP INDEX uq_posting_reservation_stock_execution,
    DROP COLUMN source_action,
    DROP COLUMN source_command_hash,
    DROP COLUMN source_execution_id,
    DROP COLUMN authority_kind""")

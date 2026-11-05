"""Private Azure document lifecycle and tenant-safe ownership; one atomic ALTER."""
from alembic import op
from sqlalchemy import text

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE company_document
        ADD COLUMN storage_state VARCHAR(16) NOT NULL DEFAULT 'legacy',
        ADD COLUMN content_sha256 VARCHAR(64) NULL,
        ADD COLUMN blob_snapshot VARCHAR(80) NULL,
        ADD COLUMN upload_expires_at DATETIME(6) NULL,
        ADD COLUMN finalized_at DATETIME(6) NULL,
        ADD INDEX ix_company_document_pending (tenant_id, company_id, storage_state, upload_expires_at),
        DROP FOREIGN KEY fk_company_document_company_id,
        ADD CONSTRAINT fk_company_document_owner FOREIGN KEY (tenant_id, company_id) REFERENCES company (tenant_id, id)""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM company_document WHERE storage_state <> 'legacy' LIMIT 1")).first():
        raise RuntimeError("archive or reconcile Azure document references before downgrade")
    op.execute("""ALTER TABLE company_document
        DROP FOREIGN KEY fk_company_document_owner,
        ADD CONSTRAINT fk_company_document_company_id FOREIGN KEY (company_id) REFERENCES company (id),
        DROP INDEX ix_company_document_pending,
        DROP COLUMN storage_state,
        DROP COLUMN content_sha256,
        DROP COLUMN blob_snapshot,
        DROP COLUMN upload_expires_at,
        DROP COLUMN finalized_at""")

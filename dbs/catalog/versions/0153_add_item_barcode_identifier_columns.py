"""Widen ``item_barcode`` with ``identifier_type_code``/``namespace_code``; one DDL.

Nullable additions with composite FKs to the two new masters. Existing rows
keep their ``symbology`` semantics — a ``symbology`` of ``GTIN`` / ``CODE128`` /
``QR`` still identifies a barcode; the new ``identifier_type_code`` extends the
same row to non-barcode identifiers such as ``MPN`` or ``SKU``.

The table keeps its ``item_barcode`` name for one v1 cycle; a follow-up
migration renames it to ``product_identifier`` once every consumer is off the
older client (see catalog-v1-completion-plan.md §4 Phase 5).
"""

from alembic import op

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE item_barcode "
    "ADD COLUMN identifier_type_code VARCHAR(30) NULL, "
    "ADD COLUMN namespace_code VARCHAR(40) NULL, "
    "ADD CONSTRAINT fk_item_barcode_identifier_type "
    "FOREIGN KEY (tenant_id, company_id, identifier_type_code) "
    "REFERENCES identifier_type (tenant_id, company_id, code), "
    "ADD CONSTRAINT fk_item_barcode_namespace "
    "FOREIGN KEY (tenant_id, company_id, namespace_code) "
    "REFERENCES identifier_namespace (tenant_id, company_id, code)"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE item_barcode "
        "DROP FOREIGN KEY fk_item_barcode_identifier_type, "
        "DROP FOREIGN KEY fk_item_barcode_namespace, "
        "DROP COLUMN identifier_type_code, "
        "DROP COLUMN namespace_code"
    )

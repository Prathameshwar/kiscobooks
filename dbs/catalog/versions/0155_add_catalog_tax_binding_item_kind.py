"""Key company-scope and ``BOTH``-group tax bindings by product kind; one DDL.

``item_kind`` is nullable: NULL keeps the existing meaning, a binding that applies to
every kind its scope admits (all legacy rows, and any scope fixed to one kind). A goods
default and a services default can now coexist on the same company or ``BOTH`` group.
No index is added: resolution reads the existing
``(tenant_id, company_id, scope_id, direction, bundle, valid_from)`` prefix and filters
the few dated rows by kind.

Downgrade drops the column and loses which kind each keyed binding served; two kinded
defaults on one scope would then overlap, so downgrade only before any are published.
"""

from alembic import op

revision = "0155"
down_revision = "0154"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE catalog_tax_binding "
    "ADD COLUMN item_kind VARCHAR(7) NULL, "
    "ADD CONSTRAINT ck_catalog_tax_binding_item_kind "
    "CHECK (item_kind IS NULL OR item_kind IN ('GOODS','SERVICE'))"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_tax_binding "
        "DROP CHECK ck_catalog_tax_binding_item_kind, "
        "DROP COLUMN item_kind"
    )

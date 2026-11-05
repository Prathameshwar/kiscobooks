"""Permit an external party to be eligible as a commercial broker."""

from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE party_role DROP CHECK ck_party_role_party_role_role, ADD CONSTRAINT ck_party_role_party_role_role CHECK (role IN ('CUSTOMER','SUPPLIER','OTHER','BROKER'))")


def downgrade() -> None:
    # Historical BROKER rows must be removed before a downgrade can restore the old check.
    op.execute("ALTER TABLE party_role DROP CHECK ck_party_role_party_role_role, ADD CONSTRAINT ck_party_role_party_role_role CHECK (role IN ('CUSTOMER','SUPPLIER','OTHER'))")

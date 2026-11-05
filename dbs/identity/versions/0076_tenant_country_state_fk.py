"""The database rejects a tenant state from a different country."""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tenant ADD CONSTRAINT fk_tenant_default_country_state "
        "FOREIGN KEY (default_country_code, default_state_code) "
        "REFERENCES state (country_code, code)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tenant DROP FOREIGN KEY fk_tenant_default_country_state")

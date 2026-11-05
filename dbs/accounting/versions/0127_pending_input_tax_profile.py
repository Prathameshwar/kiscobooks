"""Separate purchase tax pending verification from eligible input credit; one ALTER."""

from alembic import op

revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None

OLD = "'INPUT_RECOVERABLE', 'OUTPUT_PAYABLE', 'RCM_PAYABLE', 'DEPOSIT', 'ADJUSTMENT'"
NEW = (
    "'INPUT_RECOVERABLE', 'INPUT_PENDING', 'OUTPUT_PAYABLE', 'RCM_PAYABLE', 'DEPOSIT', 'ADJUSTMENT'"
)
NAME = "ck_account_tax_profile_account_tax_profile_purpose"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE account_tax_profile DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (purpose IN ({NEW}))"
    )


def downgrade() -> None:
    # Refuse if pending-credit profiles exist; never relabel financial history.
    op.execute(
        f"ALTER TABLE account_tax_profile DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (purpose IN ({OLD}))"
    )

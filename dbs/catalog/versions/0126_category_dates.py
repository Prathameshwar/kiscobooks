"""Date family categories while preserving legacy membership IDs.

The date columns are retained history. Dropping them could turn closed memberships
into current ones; downgrade past this revision is deliberately unsupported.
"""
from alembic import op

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE family_category ADD COLUMN valid_from DATE NOT NULL DEFAULT '1000-01-01', ADD COLUMN valid_to DATE NULL, ADD CONSTRAINT ck_family_category_p72_date_floor CHECK (valid_from >= '1000-01-01'), ADD CONSTRAINT ck_family_category_p72_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), ADD INDEX ix_p72_asof (tenant_id, company_id, family_id, valid_from, valid_to, id), ADD INDEX ix_p72_scheme (tenant_id, company_id, scheme_id, valid_to, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    raise NotImplementedError("category membership dates are retained history; use a forward migration")

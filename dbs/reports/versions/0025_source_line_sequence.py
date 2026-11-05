"""Generated line ordering from retained JSON; one additive DDL statement."""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE report_fact_version ADD COLUMN line_sequence BIGINT "
               "GENERATED ALWAYS AS (CASE WHEN entity = 'journal_line' THEN "
               "CAST(json_extract(data, '$.sequence') AS SIGNED) ELSE NULL END) STORED")


def downgrade() -> None:
    op.execute("ALTER TABLE report_fact_version DROP COLUMN line_sequence")

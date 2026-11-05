"""Catalog currency: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE currency (
    code CHAR(3) NOT NULL,
    numeric_code CHAR(3) NOT NULL,
    name VARCHAR(100) NOT NULL,
    symbol VARCHAR(8) NOT NULL,
    minor_unit TINYINT NOT NULL,
    major_unit_name VARCHAR(40) NOT NULL,
    minor_unit_name VARCHAR(40) NULL,
    minor_unit_name_plural VARCHAR(40) NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_currency PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE currency")

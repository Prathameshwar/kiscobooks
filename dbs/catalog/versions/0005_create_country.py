"""Catalog country: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE country (
    code CHAR(2) NOT NULL,
    iso3 CHAR(3) NOT NULL,
    numeric_code CHAR(3) NOT NULL,
    name VARCHAR(100) NOT NULL,
    official_name VARCHAR(200) NOT NULL,
    default_currency_code CHAR(3) NOT NULL,
    phone_prefix VARCHAR(8) NOT NULL,
    subdivision_label VARCHAR(60) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_country PRIMARY KEY (code),
    CONSTRAINT fk_country_default_currency_code
        FOREIGN KEY (default_currency_code) REFERENCES currency (code),
    KEY ix_country_default_currency_code (default_currency_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE country")

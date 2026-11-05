"""Catalog state: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE state (
    code VARCHAR(6) NOT NULL,
    country_code CHAR(2) NOT NULL,
    name VARCHAR(100) NOT NULL,
    subdivision_type VARCHAR(60) NOT NULL,
    tax_jurisdiction_code VARCHAR(8) NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_state PRIMARY KEY (code),
    CONSTRAINT uq_state_country_code_code UNIQUE (country_code, code),
    CONSTRAINT fk_state_country_code FOREIGN KEY (country_code) REFERENCES country (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE state")

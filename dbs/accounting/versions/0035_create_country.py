"""Create country; seed data is applied separately."""
from alembic import op
revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None
CREATE = 'CREATE TABLE country (\n\tcode CHAR(2) NOT NULL, \n\tiso3 CHAR(3) NOT NULL, \n\tnumeric_code CHAR(3) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tofficial_name VARCHAR(200) NOT NULL, \n\tdefault_currency_code CHAR(3) NOT NULL, \n\tphone_prefix VARCHAR(8) NOT NULL, \n\tsubdivision_label VARCHAR(60) NOT NULL, \n\tis_active BOOL NOT NULL, \n\tCONSTRAINT pk_country PRIMARY KEY (code), \n\tCONSTRAINT fk_country_default_currency_code FOREIGN KEY(default_currency_code) REFERENCES currency (code),\nKEY ix_country_default_currency_code (default_currency_code)\n)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
def upgrade() -> None:
    op.execute(CREATE)
def downgrade() -> None:
    op.execute("DROP TABLE country")

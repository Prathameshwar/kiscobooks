"""Create state; seed data is applied separately."""
from alembic import op
revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None
CREATE = 'CREATE TABLE state (\n\tcode VARCHAR(6) NOT NULL, \n\tcountry_code CHAR(2) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tsubdivision_type VARCHAR(60) NOT NULL, \n\ttax_jurisdiction_code VARCHAR(8), \n\tis_active BOOL NOT NULL, \n\tCONSTRAINT pk_state PRIMARY KEY (code), \n\tCONSTRAINT fk_state_country_code FOREIGN KEY(country_code) REFERENCES country (code), \n\tCONSTRAINT uq_state_country_code_code UNIQUE (country_code, code)\n)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
def upgrade() -> None:
    op.execute(CREATE)
def downgrade() -> None:
    op.execute("DROP TABLE state")

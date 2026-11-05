"""Create currency; seed data is applied separately."""
from alembic import op
revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None
CREATE = 'CREATE TABLE currency (\n\tcode CHAR(3) NOT NULL, \n\tnumeric_code CHAR(3) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tsymbol VARCHAR(8) NOT NULL, \n\tminor_unit TINYINT NOT NULL, \n\tmajor_unit_name VARCHAR(40) NOT NULL, \n\tminor_unit_name VARCHAR(40), \n\tminor_unit_name_plural VARCHAR(40), \n\tis_active BOOL NOT NULL, \n\tCONSTRAINT pk_currency PRIMARY KEY (code)\n)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
def upgrade() -> None:
    op.execute(CREATE)
def downgrade() -> None:
    op.execute("DROP TABLE currency")

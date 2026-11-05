"""Create language; seed data is applied separately."""
from alembic import op
revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None
CREATE = 'CREATE TABLE language (\n\tcode CHAR(2) NOT NULL, \n\tiso3 CHAR(3) NOT NULL, \n\tname VARCHAR(128) NOT NULL, \n\tnative_name VARCHAR(128), \n\tis_active BOOL NOT NULL, \n\tCONSTRAINT pk_language PRIMARY KEY (code), \n\tCONSTRAINT uq_language_iso3 UNIQUE (iso3)\n)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
def upgrade() -> None:
    op.execute(CREATE)
def downgrade() -> None:
    op.execute("DROP TABLE language")

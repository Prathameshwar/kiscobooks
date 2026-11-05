"""Trusted inventory reporting handoff; one atomic DDL statement."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0155"
down_revision = "0154"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_report_record",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("tenant_id", mysql.BINARY(16), nullable=False),
        sa.Column("company_id", mysql.BINARY(16), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", mysql.BINARY(16), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_by", mysql.BINARY(16), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_report_record"),
        sa.UniqueConstraint("tenant_id", "company_id", "id", name="uq_inventory_report_record_scope"),
        sa.CheckConstraint("row_version > 0", name="ck_inventory_report_record_inventory_report_record_version"),
        sa.Index("ix_inventory_report_record_page", "tenant_id", "company_id", "id"),
        sa.Index("ix_inventory_report_record_tenant_id", "tenant_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("inventory_report_record")

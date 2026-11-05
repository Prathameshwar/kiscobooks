"""Create warehouse_group_assignment; one atomic DDL, with a paired model."""

from alembic import op

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE warehouse_group_assignment (
    company_id BINARY(16) NOT NULL,
    warehouse_id BINARY(16) NOT NULL,
    group_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_warehouse_group_assignment_date_range CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_warehouse_group_assignment_dates CHECK (valid_to IS NULL OR
        valid_to >= valid_from),
    CONSTRAINT fk_warehouse_group_assignment_group FOREIGN KEY(tenant_id, company_id, group_id)
        REFERENCES warehouse_group (tenant_id, company_id, id),
    CONSTRAINT fk_warehouse_group_assignment_warehouse FOREIGN KEY(tenant_id, company_id,
        warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT pk_warehouse_group_assignment PRIMARY KEY (id),
    CONSTRAINT uq_warehouse_group_assignment_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_warehouse_group_assignment_start UNIQUE (tenant_id, company_id, warehouse_id,
        valid_from),
    KEY ix_warehouse_group_assignment_group (tenant_id, company_id, group_id, valid_from, id),
    KEY ix_warehouse_group_assignment_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE warehouse_group_assignment")

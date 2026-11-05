"""Catalog-owned item_group_parent; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_group_parent (
    company_id BINARY(16) NOT NULL,
    group_id BINARY(16) NOT NULL,
    parent_group_id BINARY(16) NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_group_parent PRIMARY KEY (id),
    CONSTRAINT uq_item_group_parent_start UNIQUE (tenant_id, company_id, group_id, valid_from),
    CONSTRAINT fk_item_group_parent_group FOREIGN KEY(tenant_id, company_id, group_id)
        REFERENCES item_group (tenant_id, company_id, id),
    CONSTRAINT fk_item_group_parent_parent FOREIGN KEY(tenant_id, company_id, parent_group_id)
        REFERENCES item_group (tenant_id, company_id, id),
    CONSTRAINT ck_item_group_parent_item_group_parent_dates CHECK (valid_to IS NULL OR valid_to
        >= valid_from),
    CONSTRAINT ck_item_group_parent_item_group_parent_self CHECK (parent_group_id IS NULL OR
        parent_group_id <> group_id),
    CONSTRAINT ck_item_group_parent_item_group_parent_date_range
        CHECK (valid_from >= '1000-01-01'),
    KEY ix_item_group_parent_descendants (tenant_id, company_id, parent_group_id, valid_from, id),
    KEY ix_item_group_parent_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_group_parent")

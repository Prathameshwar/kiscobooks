"""Catalog price_level_assignment_scope: unique CUSTOMER/PRICING_TYPE subject; one DDL."""

from alembic import op

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE price_level_assignment_scope (
    subject_kind VARCHAR(20) NOT NULL,
    customer_ref BINARY(16) NULL,
    pricing_type_ref VARCHAR(40) NULL,
    row_version INT NOT NULL DEFAULT 1,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_price_level_assignment_scope PRIMARY KEY (id),
    CONSTRAINT uq_pla_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_pla_scope_subject
        UNIQUE (tenant_id, company_id, subject_kind, customer_ref, pricing_type_ref),
    CONSTRAINT ck_pla_scope_subject
        CHECK ((subject_kind = 'CUSTOMER' AND customer_ref IS NOT NULL AND pricing_type_ref IS NULL)
            OR (subject_kind = 'PRICING_TYPE' AND pricing_type_ref IS NOT NULL AND customer_ref IS NULL)),
    CONSTRAINT ck_pla_scope_row_version CHECK (row_version >= 1),
    KEY ix_pla_scope_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE price_level_assignment_scope")

"""Catalog price_level_assignment: dated scope-to-price_level binding; one DDL."""

from alembic import op

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE price_level_assignment (
    scope_id BINARY(16) NOT NULL,
    price_level_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    row_version INT NOT NULL DEFAULT 1,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_price_level_assignment PRIMARY KEY (id),
    CONSTRAINT uq_pla_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT fk_pla_scope FOREIGN KEY (tenant_id, company_id, scope_id)
        REFERENCES price_level_assignment_scope (tenant_id, company_id, id),
    CONSTRAINT fk_pla_level FOREIGN KEY (tenant_id, company_id, price_level_id)
        REFERENCES price_level (tenant_id, company_id, id),
    CONSTRAINT ck_pla_row_version CHECK (row_version >= 1),
    CONSTRAINT ck_pla_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    KEY ix_pla_tenant_id (tenant_id),
    KEY ix_pla_effective (tenant_id, company_id, scope_id, valid_from)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE price_level_assignment")

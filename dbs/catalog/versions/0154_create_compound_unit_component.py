"""Catalog compound_unit_component: multiplicative composition of one compound unit; one DDL.

A compound unit expresses ``1 parent = component_1 x component_2 x ...`` — for
example ``1 case = 12 x 5kg bag`` decomposes as two components. Every component
row names one child unit and a positive integer quantity; the resolver
multiplies them together. Sum-based composition (``4kg + 500g``) is deliberately
excluded — the schema check enforces the multiplicative form.
"""

from alembic import op

revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE compound_unit_component (
    parent_unit_id BINARY(16) NOT NULL,
    child_unit_id BINARY(16) NOT NULL,
    quantity NUMERIC(19,4) NOT NULL,
    ordinal SMALLINT NOT NULL,
    row_version INT NOT NULL DEFAULT 1,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_compound_unit_component PRIMARY KEY (id),
    CONSTRAINT uq_compound_unit_component_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_compound_unit_component_position
        UNIQUE (tenant_id, company_id, parent_unit_id, ordinal),
    CONSTRAINT fk_compound_unit_component_parent
        FOREIGN KEY (tenant_id, company_id, parent_unit_id)
        REFERENCES unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT fk_compound_unit_component_child
        FOREIGN KEY (tenant_id, company_id, child_unit_id)
        REFERENCES unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT ck_compound_unit_component_quantity CHECK (quantity > 0),
    CONSTRAINT ck_compound_unit_component_ordinal CHECK (ordinal >= 1),
    CONSTRAINT ck_compound_unit_component_not_self CHECK (parent_unit_id <> child_unit_id),
    CONSTRAINT ck_compound_unit_component_row_version CHECK (row_version >= 1),
    KEY ix_compound_unit_component_tenant_id (tenant_id),
    KEY ix_compound_unit_component_parent (tenant_id, company_id, parent_unit_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE compound_unit_component")

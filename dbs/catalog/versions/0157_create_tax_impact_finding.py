"""Catalog tax_impact_finding: non-complete results of one tax impact review; one DDL.

Only MISSING, REQUIRE_EXPLICIT and INVALID results are stored; ``blocking`` marks the ones
that prevent publication (any INVALID result, or a non-complete result for an ACTIVE product).
"""

from alembic import op

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_impact_finding (
    review_id BINARY(16) NOT NULL,
    item_id BINARY(16) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    as_of DATE NOT NULL,
    status VARCHAR(16) NOT NULL,
    missing JSON NOT NULL,
    blocking BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_tax_impact_finding PRIMARY KEY (id),
    CONSTRAINT uq_tax_impact_finding_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_tax_impact_finding_version CHECK (row_version >= 1),
    CONSTRAINT fk_tax_impact_finding_review_id FOREIGN KEY (tenant_id, company_id, review_id)
        REFERENCES tax_impact_review (tenant_id, company_id, id),
    CONSTRAINT uq_tax_impact_finding_check
        UNIQUE (tenant_id, company_id, review_id, item_id, direction, as_of),
    CONSTRAINT ck_tax_impact_finding_result CHECK (direction IN ('SALE','PURCHASE')
        AND status IN ('MISSING','REQUIRE_EXPLICIT','INVALID')),
    KEY ix_tax_impact_finding_page (tenant_id, company_id, review_id, id),
    KEY ix_tax_impact_finding_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tax_impact_finding")

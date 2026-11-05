"""Create product_configuration_revision; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_configuration_revision (
    scope_id BINARY(16) NOT NULL,
    source_draft_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    published_at DATETIME(6) NOT NULL,
    change_reason VARCHAR(250) NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_configuration_revision PRIMARY KEY (id),
    CONSTRAINT uq_configuration_revision_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_configuration_revision_scope_id UNIQUE (tenant_id, company_id, scope_id, id),
    CONSTRAINT uq_configuration_revision_number UNIQUE (tenant_id, company_id, scope_id, revision),
    CONSTRAINT uq_configuration_revision_draft UNIQUE (tenant_id, company_id, source_draft_id),
    CONSTRAINT fk_configuration_revision_draft FOREIGN KEY(tenant_id, company_id, scope_id,
        source_draft_id) REFERENCES product_configuration_draft (tenant_id, company_id,
        scope_id, id),
    CONSTRAINT ck_product_configuration_revision_configuration_revision_number CHECK (revision
        >= 1),
    CONSTRAINT ck_product_configuration_revision_configuration_revision_date CHECK
        (effective_from >= '1000-01-01'),
    CONSTRAINT uq_configuration_revision_date UNIQUE (tenant_id, company_id, scope_id,
        effective_from),
    INDEX ix_configuration_revision_effective (tenant_id, company_id, scope_id, effective_from,
        revision, id),
    INDEX ix_configuration_revision_scope_id (tenant_id, company_id, scope_id, id),
    INDEX ix_product_configuration_revision_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_configuration_revision")

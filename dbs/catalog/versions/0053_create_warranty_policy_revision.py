"""Create warranty_policy_revision; one DDL paired with its native model."""

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE warranty_policy_revision (
    company_id BINARY(16) NOT NULL,
    policy_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    published_at DATETIME(6) NULL,
    duration INTEGER NOT NULL,
    duration_unit VARCHAR(10) NOT NULL,
    start_trigger VARCHAR(20) NOT NULL,
    coverage_description VARCHAR(2000) NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_warranty_policy_revision_warranty_policy_rev_duration CHECK ((duration_unit =
        'DAYS' AND duration BETWEEN 1 AND 36500) OR (duration_unit = 'MONTHS' AND duration
        BETWEEN 1 AND 1200) OR (duration_unit = 'YEARS' AND duration BETWEEN 1 AND 100)),
    CONSTRAINT ck_warranty_policy_revision_warranty_policy_rev_trigger CHECK (start_trigger IN
        ('SALE','DELIVERY','INSTALLATION')),
    CONSTRAINT ck_warranty_policy_revision_warranty_policy_rev_version CHECK (revision >= 1 AND
        row_version >= 1),
    CONSTRAINT fk_warranty_policy_rev_parent FOREIGN KEY(tenant_id, company_id, policy_id)
        REFERENCES warranty_policy (tenant_id, company_id, id),
    CONSTRAINT pk_warranty_policy_revision PRIMARY KEY (id),
    CONSTRAINT uq_warranty_policy_rev_number UNIQUE (tenant_id, company_id, policy_id, revision),
    CONSTRAINT uq_warranty_policy_rev_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_warranty_policy_rev_published (tenant_id, company_id, policy_id, published_at,
        revision, id),
    KEY ix_warranty_policy_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE warranty_policy_revision")

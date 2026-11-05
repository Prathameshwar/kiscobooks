"""Create return_policy_condition; one DDL paired with its native model."""

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE return_policy_condition (
    company_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NOT NULL,
    condition_code VARCHAR(30) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_return_policy_condition_return_policy_condition_code CHECK (condition_code IN
        ('ORIGINAL_PACKAGING','PROOF_OF_PURCHASE','COMPLETE_ACCESSORIES','UNUSED','UNDAMAGED')),
    CONSTRAINT fk_return_policy_condition_rev FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES return_policy_revision (tenant_id, company_id, id),
    CONSTRAINT pk_return_policy_condition PRIMARY KEY (id),
    CONSTRAINT uq_return_policy_condition_code UNIQUE (tenant_id, company_id, revision_id,
        condition_code),
    KEY ix_return_policy_condition_page (tenant_id, company_id, revision_id, condition_code, id),
    KEY ix_return_policy_condition_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE return_policy_condition")

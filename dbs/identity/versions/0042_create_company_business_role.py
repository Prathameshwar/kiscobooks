"""Tenant-scoped role bindings; parent tenant agreement is enforced by the FK."""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE company_business_role (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    business_role_code VARCHAR(32) NOT NULL,
    CONSTRAINT pk_company_business_role PRIMARY KEY (id),
    CONSTRAINT uq_company_business_role_binding UNIQUE (tenant_id, company_id, business_role_code),
    KEY ix_company_business_role_tenant_id (tenant_id),
    KEY ix_company_business_role_code (business_role_code),
    CONSTRAINT fk_company_business_role_company FOREIGN KEY (tenant_id, company_id)
        REFERENCES company (tenant_id, id),
    CONSTRAINT fk_company_business_role_code FOREIGN KEY (business_role_code)
        REFERENCES business_role (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
""")


def downgrade() -> None:
    op.execute("DROP TABLE company_business_role")

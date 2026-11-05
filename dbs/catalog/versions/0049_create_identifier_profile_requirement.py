"""Create identifier_profile_requirement; one DDL paired with its native model."""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE identifier_profile_requirement (
    company_id BINARY(16) NOT NULL,
    profile_id BINARY(16) NOT NULL,
    identifier_type VARCHAR(10) NOT NULL,
    namespace_rule VARCHAR(20) NOT NULL,
    min_count INTEGER NOT NULL,
    max_count INTEGER NOT NULL,
    requires_slot BOOL NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_identifier_profile_requirement_identifier_requirement_counts CHECK (min_count >= 0
        AND max_count >= 1 AND min_count <= max_count AND max_count <= 8),
    CONSTRAINT ck_identifier_profile_requirement_identifier_requirement_imei CHECK (identifier_type
        != 'IMEI' OR namespace_rule = 'COMPANY'),
    CONSTRAINT ck_identifier_profile_requirement_identifier_requirement_86ec CHECK (namespace_rule
        IN ('COMPANY','MANUFACTURER_SKU')),
    CONSTRAINT ck_identifier_profile_requirement_identifier_requirement_slots CHECK (requires_slot
        IN (0,1) AND (max_count <= 1 OR requires_slot = 1)),
    CONSTRAINT ck_identifier_profile_requirement_identifier_requirement_type CHECK (identifier_type
        IN ('SERIAL','IMEI')),
    CONSTRAINT fk_identifier_requirement_profile FOREIGN KEY(tenant_id, company_id, profile_id)
        REFERENCES identifier_profile (tenant_id, company_id, id),
    CONSTRAINT pk_identifier_profile_requirement PRIMARY KEY (id),
    CONSTRAINT uq_identifier_requirement_type UNIQUE (tenant_id, company_id, profile_id,
        identifier_type),
    KEY ix_identifier_profile_requirement_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE identifier_profile_requirement")

"""Create handling_profile_revision; one DDL paired with its native model."""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE handling_profile_revision (
    company_id BINARY(16) NOT NULL,
    profile_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    published_at DATETIME(6) NULL,
    temperature_min NUMERIC(19,4) NULL,
    temperature_max NUMERIC(19,4) NULL,
    temperature_unit VARCHAR(10) NULL,
    fragile BOOL NOT NULL,
    keep_dry BOOL NOT NULL,
    keep_upright BOOL NOT NULL,
    instructions VARCHAR(2000) NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_handling_profile_revision_handling_profile_rev_absolute_zero CHECK
        ((temperature_min IS NULL OR temperature_min >= -273.15) AND (temperature_max IS NULL OR
        temperature_max >= -273.15)),
    CONSTRAINT ck_handling_profile_revision_handling_profile_rev_flags CHECK (fragile IN (0,1) AND
        keep_dry IN (0,1) AND keep_upright IN (0,1)),
    CONSTRAINT ck_handling_profile_revision_handling_profile_rev_order CHECK (temperature_min IS
        NULL OR temperature_max IS NULL OR temperature_min <= temperature_max),
    CONSTRAINT ck_handling_profile_revision_handling_profile_rev_unit CHECK (((temperature_min IS
        NOT NULL OR temperature_max IS NOT NULL) AND temperature_unit IS NOT NULL AND
        temperature_unit = 'CELSIUS') OR (temperature_min IS NULL AND temperature_max IS NULL AND
        temperature_unit IS NULL)),
    CONSTRAINT ck_handling_profile_revision_handling_profile_rev_version CHECK (revision >= 1 AND
        row_version >= 1),
    CONSTRAINT fk_handling_profile_rev_parent FOREIGN KEY(tenant_id, company_id, profile_id)
        REFERENCES handling_profile (tenant_id, company_id, id),
    CONSTRAINT pk_handling_profile_revision PRIMARY KEY (id),
    CONSTRAINT uq_handling_profile_rev_number UNIQUE (tenant_id, company_id, profile_id, revision),
    CONSTRAINT uq_handling_profile_rev_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_handling_profile_rev_published (tenant_id, company_id, profile_id, published_at,
        revision, id),
    KEY ix_handling_profile_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE handling_profile_revision")

"""Create manufacturer_site; one atomic DDL, with a paired model."""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE manufacturer_site (
    manufacturer_id BINARY(16) NOT NULL,
    country_code CHAR(2) NOT NULL,
    state_code VARCHAR(6) NULL,
    company_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT ck_manufacturer_site_manufacturer_site_version CHECK (row_version >= 1),
    CONSTRAINT fk_manufacturer_site_country FOREIGN KEY(country_code) REFERENCES country (code),
    CONSTRAINT fk_manufacturer_site_parent FOREIGN KEY(tenant_id, company_id, manufacturer_id)
        REFERENCES manufacturer (tenant_id, company_id, id),
    CONSTRAINT fk_manufacturer_site_state FOREIGN KEY(country_code, state_code) REFERENCES state
        (country_code, code),
    CONSTRAINT pk_manufacturer_site PRIMARY KEY (id),
    CONSTRAINT uq_manufacturer_site_parent_id UNIQUE (tenant_id, company_id, manufacturer_id, id),
    CONSTRAINT uq_manufacturer_site_scope_code UNIQUE (tenant_id, company_id, manufacturer_id,
        code),
    CONSTRAINT uq_manufacturer_site_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_manufacturer_site_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_manufacturer_site_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_manufacturer_site_code (tenant_id, company_id, code, id),
    KEY ix_manufacturer_site_country_state (country_code, state_code),
    KEY ix_manufacturer_site_name (tenant_id, company_id, name, id),
    KEY ix_manufacturer_site_parent_name (tenant_id, company_id, manufacturer_id, name, id),
    KEY ix_manufacturer_site_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE manufacturer_site")

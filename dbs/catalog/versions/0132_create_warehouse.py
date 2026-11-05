"""Create warehouse; one atomic DDL, with a paired model."""

from alembic import op

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE warehouse (
    kind VARCHAR(20) NOT NULL,
    is_system BOOL NOT NULL,
    department_id BINARY(16) NULL,
    timezone VARCHAR(64) NULL,
    address_line1 VARCHAR(120) NULL,
    address_line2 VARCHAR(120) NULL,
    city VARCHAR(60) NULL,
    postal_code VARCHAR(20) NULL,
    country_code CHAR(2) NULL,
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
    CONSTRAINT ck_warehouse_warehouse_kind CHECK (kind IN ('STORE','GODOWN','INTERNAL_TRANSIT')),
    CONSTRAINT ck_warehouse_warehouse_state CHECK (state_code IS NULL OR country_code IS NOT NULL),
    CONSTRAINT ck_warehouse_warehouse_system_code CHECK ((is_system = 0 AND code NOT IN
        ('MAIN','TRANSIT')) OR (is_system = 1 AND code IN ('MAIN','TRANSIT'))),
    CONSTRAINT ck_warehouse_warehouse_transit_code CHECK ((kind <> 'INTERNAL_TRANSIT' OR code =
        'TRANSIT') AND (code <> 'TRANSIT' OR kind = 'INTERNAL_TRANSIT')),
    CONSTRAINT ck_warehouse_warehouse_version CHECK (row_version >= 1),
    CONSTRAINT fk_warehouse_country FOREIGN KEY(country_code) REFERENCES country (code),
    CONSTRAINT fk_warehouse_state FOREIGN KEY(country_code, state_code) REFERENCES state
        (country_code, code),
    CONSTRAINT pk_warehouse PRIMARY KEY (id),
    CONSTRAINT uq_warehouse_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_warehouse_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_warehouse_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_warehouse_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_warehouse_country_state (country_code, state_code),
    KEY ix_warehouse_kind (tenant_id, company_id, kind, is_active, id),
    KEY ix_warehouse_name (tenant_id, company_id, name, id),
    KEY ix_warehouse_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE warehouse")

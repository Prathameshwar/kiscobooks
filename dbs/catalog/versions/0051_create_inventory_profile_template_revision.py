"""Create inventory_profile_template_revision; one DDL paired with its native model."""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE inventory_profile_template_revision (
    company_id BINARY(16) NOT NULL,
    template_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    row_version INTEGER NOT NULL,
    published_at DATETIME(6) NULL,
    identifier_profile_id BINARY(16) NULL,
    lot_tracking BOOL NOT NULL,
    serial_tracking BOOL NOT NULL,
    expiry_required BOOL NOT NULL,
    manufacture_date_required BOOL NOT NULL,
    shelf_life_days INTEGER NULL,
    minimum_remaining_life_days INTEGER NULL,
    issue_strategy VARCHAR(10) NOT NULL,
    valuation_method VARCHAR(20) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_83c1 CHECK (lot_tracking
        = 1 OR (expiry_required = 0 AND manufacture_date_required = 0 AND shelf_life_days IS NULL
        AND minimum_remaining_life_days IS NULL)),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_5f1a CHECK
        (expiry_required = 1 OR (issue_strategy != 'FEFO' AND minimum_remaining_life_days IS
        NULL)),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_9cc8 CHECK (lot_tracking
        IN (0,1) AND serial_tracking IN (0,1) AND expiry_required IN (0,1) AND
        manufacture_date_required IN (0,1)),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_f8f4 CHECK
        (issue_strategy IN ('FIFO','FEFO')),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_3dcc CHECK
        (shelf_life_days IS NULL OR minimum_remaining_life_days IS NULL OR
        minimum_remaining_life_days <= shelf_life_days),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_f801 CHECK
        (minimum_remaining_life_days IS NULL OR minimum_remaining_life_days BETWEEN 0 AND 36500),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_9575 CHECK
        (serial_tracking = 1 OR (identifier_profile_id IS NULL AND valuation_method !=
        'SPECIFIC')),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_3d24 CHECK
        (shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 36500),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_bacb CHECK
        (valuation_method IN ('FIFO','MOVING_AVERAGE','SPECIFIC')),
    CONSTRAINT ck_inventory_profile_template_revision_inventory_templat_7d54 CHECK (revision >= 1
        AND row_version >= 1),
    CONSTRAINT fk_inventory_template_rev_identifier FOREIGN KEY(tenant_id, company_id,
        identifier_profile_id) REFERENCES identifier_profile (tenant_id, company_id, id),
    CONSTRAINT fk_inventory_template_rev_parent FOREIGN KEY(tenant_id, company_id, template_id)
        REFERENCES inventory_profile_template (tenant_id, company_id, id),
    CONSTRAINT pk_inventory_profile_template_revision PRIMARY KEY (id),
    CONSTRAINT uq_inventory_template_rev_number UNIQUE (tenant_id, company_id, template_id,
        revision),
    CONSTRAINT uq_inventory_template_rev_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_inventory_profile_template_revision_tenant_id (tenant_id),
    KEY ix_inventory_template_rev_identifier (tenant_id, company_id, identifier_profile_id),
    KEY ix_inventory_template_rev_published (tenant_id, company_id, template_id, published_at,
        revision, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE inventory_profile_template_revision")

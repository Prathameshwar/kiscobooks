"""Catalog-owned field_index_state; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE field_index_state (
    company_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    field_key VARCHAR(64) NOT NULL,
    generation BIGINT NOT NULL,
    ready_generation BIGINT NULL,
    ready_digest VARCHAR(64) NULL,
    building_generation BIGINT NULL,
    building_digest VARCHAR(64) NULL,
    retired_generation BIGINT NULL,
    row_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_field_index_state PRIMARY KEY (id),
    CONSTRAINT uq_field_index_state_key UNIQUE (tenant_id, company_id, entity_type, field_key),
    CONSTRAINT uq_field_index_state_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_field_index_state_field_index_version CHECK (generation >= 0 AND row_version >=
        1),
    CONSTRAINT ck_field_index_state_field_index_ready_generation CHECK (ready_generation IS NULL OR
        (ready_generation >= 1 AND ready_generation <= generation)),
    CONSTRAINT ck_field_index_state_field_index_building_generation CHECK (building_generation IS
        NULL OR (building_generation >= 1 AND building_generation <= generation)),
    CONSTRAINT ck_field_index_state_field_index_retired_generation CHECK (retired_generation IS NULL
        OR (retired_generation >= 1 AND retired_generation <= generation)),
    CONSTRAINT ck_field_index_state_field_index_ready_pair CHECK ((ready_generation IS NULL) =
        (ready_digest IS NULL)),
    CONSTRAINT ck_field_index_state_field_index_building_pair CHECK ((building_generation IS NULL) =
        (building_digest IS NULL)),
    CONSTRAINT ck_field_index_state_field_index_cleanup_first CHECK (building_generation IS NULL OR
        retired_generation IS NULL),
    CONSTRAINT ck_field_index_state_field_index_monotonic_build CHECK
        (ready_generation IS NULL OR building_generation IS NULL OR ready_generation <
        building_generation),
    CONSTRAINT ck_field_index_state_field_index_retired_not_ready CHECK
        (ready_generation IS NULL OR retired_generation IS NULL OR ready_generation <>
        retired_generation),
    KEY ix_field_index_state_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_index_state")

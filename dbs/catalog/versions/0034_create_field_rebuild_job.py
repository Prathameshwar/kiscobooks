"""Catalog-owned field_rebuild_job; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE field_rebuild_job (
    company_id BINARY(16) NOT NULL,
    state_id BINARY(16) NOT NULL,
    actor_user_id BINARY(16) NOT NULL,
    generation BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    definition_digest VARCHAR(64) NOT NULL,
    definition JSON NOT NULL,
    status VARCHAR(12) NOT NULL,
    phase VARCHAR(12) NOT NULL,
    checkpoint_id BINARY(16) NULL,
    processed_count BIGINT NOT NULL,
    cleanup_count BIGINT NOT NULL,
    reason_code VARCHAR(80) NULL,
    row_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_field_rebuild_job PRIMARY KEY (id),
    CONSTRAINT uq_field_rebuild_job_generation UNIQUE (tenant_id, company_id, state_id, generation),
    CONSTRAINT fk_field_rebuild_job_state FOREIGN KEY(tenant_id, company_id, state_id) REFERENCES
        field_index_state (tenant_id, company_id, id),
    CONSTRAINT ck_field_rebuild_job_field_rebuild_counters CHECK (generation >= 1 AND source_version
        >= 1 AND row_version >= 1 AND processed_count >= 0 AND cleanup_count >= 0),
    CONSTRAINT ck_field_rebuild_job_field_rebuild_status CHECK (status IN
        ('pending','running','succeeded','failed','cancelled')),
    CONSTRAINT ck_field_rebuild_job_field_rebuild_phase CHECK (phase IN
        ('build','cleanup','complete')),
    KEY ix_field_rebuild_job_poll (tenant_id, company_id, phase, status, id),
    KEY ix_field_rebuild_job_state (tenant_id, company_id, state_id),
    KEY ix_field_rebuild_job_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_rebuild_job")

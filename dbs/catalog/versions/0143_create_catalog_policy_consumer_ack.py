"""Create catalog_policy_consumer_ack; one atomic DDL, with a paired model."""

from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_policy_consumer_ack (
    release_id BINARY(16) NOT NULL,
    release_revision INTEGER NOT NULL,
    consumer VARCHAR(20) NOT NULL,
    aggregate VARCHAR(30) NOT NULL,
    aggregate_id BINARY(16) NOT NULL,
    enforced_revision INTEGER NOT NULL,
    result VARCHAR(10) NOT NULL,
    reason_code VARCHAR(30) NULL,
    source_message_id BINARY(16) NOT NULL,
    acknowledged_at DATETIME(6) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_catalog_policy_consumer_ack_aggregate CHECK (aggregate IN
        ('CATALOG_POLICY_RELEASE', 'WAREHOUSE_OPERATION_POLICY', 'WAREHOUSE_RETIREMENT')),
    CONSTRAINT ck_catalog_policy_consumer_ack_consumer CHECK (consumer IN ('billing')),
    CONSTRAINT ck_catalog_policy_consumer_ack_result CHECK (result IN ('APPLIED', 'REJECTED')),
    CONSTRAINT ck_catalog_policy_consumer_ack_revision CHECK (release_revision >= 1
        AND enforced_revision >= 1),
    CONSTRAINT ck_catalog_policy_consumer_ack_subject CHECK (aggregate <> 'CATALOG_POLICY_RELEASE'
        OR aggregate_id = release_id),
    CONSTRAINT ck_catalog_policy_consumer_ack_verdict CHECK ((result = 'APPLIED'
        AND reason_code IS NULL) OR (reason_code IS NOT NULL AND reason_code IN ('OPEN_COUNT',
        'OPEN_TRANSFER', 'PENDING_DOCUMENT', 'POLICY_CONFLICT', 'RESERVED_STOCK',
        'SOURCE_UNAVAILABLE', 'STOCK_ON_HAND', 'UNKNOWN_LOCATION', 'UNSUPPORTED_OPERATION'))),
    CONSTRAINT ck_catalog_policy_consumer_ack_version CHECK (row_version >= 1),
    CONSTRAINT fk_catalog_policy_ack_release_id FOREIGN KEY(tenant_id, company_id, release_id)
        REFERENCES catalog_policy_release (tenant_id, company_id, id),
    CONSTRAINT pk_catalog_policy_consumer_ack PRIMARY KEY (id),
    CONSTRAINT uq_catalog_policy_ack_subject UNIQUE (tenant_id, company_id, consumer, aggregate,
        aggregate_id, release_id),
    CONSTRAINT uq_catalog_policy_consumer_ack_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_catalog_policy_ack_aggregate (tenant_id, company_id, aggregate, aggregate_id,
        release_revision),
    KEY ix_catalog_policy_consumer_ack_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_policy_consumer_ack")

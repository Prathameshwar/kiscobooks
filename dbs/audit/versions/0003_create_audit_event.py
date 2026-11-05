"""Create audit_event, RANGE-partitioned monthly on occurred_at.

One literal MySQL DDL statement per direction (rule 4.8). Two things here are
irreversible without a full table rebuild and so must be right in this first migration
(docs/audit.md §6):

* **PK ``(occurred_at, id)``** — every unique key on a partitioned table must include
  the partition column. ``id`` alone is globally unique by UUIDv7 generation, so no
  second unique key is needed (and none could omit ``occurred_at`` anyway).
* **RANGE COLUMNS(occurred_at)** monthly partitions, with a ``pmax`` catch-all so an
  insert never fails for a missing partition. The create-ahead job (``tasks/partitions``)
  keeps future months provisioned by reorganizing ``pmax``; the retention job drops whole
  past partitions (§4.1) — audit rows are never deleted row-by-row.

Seeded from 2026-09 (the service's first month) with three months ahead, matching
``Settings.partition_months_ahead``. No foreign keys: partitioned InnoDB forbids them,
and audit references ids it must not couple to (§5.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE audit_event (
    occurred_at DATETIME(6) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    sequence BIGINT NOT NULL,
    actor_type VARCHAR(32) NULL,
    actor_user_id BINARY(16) NULL,
    on_behalf_of_user_id BINARY(16) NULL,
    actor_ip VARCHAR(45) NULL,
    actor_user_agent VARCHAR(400) NULL,
    api_client_id BINARY(16) NULL,
    company_id BINARY(16) NULL,
    department_id BINARY(16) NULL,
    category VARCHAR(20) NOT NULL,
    action VARCHAR(60) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id BINARY(16) NULL,
    changes JSON NULL,
    context JSON NULL,
    reason VARCHAR(500) NULL,
    source_service VARCHAR(40) NULL,
    trace_id VARCHAR(32) NULL,
    request_id VARCHAR(64) NULL,
    message_id BINARY(16) NOT NULL,
    prev_hash BINARY(32) NULL,
    row_hash BINARY(32) NOT NULL,
    ingested_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_audit_event PRIMARY KEY (occurred_at, id),
    KEY ix_audit_event_tenant_id (tenant_id),
    KEY ix_audit_event_tenant_id_occurred_at (tenant_id, occurred_at),
    KEY ix_audit_event_tenant_id_entity_type_entity_id (tenant_id, entity_type, entity_id),
    KEY ix_audit_event_tenant_id_category_occurred_at (tenant_id, category, occurred_at),
    KEY ix_audit_event_tenant_id_company_id_occurred_at (tenant_id, company_id, occurred_at),
    KEY ix_audit_event_tenant_id_sequence (tenant_id, sequence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
PARTITION BY RANGE COLUMNS(occurred_at) (
    PARTITION p202609 VALUES LESS THAN ('2026-10-01 00:00:00'),
    PARTITION p202610 VALUES LESS THAN ('2026-11-01 00:00:00'),
    PARTITION p202611 VALUES LESS THAN ('2026-12-01 00:00:00'),
    PARTITION p202612 VALUES LESS THAN ('2027-01-01 00:00:00'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
)
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE audit_event")

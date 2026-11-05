"""create company_feature

Revision ID: 0010
Revises: 0009

Per-company capability toggles (docs/company-features.md §3). Rows rather than a JSON
column on `company`, because a blob cannot carry `enabled_by`, cannot answer "which
companies have inventory on", and gives the audit trail one opaque diff where there
should be a discrete event per feature.

`UNIQUE (company_id, feature_key)` deliberately omits `tenant_id`, unlike
`uq_company_tenant_id_code`. `company_id` already determines the tenant, so adding it
would *weaken* the constraint: the same (company, feature) pair could insert twice
under a mismatched `tenant_id`. Leading with `company_id` also supports
`fk_company_feature_company_id`, so no separate index is needed for it.

`feature_key` carries **no foreign key** — features are code, not data, for the same
reason permission keys are: a feature is a claim that code exists to honour it. Boot
rejects a row naming a key absent from `billing_platform.features`.

`locked_at` is the ratchet (§4). Non-null means the feature is **permanently
enabled**: it is set by the first dependent write, inside that write's transaction,
and never cleared. Nullable in the schema because the schema cannot express "write
once"; the enforcement is in `identity.domain.company_features` and applies to every
actor including platform admin. `lock_reason` stores the `locks_on` event so the
rejection can say why rather than "this cannot be changed".

`enabled_at`/`enabled_by` and `disabled_at`/`disabled_by` are not duplicates of
`AuditMixin`: they record the last transition in each direction and survive the next
write, while `updated_at`/`updated_by` is simply the most recent write of any kind.

Lifecycle is `is_enabled` — rule 4.12's boolean form, never combined with a `status`.
Absent row means disabled; a missing replica row in a consuming service is a hard
failure, never an implicit enable (§5).

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_company_feature_company_id_feature_key`
is 256 bytes, far under 3072 (§1.6) · no NULL inside a unique key (§2) · no ENUM ·
no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_feature (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    feature_key VARCHAR(60) NOT NULL,
    is_enabled TINYINT(1) NOT NULL,
    enabled_at DATETIME(6) NULL,
    enabled_by BINARY(16) NULL,
    disabled_at DATETIME(6) NULL,
    disabled_by BINARY(16) NULL,
    locked_at DATETIME(6) NULL,
    lock_reason VARCHAR(120) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_feature PRIMARY KEY (id),
    CONSTRAINT uq_company_feature_company_id_feature_key UNIQUE (company_id, feature_key),
    CONSTRAINT fk_company_feature_company_id
        FOREIGN KEY (company_id) REFERENCES company (id),
    KEY ix_company_feature_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_feature")

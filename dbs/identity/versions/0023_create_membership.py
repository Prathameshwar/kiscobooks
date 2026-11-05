"""create membership

Revision ID: 0023
Revises: 0022

A user's affiliation to a company or department (docs/identity-schema.md §4.7) — kept
separate from ``role_assignment`` by design: this is where a person works, not what they
may do. The unique key leads with ``user_id`` and supports that FK; ``company_id`` and the
nullable ``department_id`` get their own FK-supporting indexes. ``department_id`` is
genuinely nullable (not a SCOPE_ALL table): a company-level membership has no department.
``user`` is backticked — reserved word.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT · business dates ``DATE`` suffixed ``_on`` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE membership (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    department_id BINARY(16) NULL,
    is_primary TINYINT(1) NOT NULL,
    started_on DATE NULL,
    ended_on DATE NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_membership PRIMARY KEY (id),
    CONSTRAINT uq_membership_user_company_department
        UNIQUE (user_id, company_id, department_id),
    CONSTRAINT fk_membership_user_id FOREIGN KEY (user_id) REFERENCES `user` (id),
    CONSTRAINT fk_membership_company_id FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_membership_department_id FOREIGN KEY (department_id) REFERENCES department (id),
    KEY ix_membership_tenant_id (tenant_id),
    KEY ix_membership_company_id (company_id),
    KEY ix_membership_department_id (department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE membership")

"""create department

Revision ID: 0019
Revises: 0018

A cost centre within a company, self-nesting (docs/identity-schema.md §3.12). It is a
*scope* an assignment can narrow to, not an approval chain.

`path` is a materialized ancestor path — `/<id-hex>/…/` — indexed by
`ix_department_tenant_id_path` so ancestor-or-self resolution is an indexed prefix test
rather than a recursive CTE on every permission check. Maintained in `domain/`, capped
at six levels.

`fk_department_company_id`'s supporting index is `uq_department_company_id_code`, which
leads with `company_id`, so no separate index is declared for it (§1.7). `parent_id` and
`head_user_id` get explicit FK-supporting indexes or InnoDB invents them and they read as
autogenerate drift. `user` is backticked — reserved word.

`(tenant_id, path)` is 16 + 500*4 = 2016 bytes, under the 3072 DYNAMIC limit (§1.6).

Raw DDL for the reason in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a unique key · no ENUM · no
FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE department (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    parent_id BINARY(16) NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(150) NOT NULL,
    cost_centre_code VARCHAR(30) NULL,
    head_user_id BINARY(16) NULL,
    path VARCHAR(500) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_department PRIMARY KEY (id),
    CONSTRAINT uq_department_company_id_code UNIQUE (company_id, code),
    CONSTRAINT fk_department_company_id FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_department_parent_id FOREIGN KEY (parent_id) REFERENCES department (id),
    CONSTRAINT fk_department_head_user_id FOREIGN KEY (head_user_id) REFERENCES `user` (id),
    KEY ix_department_tenant_id (tenant_id),
    KEY ix_department_tenant_id_path (tenant_id, path),
    KEY ix_department_parent_id (parent_id),
    KEY ix_department_head_user_id (head_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE department")

"""create company_contact

Revision ID: 0024
Revises: 0023

A named point of contact on a company (docs/identity-schema.md §3.9). The
`(company_id, type)` index leads with `company_id` (§1.7 second exception — it
determines tenant_id) and supports the FK.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_contact (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    type VARCHAR(20) NOT NULL,
    name VARCHAR(150) NOT NULL,
    designation VARCHAR(100) NULL,
    email VARCHAR(320) NULL,
    phone_country_code VARCHAR(8) NULL,
    phone VARCHAR(20) NULL,
    is_primary TINYINT(1) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_contact PRIMARY KEY (id),
    CONSTRAINT fk_company_contact_company_id FOREIGN KEY (company_id) REFERENCES company (id),
    KEY ix_company_contact_tenant_id (tenant_id),
    KEY ix_company_contact_company_id_type (company_id, type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_contact")

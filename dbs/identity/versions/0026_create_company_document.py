"""create company_document

Revision ID: 0026
Revises: 0025

A stored statutory/corporate document reference (docs/identity-schema.md §3.11).
``file_url`` is an object key served via a signed expiring URL (§5.14). ``expires_on``
feeds a renewal sweep.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT (``BIGINT`` is an integer, not a float) · timestamps `DATETIME(6)` suffixed `_at`,
business dates `DATE` suffixed `_on` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_document (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    type VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    number VARCHAR(60) NULL,
    file_url VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NULL,
    content_type VARCHAR(100) NULL,
    issued_on DATE NULL,
    expires_on DATE NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_document PRIMARY KEY (id),
    CONSTRAINT fk_company_document_company_id FOREIGN KEY (company_id) REFERENCES company (id),
    KEY ix_company_document_tenant_id (tenant_id),
    KEY ix_company_document_company_id_type (company_id, type),
    KEY ix_company_document_expires_on (expires_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_document")

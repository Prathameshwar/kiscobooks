"""create company_bank_account

Revision ID: 0025
Revises: 0024

A company's bank account (docs/identity-schema.md §3.10). ``account_number`` and ``iban``
are log-redaction targets (CLAUDE.md §5.11) — stored, never logged. The currency FK gets
its own supporting index leading with `currency_code`; the `(company_id, currency_code)`
index leads with `company_id` and supports that FK.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_bank_account (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    label VARCHAR(100) NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    account_number VARCHAR(60) NULL,
    iban VARCHAR(34) NULL,
    swift VARCHAR(11) NULL,
    ifsc VARCHAR(11) NULL,
    bank_name VARCHAR(200) NOT NULL,
    branch VARCHAR(200) NULL,
    currency_code CHAR(3) NOT NULL,
    is_primary TINYINT(1) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_bank_account PRIMARY KEY (id),
    CONSTRAINT fk_company_bank_account_company_id FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_company_bank_account_currency_code
        FOREIGN KEY (currency_code) REFERENCES currency (code),
    KEY ix_company_bank_account_tenant_id (tenant_id),
    KEY ix_company_bank_account_company_id_currency (company_id, currency_code),
    KEY ix_company_bank_account_currency_code (currency_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_bank_account")

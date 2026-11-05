"""create company

Revision ID: 0008
Revises: 0007

The legal entity that issues documents (docs/identity-schema.md §3.3). The widest
table in the service, and the one whose keys carry the most weight.

**The composite foreign key is the point of this revision.**
`(country_code, state_code)` references `state (country_code, code)`, which is why
revision 0006 carries a unique key on those two columns that looks redundant against
its primary key. Without it, `country_code='IN'` with `state_code='US-CA'` is
accepted, and `state_code` decides whether every issued invoice is intra-state or
inter-state GST. The pair is refused by the database, not by a form.

`fk_company_country_code` needs no index of its own: InnoDB accepts any index whose
leftmost prefix matches the constrained columns, and
`ix_company_country_code_state_code` starts with it. The three FK-supporting indexes
that *are* declared exist so InnoDB does not create them itself and name them after
the constraints — an implicitly created index is invisible in the model and reads as
autogenerate drift on every later revision.

Those FK indexes deliberately do not lead with `tenant_id` (§1.7): an index
supporting a foreign key must begin with the foreign key's own columns. The query
index that matters, `ix_company_tenant_id_status`, does lead with it.

`fk_company_parent_company_id` is self-referencing, which InnoDB supports inside
`CREATE TABLE`. It proves the parent exists; it cannot prove the parent belongs to
the same tenant, so that is a `domain/` check — a cross-tenant parent would be a
§5.2 object-scope breach no `WHERE` clause would catch.

`print_template_id` carries **no foreign key**: templates live outside `identity`,
and cross-service foreign keys are what the architecture forbids.

Ten columns are immutable once `first_posted_at` is set — `code`, `country_code`,
`state_code`, `base_currency`, both fiscal-start columns, `books_begin_date`, both
precisions, and `rounding_mode` (docs/company.md §5.2). The schema cannot express
"write once after a condition", so the freeze lives in
`identity.domain.company_immutability` and applies to every actor including platform
admin. `first_posted_at` itself stays nullable and is set once by the first posting.

`amount_precision` and `quantity_precision` are `TINYINT` **display** scales, 0–4.
Storage is `DECIMAL(19,4)` regardless (docs/company.md §4.5); reading them as storage
scales is how a subledger stops tying. Both money columns here — `credit_limit_default`
and `cash_receipt_limit` — are denominated in `base_currency` on the same row, which
is their currency sibling.

`dsc_thumbprint` is a certificate fingerprint, never a key or a PFX blob (§5.9).
`logo_url` and `signature_url` hold object keys served through signed expiring URLs
(§5.14), never public bucket paths.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_company_tenant_id_code` is 96 bytes,
far under 3072 (§1.6) · `tenant_id` leads the query index (§1.7) · no NULL inside a
unique key (§2) · no ENUM · no FLOAT · money columns are DECIMAL(19,4) · timestamps
`DATETIME(6)` suffixed `_at`, business dates `DATE` suffixed `_date` · no seed data ·
downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    parent_company_id BINARY(16) NULL,
    code VARCHAR(20) NOT NULL,
    legal_name VARCHAR(255) NOT NULL,
    trade_name VARCHAR(255) NULL,
    display_name VARCHAR(120) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    incorporation_date DATE NULL,
    country_code CHAR(2) NOT NULL,
    state_code VARCHAR(6) NOT NULL,
    status VARCHAR(20) NOT NULL,
    first_posted_at DATETIME(6) NULL,
    base_currency CHAR(3) NOT NULL,
    reporting_currency CHAR(3) NULL,
    fiscal_year_start_month TINYINT NOT NULL,
    fiscal_year_start_day TINYINT NOT NULL,
    books_begin_date DATE NOT NULL,
    amount_precision TINYINT NOT NULL,
    quantity_precision TINYINT NOT NULL,
    rounding_mode VARCHAR(20) NOT NULL,
    default_tax_system VARCHAR(20) NOT NULL,
    tax_treatment_default VARCHAR(12) NOT NULL,
    default_payment_terms_days SMALLINT NOT NULL,
    credit_limit_default DECIMAL(19,4) NULL,
    cash_receipt_limit DECIMAL(19,4) NULL,
    backdated_posting_limit_days SMALLINT NULL,
    industry_code VARCHAR(20) NULL,
    business_nature VARCHAR(20) NULL,
    timezone VARCHAR(64) NOT NULL,
    locale VARCHAR(8) NOT NULL,
    date_format VARCHAR(20) NOT NULL,
    datetime_format VARCHAR(30) NOT NULL,
    digit_grouping VARCHAR(10) NOT NULL,
    decimal_separator VARCHAR(2) NOT NULL,
    thousands_separator VARCHAR(2) NOT NULL,
    negative_format VARCHAR(15) NOT NULL,
    show_amount_in_words TINYINT(1) NOT NULL,
    currency_symbol_position VARCHAR(10) NOT NULL,
    currency_symbol_override VARCHAR(8) NULL,
    logo_url VARCHAR(500) NULL,
    signature_url VARCHAR(500) NULL,
    brand_color CHAR(7) NULL,
    print_template_id BINARY(16) NULL,
    terms_and_conditions TEXT NULL,
    declaration_text TEXT NULL,
    jurisdiction_text VARCHAR(200) NULL,
    signatory_name VARCHAR(150) NULL,
    signatory_designation VARCHAR(100) NULL,
    dsc_thumbprint VARCHAR(64) NULL,
    visibility VARCHAR(10) NOT NULL,
    requires_step_up TINYINT(1) NOT NULL,
    visibility_changed_at DATETIME(6) NULL,
    visibility_changed_by BINARY(16) NULL,
    custom_fields JSON NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company PRIMARY KEY (id),
    CONSTRAINT uq_company_tenant_id_code UNIQUE (tenant_id, code),
    CONSTRAINT fk_company_parent_company_id
        FOREIGN KEY (parent_company_id) REFERENCES company (id),
    CONSTRAINT fk_company_country_code
        FOREIGN KEY (country_code) REFERENCES country (code),
    CONSTRAINT fk_company_country_code_state_code
        FOREIGN KEY (country_code, state_code) REFERENCES state (country_code, code),
    CONSTRAINT fk_company_base_currency
        FOREIGN KEY (base_currency) REFERENCES currency (code),
    CONSTRAINT fk_company_reporting_currency
        FOREIGN KEY (reporting_currency) REFERENCES currency (code),
    KEY ix_company_tenant_id (tenant_id),
    KEY ix_company_tenant_id_status (tenant_id, status),
    KEY ix_company_country_code_state_code (country_code, state_code),
    KEY ix_company_base_currency (base_currency),
    KEY ix_company_reporting_currency (reporting_currency),
    KEY ix_company_parent_company_id (parent_company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company")

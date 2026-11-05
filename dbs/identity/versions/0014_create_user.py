"""create user

Revision ID: 0014
Revises: 0013

A principal within one tenant (docs/identity-schema.md §4.1). Credentials stay in
Authentik — no password hash, no MFA secret, no session, no recovery code — so this
table cannot become a second authentication authority that disagrees with the first.

`user` is not a reserved word in MariaDB, but it is a system-table name in the `mysql`
schema and reads as one to anybody scanning this file, so it is backticked throughout.

Two unique keys pull in opposite directions on NULL, deliberately:

* `uq_user_tenant_id_email` is **per tenant**. The same address may exist in two
  tenants as two different people-in-context (docs/org-model.md §4.3). Neither column
  is nullable, so §2 does not apply.
* `uq_user_authentik_sub` is **global and nullable**, and MariaDB treating NULLs
  inside a unique key as distinct is what makes it work: every pending invitation has
  a NULL subject and they must all coexist. The opposite of the sentinel case in §2,
  where distinct NULLs break the key. Global rather than per tenant because the OIDC
  callback resolves by subject alone.

`default_department_id` is created **without** a foreign key. `department` is revision
0019, and `user.default_department_id` → `department` → `company` → ... closes a cycle
one direction of which has to give (§1.5). Revision 0019 adds the constraint; it is
deferred, not forgotten.

`deactivated_at` / `deactivated_by` / `deactivation_reason` are spelled out rather than
taken from the `Deactivable` mixin: this table's lifecycle is `status`, and adding
`is_active` alongside it would be the two competing switches rule 4.12 forbids. These
three are evidence for the `deactivated` status, not a second one.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_user_tenant_id_email` is
16 + 320*4 + 2 = 1298 bytes, under 3072 (§1.6) · no NULL inside a non-nullable unique
key, and the one nullable unique key wants distinct NULLs (§2) · no ENUM · no FLOAT ·
timestamps `DATETIME(6)` suffixed `_at`, business dates `DATE` · JSON is MariaDB's
LONGTEXT + `json_valid` CHECK, which reflection reports as LONGTEXT (revision 0001) ·
no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE `user` (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    authentik_sub VARCHAR(64) NULL,
    user_type VARCHAR(30) NOT NULL,
    salutation VARCHAR(20) NULL,
    first_name VARCHAR(100) NOT NULL,
    middle_name VARCHAR(100) NULL,
    last_name VARCHAR(100) NULL,
    display_name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    email_verified_at DATETIME(6) NULL,
    phone_country_code VARCHAR(8) NULL,
    phone VARCHAR(20) NULL,
    phone_verified_at DATETIME(6) NULL,
    employee_code VARCHAR(40) NULL,
    job_title VARCHAR(120) NULL,
    reporting_manager_id BINARY(16) NULL,
    default_company_id BINARY(16) NULL,
    default_department_id BINARY(16) NULL,
    date_of_joining DATE NULL,
    date_of_exit DATE NULL,
    locale VARCHAR(8) NULL,
    timezone VARCHAR(64) NULL,
    date_format VARCHAR(20) NULL,
    datetime_format VARCHAR(30) NULL,
    digit_grouping VARCHAR(10) NULL,
    currency_display VARCHAR(20) NULL,
    theme VARCHAR(20) NULL,
    landing_page VARCHAR(100) NULL,
    status VARCHAR(20) NOT NULL,
    invited_by BINARY(16) NULL,
    invited_at DATETIME(6) NULL,
    activated_at DATETIME(6) NULL,
    last_active_at DATETIME(6) NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    deactivation_reason VARCHAR(500) NULL,
    anonymized_at DATETIME(6) NULL,
    terms_accepted_at DATETIME(6) NULL,
    terms_version VARCHAR(20) NULL,
    privacy_accepted_at DATETIME(6) NULL,
    custom_fields JSON NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_user PRIMARY KEY (id),
    CONSTRAINT uq_user_tenant_id_email UNIQUE (tenant_id, email),
    CONSTRAINT uq_user_authentik_sub UNIQUE (authentik_sub),
    CONSTRAINT fk_user_reporting_manager_id
        FOREIGN KEY (reporting_manager_id) REFERENCES `user` (id),
    CONSTRAINT fk_user_default_company_id
        FOREIGN KEY (default_company_id) REFERENCES company (id),
    KEY ix_user_tenant_id (tenant_id),
    KEY ix_user_tenant_id_status (tenant_id, status),
    KEY ix_user_reporting_manager_id (reporting_manager_id),
    KEY ix_user_default_company_id (default_company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE `user`")

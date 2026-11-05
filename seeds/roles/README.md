# System-role seed

`python -m seeds.roles --dry-run` (then without `--dry-run`) runs the existing Identity
role seed using `IDENTITY_DATABASE_URL`. Use Identity's virtual environment and an
explicitly intended database. The seed reads `identity.domain.system_roles` and the
shared fixed permission catalogue; there is no separate Accounting role database.

The existing Accounting grants are included in the same idempotent seed: TenantAuditor
reads; CompanyAdmin and Controller manage masters, import and publish mappings. The
[permission catalogue](../../docs/roles-permissions.md) documents the exact keys.
Existing role identities are preserved, permissions are reconciled, and no user assignment
is created. The September 14 Accounting repair introduces no new seed grants.

The 2026-10-29 Tenant Administrator update adds complete-company report read,
source/run creation and export authority without money writes. Existing operators
can review and apply the same fixed seed through Platform administration → System
role updates; the authenticated API adds preview fingerprints, replay protection
and a transactional audit event. It preserves custom tenant roles and assignments.

The user-approved 2026-10-30 Tenant Administrator opening update uses this same
canonical seed and platform workflow. It adds native finance management, journal
posting, ordinary open-period posting, opening read/manage/zero and Accounting
export read authority. These are existing permission keys and also authorize native
finance/journal operations. Company Administrator bootstrap and period
close/reopen/lock, voucher approval/posting and impersonation policy are unchanged.

The 2026-10-05 withholding grants follow the same split. TenantAuditor gets
`accounting.withholding.read`, and CompanyAdmin and Controller get read and
`accounting.withholding.manage`. No statutory section or rate is seeded; those are company
masters with source evidence.

The 2026-10-27 Company Administrator correction includes read/manage authority for
identifier types, identifier namespaces and sales channels. Those keys already
exist in the permission catalogue. Re-running this seed adds six grants to the
same system role without changing assignments; the following dry run is unchanged.
Company creation separately grants that fixed role to its creator at the new
company's scope in the creation transaction. See
[company-owner-access](../../docs/company-owner-access.md).

The 2026-11-01 Purchase roles update adds the `purchase_clerk` role (26 existing keys), five read
keys to `billing_approver` and four to `stock_operator`; no permission key is new and no
schema migration is needed. Re-running this seed inserts the one role and the 35 missing grants,
keeps every role id and assignment, and the next run is a no-op. **It is not insert-only**: it also
removes any grant on a shipped role that the catalogue does not list. For this change that is none
(the dry run reports `revoked=0`), but a grant added by hand to a shipped role would be removed, so
run `--dry-run` immediately before applying and read the `revoked` column. **Run it before
using company creation again**: creation compares the installed `company_admin` and
`stock_operator` grants with the catalogue and answers 409 until they match. From the repository
root, with `IDENTITY_DATABASE_URL` set to the intended database (dry run first):
`.\apis\identity\.venv\Scripts\python.exe -m seeds.roles --dry-run`, then without `--dry-run`.
See [roles-permissions](../../docs/roles-permissions.md), decision log 2026-11-01.

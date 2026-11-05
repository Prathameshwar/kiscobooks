# Seeds

Seed data lives here, **never in a migration** (CLAUDE.md §2). A migration carrying
content runs once, in one environment, and cannot be corrected; a seed is
re-runnable, so a correction reaches every environment on the next deploy.

Every seed is an **idempotent upsert on the natural key** and safe to run on every
deploy. A withdrawn row that anything can reference is **deactivated, never deleted**
(CLAUDE.md invariant 12): a currency on a posted invoice, a role on a live assignment.

The one exception is `role_permission`, which *is* deleted when a shipped role stops
granting a permission — it carries no lifecycle switch, and a deactivated row would
keep occupying the unique key and silently refuse the re-grant. Nothing references a
grant row; what changed lives in the audit trail.

| Seed | Phase | Content |
|---|---|---|
| `reference/` | 1 | `currency`, `country`, `state` from `libs/platform` static data |
| `roles/` | 5 | Fourteen system roles + `role_permission`, keyed `(SCOPE_ALL, key)` |
| `business_classifications/` | 0042 | Business categories, business roles (including Online/Store), store formats |
| `pricing/` | 0085 | Platform 1/3-year fees and optional communications/AI/document add-ons; insert missing codes only, preserving admin edits and tombstones |

## Installation defaults

For the Identity step of platform installation, configure `IDENTITY_DATABASE_URL` for
an existing MySQL database and run `.\start\win\install-identity.ps1` from the repository
root (requires `uv` and enabled PowerShell script execution). Alternatively use the
Identity Python environment without changing any execution policy:

```powershell
.\apis\identity\.venv\Scripts\python.exe -m identity.install
```

This applies the schema migrations and loads ISO reference data, system security roles,
and business categories/roles/store formats. All default values commit together. Installation is
also responsible for the INR/USD [pricing catalog](../docs/platform-pricing.md).
Pricing seeds do not overwrite commercial terms chosen by administrators. Setup is
safe to rerun on upgrades and after a failed installation; it creates no companies or users.
The individual commands below remain available for targeted updates and dry runs.

## Running

```bash
IDENTITY_DATABASE_URL=... python -m seeds.reference identity --dry-run
IDENTITY_DATABASE_URL=... python -m seeds.reference identity

# `roles` imports identity's own domain package, so it runs under that venv
cd apis/identity
IDENTITY_DATABASE_URL=... python -m uv run python -m seeds.roles --dry-run
IDENTITY_DATABASE_URL=... python -m uv run python -m seeds.roles
```

Verified form on Windows (2026-11-01): run from the **repository root** with the Identity
virtual environment's interpreter, because `seeds` is a root package that the `apis/identity`
working directory cannot import. Set `IDENTITY_DATABASE_URL` to the intended database first.

```powershell
.\apis\identity\.venv\Scripts\python.exe -m seeds.roles --dry-run
.\apis\identity\.venv\Scripts\python.exe -m seeds.roles
```

`--dry-run` reports what would change and rolls back. Worth running first on every
deploy that touches a shipped role, since adding a permission to one widens access
for every tenant at once.

The URL comes from `<SERVICE>_DATABASE_URL` in the environment and is never read
from a file in the repo — a database URL carries a password (CLAUDE.md §5.9).

Order in a fresh environment: `alembic upgrade head`, then `seeds.reference`, then
any later phase's migrations that add foreign keys pointing at the reference tables.
`seeds.roles` needs revision 0016 and is otherwise unordered — it references no
reference table.

## Regenerating the reference data

The datasets under `libs/platform/src/billing_platform/reference/data/` are
generated, not hand-edited:

```bash
cd libs/platform
python -m uv run --group reference python tools/generate_reference_data.py
```

The generator reads `pycountry`, CLDR and libphonenumber at generation time only,
and refuses to write a value that would not fit its column. Review the resulting
diff like any other change.

## Business classifications

After Identity revision `0042`, run `python -m seeds.business_classifications --dry-run`
then `python -m seeds.business_classifications` from the repository root using the Identity
virtual environment and `IDENTITY_DATABASE_URL`. The seed under `business_classifications/`
upserts categories, business roles and store formats; withdrawn codes are deactivated.
There is no CRUD API for these global tables. See
[company-classification.md](../docs/company-classification.md) for API values and defaults.

## Catalog General group

Run `python -m seeds.catalog --base-url URL --company UUID` using the Catalog virtualenv. Supply current gateway authorization/signed actor headers and optional custom_fields as bounded JSON on stdin. This calls ordinary Catalog APIs; it does not bypass tenant/company scope, Identity freshness, custom validation, idempotency or audit. Reruns preserve the existing General definition. See [classification API](../docs/catalog-classification-api.md).


Manufacturing-operation authoring (2026-10-27, shared catalogue 0.43.0): the company administrator
receives `manufacturing_operation.read`, `.manage` and `.publish`; the tenant auditor receives read.
Other fixed roles receive none. Apply the normal role seed after reviewing its dry run; existing
company-scoped assignments acquire the matching keys without widening their scope.

Sequential routes add `manufacturing_route.read`, `.manage` and `.publish` to the same company
administrator and read-only auditor roles. The seed was verified without modifying user assignments.

BOM definition authoring adds `bom.read/manage/publish/assign` for company administrators and
read for tenant auditors, using the normal role seed. It does not enable the company feature.

Promotion stacking-policy authoring adds `promotion_stack_policy.read/manage/publish` to company
administrators and read to tenant auditors. The sales_promotions feature remains off until enabled.

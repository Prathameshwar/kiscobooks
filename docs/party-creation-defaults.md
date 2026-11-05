# Party creation defaults and optional tax start date

User decision, 2026-10-31: party creation suggests legal name from name, company
country (falling back to IN), address label `Billing address`, and tax country/state
from the preceding identity/address steps. All suggestions remain editable.
`Valid from` on a party tax registration is optional throughout the UI/API/database.

## Delivery phases

1. Add regression tests, make only party tax-registration starts nullable, and
   migrate the column in one DDL. Adapt effective-date validation, overlap queries,
   history guards, child containment, voucher tax evaluation and signed lookups.
   A null start means no lower date bound; expiry and immutable history still apply.
   Existing dates and all other dated resources retain their current contracts.
2. Add permission-aware wizard defaults, pass the authorized company country from
   Identity to the creation page, regenerate public contracts, and test suggested
   values, overrides, navigation, permissions and creation without a tax start date.
3. Run affected suites, type/lint checks, native migration checks and browser review.
   Review CLAUDE.md sections 5 and 6 manually; `/simplify` and `/security-review`
   commands are unavailable in this session, so record the equivalent review here.

The existing company setup lock serializes interval admission. Nullable SQL unique
keys do not replace the scoped application overlap check. Downgrade refuses to
invent dates for null starts: supply reviewed dates before reverting the column.

## Verification

Wizard/company-default coverage passed (76 tests), with a later wizard/company
boundary run also green (111 tests). Live browser review confirmed that legal name
follows name until overridden. The local database is at Accounting 0227 and the tax
start column accepts NULL; native MySQL upgrade/downgrade and the guarded downgrade
with existing NULL values were verified. Seven optional-start regressions passed,
covering omitted/explicit NULL starts, overlap, as-of reads, history and containment.
Five Vouchers lookup cases passed, including a nullable tax-registration start.
OpenAPI and generated-client freshness checks passed; affected Accounting mypy and
Ruff checks passed. The final native MySQL tax/domain/optional-start run passed
all 46 tests with 94.94% domain coverage, including preview/post of a taxed bill
with either an explicit registration start or NULL. The accompanying setup-timeout
fix is recorded in product-creation-recovery.md.

Manual CLAUDE.md sections 5/6 review found no additional issues: field permissions
still gate suggestions, the company is read through its authorized Identity API,
tenant/company scope and serialized interval checks remain, and no dates are
fabricated in stored history or during downgrade. Tax calculations retain Decimal.

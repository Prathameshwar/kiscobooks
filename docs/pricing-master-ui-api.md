# Pricing master UI and API

Delivery plan (25 October 2026), authorized by the requested end-to-end implementation:

1. Verify native sales channel, price level and price plan contracts; supply typed field
   controls and operation-specific read-only fields, with a closed Console proxy policy.
2. Reuse shared layout, styles, searchable references, custom fields, tables, menus,
   notices and navigation guards for scoped directories/create/edit/detail pages. Include
   explicit baseline-level bootstrap and guarded level/channel lifecycle actions.
3. Verify native permissions, field access, purpose/currency/feature guards, receipts and
   command recovery; review browser layouts; run focused and complete checks and fix findings.

Price plans are reusable books. Purpose, currency, tax basis and sale level are immutable.
Rates, dated price publication, customer assignments and pricing policies retain their existing
native workflows and are outside these three master management pages. Purchase books require
purchase-price read/manage in addition to price-plan authority. No alternative pricing engine
or monetary calculation is introduced.

The existing models and migrations already contain all three masters. No DDL or seed change
is planned. Baseline price levels are created only through the explicit native idempotent
bootstrap command; additional levels start at ordinal four and require the company feature.

## Implemented contracts

- `/masters/sales-channels`, `/masters/price-levels` and `/masters/price-plans` provide
  scoped directories, native search/filter/signed paging, create/edit/detail, authorized
  row menus and related/back navigation. Company/tenant grants govern navigation and pages;
  a platform role alone does not imply company authority.
- Channel name/code patches and separate activate/deactivate commands retain native
  referenced-series guards. Level patches preserve the required current name/active values;
  baseline retirement is withheld. Confirmed bootstrap creates only the configured baseline
  definitions and preserves existing names. New level codes/numbers are validated locally.
- Plan purpose, sale level, currency and tax basis are chosen at creation and retained thereafter.
  Purchase requires both purchase read/manage; non-sale plans omit sale-level semantics.
  Native currency/feature/source guards remain authoritative. Descriptive custom fields reuse
  their existing requiredness, conditions, exact value controls and option-source loader.
- Pricing receipts are checked for identity/version/generation/source shape, then confirmed
  against a current record read within the requested company. An unavailable or mismatched
  read makes the result uncertain; retry retains the exact body and idempotency key.
  Uncertain inputs are locked, duplicate creates retain editable drafts, and version conflicts
  require confirmed reload. Dirty navigation and validation focus reuse shared controls.
- Native typed field controls and update read-only metadata match the existing request schemas.
  Closed proxy routes reject invented publication/lifecycle paths and unsupported queries.
  No ORM/migration/seed changes; the OpenAPI schema and generated client remain current.

## Review and verification

Manual code/security review checked native method/body contracts, tenant/company authority,
purchase and protected-purpose restrictions, generated receipt recovery, field-level edits,
immutable terms, referenced retirement, navigation and exact custom values. Review corrections
included protected-purpose action gating, readable saved level labels, custom-only name retention,
and explicit currency choice recovery. No alternative price calculation, CSS or dependency added.

Focused Console regression: **88 passed**. Native pricing/channel/security/custom-field/
metadata regression: **25 passed**. Catalog lint and strict typing, OpenAPI freshness,
Catalog SDK freshness/types and all **8 SDK transport tests** passed.

Browser review passed **110 checks** at 1440px and 390px in light, dark and ledger themes.
It exercised actual Console components/providers/shared CSS with intercepted API fixtures;
no local business records were created. Checks include authoring/lifecycle, read-only and
purchase restrictions, setup confirmation, validation focus, dirty navigation and exact retry
identity, plus saved compound-sort navigation. Screenshots were visually reviewed.

The final production build passed and managed Console returned to `UP` on port 4320. Catalog
was restarted with the current metadata and passed readiness. The read-only schema audit
confirmed migration/model/database head `0191`, **164** model tables and no Alembic drift.
Live native/proxy checks also verified readiness and unauthenticated rejection for all three
master resources. The complete Console suite passed **2,215 tests across 153 files** with
no failures. All three delivery phases and the review/fixes are complete.

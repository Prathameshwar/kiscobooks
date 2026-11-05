# Simple product multiple selling prices

Authorized 2026-11-04: show and save selling prices according to enabled product
configuration. Keep Simple creation and import consistent.

## Delivery phases

1. Expose company-owned active sale levels and base-currency books through Simple
   options; accept exact per-level amounts and enforce configuration, required
   coverage and native permissions before creating a product.
2. Render metadata-driven selling-price inputs and matching flat import columns;
   preserve uncertain request identities and entered values across refreshes.
3. Regenerate API/client contracts, run creation/import/security/layout regression
   checks, and document final evidence.

## Decisions

- With multiple levels disabled, retain the existing single Selling price input.
- With multiple levels permitted by Product Configuration and company capability,
  show active levels with a company-currency SALE book, ordered by ordinal and
  labelled with their existing names. Do not invent or silently create levels.
- Required coverage follows the native activation rule: the company default level
  plus levels through Number of sale price levels. Other configured levels remain
  optional. Missing required levels/books produce actionable setup guidance.
- A product save carries level identities and exact decimal amounts. The native
  initial setup, publication and activation owners apply each price. The existing
  initial-price bound expands to 65: up to 64 selling levels and one purchase book.
- Import columns use stable level ordinals (`sale_price_1`, `sale_price_2`, ...)
  and display their configured names. Template fingerprints include these choices.
- Existing single-price requests and saved-command hashes remain compatible.
  No database model change or migration is needed.
- Activation verifies each required price and records immutable source evidence.
  Native MySQL reproduced a timeout with three required levels at the old 10-second
  command limit. Activation now uses the same bounded 30-second budget as aggregate
  creation; authority, locking, idempotency and rollback rules are unchanged.
- Import validation publishes newly created drafts within its rollback savepoint.
  It uses their protected versions and current policy/source versions directly;
  native publication still assesses readiness and history. This avoids repeating
  those same expensive checks in a separate preview for every level.
- The validation-only activation command also reuses its freshly calculated review
  inside the same locked company transaction. Reuse requires the matching session,
  factory, tenant, company, actor and task; ordinary bulk/API activation still
  recomputes its signed review. Native authorization, write checks, adoption and
  source recording still run, and the validation savepoint is rolled back.

## Review

- Permission review covers tenant/company-scoped price levels and books, native
  price amount metadata, write denial before product persistence, and amount read
  denial on import results after source-file expiry. Unknown level identifiers use
  the native reference boundary; foreign-company identifiers cannot be selected.
- Amounts remain exact decimal strings across form, import, native prices and
  retained results. Required levels are enforced server-side. Native free-sale
  restrictions still apply to a zero selling amount.
- Retry bodies retain the original level identities and amounts. Configuration
  changes require explicitly clearing inputs that have become unavailable; import
  template signatures bind the level names, identities and requirements.
- Manual simplification and security review completed; the repository's named
  slash-command review tools are not available in this session.

## Verification

Completed 2026-11-04:

- Six focused creation/schema checks cover exact amounts, four published prices
  (three selling levels and purchase), replay, required/optional levels, missing
  books, duplicate/foreign identifiers, read/write denial and legacy request hashes.
  The metadata cache was additionally checked against mixed required/optional levels
  and write-denied amounts.
- Four import checks cover Goods CSV and Service XLSX, validation rollback,
  completion, history, exact retained results, read revocation after file expiry,
  rejected/missing/zero prices, stale template names and locked-review reuse guards.
- Three isolated native MySQL checks passed with production time limits: direct
  creation and both import formats, each publishing three selling prices and one
  purchase price. The temporary server on port 13398 was shut down afterward.
- Four single-price/GST/opening workflow regressions and seven activation preview/
  source-refresh regressions passed.
- 57 creation/import UI tests passed. Browser checks passed for six scenarios at
  four widths in three themes (72 combinations); desktop/mobile multiple-price
  screenshots were also visually reviewed.
- Ruff and strict mypy passed for the 14 affected Catalog modules. Catalog OpenAPI
  and TypeScript contracts were regenerated and checked; the console and Catalog
  declarations type-check. API client version is 0.2.65; its consumer lockfile was
  refreshed (the local file dependency requires no textual lock change).
- The full shared-client type-check has an unrelated Accounting test mismatch:
  `clients/api-client/tests/accounting-types.ts:5` still expects `AccountCreate`,
  which is absent from its current Accounting contract. Accounting files were not
  changed for this task.

The named slash-command reviews were performed manually as recorded above. No
unresolved correctness or permission finding remains in this change. Native
performance evidence covers three selling levels; the schema accepts the existing
platform bound of 64 levels.

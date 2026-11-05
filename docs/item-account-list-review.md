# Item and account list review — 2026-10-13

The Catalog item and Accounting account lists retain the shared signed keyset page contract:
company and tenant scoping, a 50-row default/200-row cap, an ID tie-breaker, lean projections,
no exact count, and a cursor bound to query and authority. Searches are bounded, prefix-based
and restricted to readable code/name columns. Read-denied fields cannot be used for filters or
sorts.

## Changes and review fixes

- Item lists now filter by `base_unit_id` in addition to the existing family, status, sale and
  purchase filters. Status/SKU and base-unit/SKU composite indexes support those common pages.
- Account lists now filter by `currency` and `currency_mode`, expose readable currency mode,
  and sort by code in either direction. Code is the default account order. Composite indexes
  cover status, kind, group, currency and currency-mode filters followed by code/ID ordering.
- Review found that the shared search helper's two-character minimum would change other
  Accounting master lists. It is applied only to accounts; existing master lists retain their
  prior minimum. The helper escapes wildcard characters before indexed prefix search.
- Review checked scope and data leakage: list queries select explicit columns, apply the
  company predicate, enforce readable filter/search/sort fields, and reject a cursor when a
  filter changes. No detail JSON or unconditional count is loaded.

## Verification

Catalog product and migration tests passed (8); Accounting master and migration-head tests
passed (6); the broader Accounting masters/field-policy suite passed (17). Strict mypy passed
for Accounting (152 files) and Catalog (270 files). Ruff, offline MySQL migration SQL generation,
and Accounting/Catalog OpenAPI client-drift checks passed. The full Accounting regression run
passed 708 tests with 15 skipped before the final list-only changes; focused list tests cover
those changes. Database-scale `EXPLAIN` measurements are still needed against representative
company data before making a latency claim.

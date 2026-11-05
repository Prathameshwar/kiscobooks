# Simple product Category and Manufacturer entry

Requested 2026-11-04: make Category and Manufacturer available on Simple product
creation when enabled by Product Configuration.

## Delivery

1. Extend the Simple input/options and native initial setup with protected category
   memberships and a Goods manufacturer/site; enforce configuration and references.
2. Add optional/required switches, dependent search fields and category rows using
   the existing form components. Preserve entered data and exact retries.
3. Check creation/activation, permissions, config changes and responsive layouts;
   regenerate contracts and record verification.

## Decisions

- Optional sections follow their configured defaults; required sections stay on.
- Categories retain native schemes, required schemes and single/multiple membership
  rules. Manufacturer uses the existing manufacturer and optional site masters, the
  native Manufacturer role and the company business date. Services have no physical
  manufacturer assignments.
- Assignments participate in native initial product creation and its existing audit,
  field permissions and rollback; Save continues through automatic activation.
- This request changes the creation form. Import retains its explicit unsupported
  guidance for required Category/Manufacturer settings until its columns are added.
- Existing empty-input command hashes remain compatible. No migration is needed.

## Verification

- Goods and Services with required categories create active products. Goods also
  retain the manufacturer and site; replay returns the same creation and records.
- Disabled/required options, duplicate/single-scheme restrictions, wrong-company
  references and mismatched category/site parents are rejected. Native category
  and manufacturer field write denies roll back the whole initial product.
- The creation and import UI checks pass all 66 tests (41 existing creation,
  16 import, nine classification). These cover required schemes under an optional
  setting, inaccessible optional fields, validation, parent filtering and Save.
- The classification layout passes at 320, 390, 768 and 1440 pixels in light,
  dark and ledger themes (12 combinations). Mobile light and desktop dark
  screenshots were visually reviewed; controls align without horizontal overflow.
- Console TypeScript, Catalog client type checks, generated Catalog contract
  checks, Ruff and strict mypy for eight affected source modules pass. The API
  client is 0.2.66 and its local pnpm consumers were refreshed.
- Seven new backend cases pass across the creation and permission runs. The
  options response rejects protected category names, and import retains explicit
  guidance for required Category/Manufacturer settings.
- All 16 initial-setup, existing command-hash and barcode import-template
  regressions pass (162.83 seconds), bringing the targeted backend total to 23.

## Final review

Manual equivalents of `/simplify` and `/security-review` were used because those
commands are unavailable in this session. Entry uses shared controls and native
option sources with search/pagination and parent filtering. No new dependency,
table, permission or approval step is introduced.

The review fixed category write availability for the native primary flag and
keeps denied optional category fields hidden. Settings/type changes retain entered
details and require an explicit clear before Save; selected sites reset when their
manufacturer changes. Native reference and field checks remain authoritative, and
assignments use the existing transaction, audit and automatic activation flow.

Early test-fixture failures were corrected (missing country reference, invalid
mode/default combinations, and mocked responses without company ownership). One
existing UI test exceeded its five-second budget under parallel load; the full
targeted run passed with one worker and a 15-second test budget. The barcode hash
regression now explicitly describes the pre-extension request shape.

No new MySQL migration run, full repository CI, or Save through a running
gateway/worker deployment is claimed for this additive creation-form change.

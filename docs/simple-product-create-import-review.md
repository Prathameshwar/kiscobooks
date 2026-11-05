# Simple product creation and import review

Authorized 2026-11-04: review Simple creation and import and fix findings.

## Delivery

1. Reproduce configuration/data-loss and uncertain-import-retry issues with UI
   tests; exercise barcode import through template, validation and native creation.
2. Align import with the configured Barcode option using flat value/format
   columns, native creation/validation, duplicate detection and field protection.
   Preserve uncertain requests and block silently discarded form entries.
3. Check generated contracts, run API/UI/recovery/layout checks, and review security,
   audit, scope, exact quantities and readiness behavior.

## Findings

- Fixed: Barcode configuration was supported by Simple creation but absent from
  import. Required barcode prevented downloading any Simple import template.
  Templates, validation, native creation and result downloads now carry barcodes.
- Fixed: initial import actions and continuation cleared their retained command
  on HTTP 408 and 429, although those responses do not confirm the command's
  outcome. Retries now retain the original request body and idempotency key.
- Fixed: creation could omit an entered optional price or detail when refreshed
  metadata or configuration made it unavailable. Save now waits for an explicit
  clear or restored settings; the clear action uses the shared Notice layout.

## Decisions

- Barcode-enabled templates expose `barcode_value` and `barcode_symbology`.
  A supplied value uses CODE128 when format is blank. Required barcode requires
  the value; disabled barcode omits both columns. Leading zeroes remain strings.
- Duplicate values and equivalent GTIN representations within an import are
  reported before committing. Native uniqueness remains authoritative on Save.
- Existing Simple import history, signed downloads, correction/retry identities,
  native activation and opening posting remain in use.

## Verification

Completed 2026-11-04:

- 82 UI tests passed across Simple creation, Simple import, existing product
  import and party import. Three affected creation checks passed again after
  placing the clear action in the Notice action slot.
- 10 targeted Catalog API cases passed: barcode template modes, optional/default
  format handling, required and invalid values, equivalent GTIN duplicates,
  CSV Goods and XLSX Services through activation/history/result download,
  retained-receipt read protection, GST for both types, required Brand/Model/price
  configuration, exact opening cost and lost-response recovery, and historical
  download protection. The two runs reported 5 passed in 225.68s and 5 passed in
  200.39s.
- 24 browser layout combinations passed: the creation warning and new-import
  screen at 1440, 768, 390 and 320 pixels in light, dark and ledger themes.
  The 12 creation combinations passed again after the final Notice layout edit.
  Mobile screenshots were visually reviewed for wrapping and action placement.
- TypeScript `tsc --noEmit`, Ruff, strict mypy on the changed backend modules,
  and the Catalog OpenAPI export check passed. Barcode columns are a dynamic
  template schema; the static API contract remains current. No model or
  migration change is needed for this review.

The regression tests reproduced the missing required-barcode template, discarded
408/429 requests and silently omitted form entries before the fixes. The native
import integration test also caught missing barcode columns in result downloads;
the final green run includes that correction.

Manual simplicity/security review (the `/simplify` and `/security-review`
commands are unavailable in this environment):

- Barcode capture reuses the native validator, uniqueness rules and transactional
  creation/activation path. Company and tenant scoping, audit/outbox ownership,
  exact decimal pricing and opening posting retain their existing owners.
- Barcode read protection applies to uploaded rows and retained nested creation
  requests after source-file expiry. The API regression verifies a read denial
  returns 403 without revealing the barcode.
- Request retries preserve identity, while clearing unavailable creation entries
  requires a deliberate action and is disabled while a save is pending.
- No additional findings remain in the reviewed changes. Full repository CI,
  coverage measurement and a fresh MySQL/live-service rehearsal were not run in
  this review; API tests use the existing isolated test fixtures.

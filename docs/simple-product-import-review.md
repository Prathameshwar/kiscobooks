# Simple product import follow-up review

The user requested another review and fixes on 2026-11-04. This pass preserves
the existing Simple creation and native opening-posting contracts.

## Work plan

1. Reproduce history/download and interrupted-response problems with regression
   tests; inspect template usability and configuration handling.
2. Fix the confirmed problems through the existing import framework and UI.
3. Run affected backend/UI tests, contract and type checks, and the required
   security/correctness review. Record results below.

## Confirmed findings

- An older attempt download selects the latest file revision before locating its
  attempt, preventing downloads after a corrected file has been uploaded.
- An old failed import report can borrow the product name/code from a later
  corrected row that uses the same row key. Reports now check that retained
  effects match the original input before adding generated result fields.
- When the server completes a product but its last response is lost, a successful
  progress refresh does not update the parent page's job/status.
- A successful import retained its earlier "Import started" notice. Completion
  now clears that obsolete progress message.
- Excel templates encode existing cells as text but do not format blank input
  columns as text. Spreadsheet entry can therefore change leading-zero codes or
  exact decimal text before upload.

## Decisions

- Attempt downloads resolve the attempt's original revision and recheck its job,
  company, actor and field authority. Explicit conflicting revisions are rejected.
- A verified newer server progress read updates the page without another write.
  Uncertain admission requests retain their exact retry key and body.
- Generated spreadsheet input columns use Excel's built-in Text format; existing
  formula rejection and exact-number parsing remain in effect.

## Verification

- Regression tests first reproduced the original-revision download failure,
  historical name drift, lost-response status problem and missing Excel text style.
- Focused shared framework/file tests: 47 passed, including historical field
  revocation and attempts belonging to another job. Current reports still receive
  generated/native result values when their input matches.
- The full shared-library run passed 1,177 tests and found one outdated workbook
  fixture that replaced serialized XML without allowing a cell style attribute.
  The fixture now edits the intended cell structurally, preserving its original
  shared-string/security checks. Its suite and report regressions were rerun:
  21 passed, with accumulated shared-library coverage of 93.62% (90% required).
- Catalog API and Simple configuration/expiry checks: five passed. The API test
  downloads an original validation attempt after a replacement file is uploaded
  and verifies its product name, original filename and field diagnostic.
- Simple UI: ten passed, including a committed admission whose response is lost
  and whose retry retains its exact key/body. Existing Product and Party import
  UI suites: 29 passed. Four browser scenarios passed across 48 widths/themes;
  the mobile invalid-import screenshot was also visually reviewed.
- Targeted Ruff, strict mypy, Console TypeScript and whitespace checks passed.
- Shared library version is 0.44.5; all twelve Python lockfiles were refreshed.
  API schemas and database storage are unchanged; no migration is needed.

## Security and simplicity review

Manual equivalents of `/simplify` and `/security-review` were completed because
those commands are unavailable in this session. Attempt resolution checks the
owning job before accessing its original input and rechecks current field access.
Download tickets, tenant/company/actor scope, expiry and export audit remain in
force. Report enrichment checks the immutable effect input hash. The UI uses
verified reads to recover status and retains uncertain admission commands.
Excel text formatting leaves formula/external-link rejection and Decimal parsing
intact. This pass changes no native product, price or financial posting command.
No unresolved finding remains within this review's scope.

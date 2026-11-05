# Product configuration and Simple creation review

Requested 2026-11-04. This review follows the approved
[Simple product delivery plan](simple-product-ready-plan.md).

## Review phases

1. Trace new-company defaults, published configuration and the form's effective
   settings against the native Save preparation, including Goods and Services.
2. Exercise configuration changes, required fields, pricing, GST and opening
   stock; add failing regressions for confirmed defects and fix them at the owner.
3. Run affected API and UI suites, isolated native MySQL checks for money paths,
   static checks and manual security/simplicity review. Record precise evidence
   and remaining verification limits here.

Existing company data and unrelated workspace changes are preserved. Tests use
isolated databases; application services and the user's database are not test data.

## Findings and fixes

- Simple form options resolved company settings without selecting the default
  product type. A Brand required by that type could appear optional in the form,
  although Save rejected it. Options now use the same native authoring-default
  resolver as Save, for Goods and Services. Both regressions failed before the fix.
- Starting a creation returned its generated code before checking the code's read
  permission. Later reads correctly denied access, leaving an unreadable receipt.
  Start now checks the same field permission before reserving a code or writing a
  receipt. The regression reproduced the disclosure and now verifies a 403 with
  no stored receipt.
- A configuration-directory test retained the old card heading after the UI was
  renamed to “Company product defaults”. Its assertion now matches that label.

Expanded API coverage uses the new-company inventory configuration for both Goods
and Services, including GST HSN/SAC. A further test publishes a configuration with
required Model/MRP and disabled selling price, checks the form metadata, then
creates and activates a product under those settings. Services correctly omit MRP.

## Verification

- Final combined Catalog regression suite: 27 tests pass, covering Simple
  creation, the review regressions and company configuration defaults.
- 149 UI tests pass, including 72 browser layout scenarios: configuration edit and
  review plus four Simple form states, at four widths in three themes. Inspected
  the current mobile configuration editor and desktop Goods screenshots.
- Console TypeScript passes. Changed Python source passes strict mypy; application
  and test files pass Ruff checks and formatting.
- Identity company creation, opening authority and gateway context: 22 tests pass.
- Vouchers native opening creation/submission/issue/posting admission: 1 test passes.
- Accounting native MySQL opening suites: 7 tests pass, including Decimal
  quantity/value, replay, finalization, another product's prior trading and
  closed-period rejection without new control/audit rows.
- Catalog native MySQL matrix passes (235.82 seconds): new-company inventory
  Goods/Services, GST, inherited type requirements, published Model/MRP/pricing
  changes, protected receipt rejection, tenant isolation, active products and live
  prices, lost-response recovery, rejected-post retry, pre-create correction and
  retained-receipt rollback protection.
- Catalog OpenAPI and generated-client consistency checks pass; the API contract
  remains unchanged.

Run logs are in `.tools/product-config-starter-review/e2e-*.log`; browser artifacts
are in `.tools/product-config-ui-review/` and `.tools/simple-product-ui-review/`.

## Security and simplicity review

Manual equivalents of `/security-review` and `/simplify` were performed because
those commands are unavailable in this session. The permission defect above is
fixed at the API boundary. Tenant/company and initiating-user checks, fresh
authority, exact decimals, native posting, closed-period controls and idempotent
recovery remain in their existing owners. No new lifecycle, API schema, database
migration, dependency or shared style was introduced.

These checks exercise native owner APIs and isolated databases. Browser fixtures
use the real components/styles with mocked API responses. A live browser Save
through the running gateway and background workers is not claimed.
The temporary MySQL server on 13398 was shut down after verification. The existing
database on 3306 remains running; application services remain stopped.

All three review phases are complete. No additional unresolved defect was found
in the reviewed Simple flow. The live gateway/worker limitation above remains
explicit; these results do not claim whole-repository test coverage.

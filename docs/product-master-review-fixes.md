# Product master review corrections

Scope approved on 2026-10-29: fix all four findings from the Product Master review
and restore the two quantity-grid regression scenarios blocked by their fixtures.

## Delivery phases

1. Completed: add failing regressions for product reads without configuration access, scoped
   reference validation, expired revision recovery and directory failure/empty states.
2. Completed: correct the native aggregate ordering and product revision error mapping; fix
   the UI read/recovery/list states and use unbarcoded fixtures for grid revisions.
3. Completed: run affected API/UI suites, strict typing and lint; review security, transaction,
   field-policy and retry invariants, and record evidence here.

Existing API schemas, permission keys, database structure and publication workflow
remain in place. Configuration reads and writes retain their own permissions.

## Delivered corrections

- Product detail reads fall back to the existing native detail component when
  authoring settings are unavailable. Item and field permissions still authorize
  that read; creation/editing remain gated on verified settings.
- Simple PATCH validates both aggregate members' changed fields and their scoped
  references before claim/index persistence can flush either member. Invalid
  references retain 403/404 semantics; regression checks assert unchanged versions,
  names, brand and audit count after rejection and a successful corrected retry.
- Product revision decoding keeps signed actor/company/item binding and one-day
  expiry. Invalid/expired tokens return a 422 `revision` error with a review
  instruction rather than a pagination error. All product setup adapters reuse
  that mapping. The editor supports explicit revision review and a new save key
  while retaining entered values; uncertain saves still retry their exact key/body.
- Failed metadata/list reads suppress empty catalogue messaging and pagination.
  Filtered empty results show a clear-filter action, preserving sort and return
  navigation; a reader is not instructed to create records they cannot create.
- The two quantity-grid tests explicitly use a product without a barcode. Default
  fixtures retain their barcode; production barcode immutability is unchanged.

## Verification

- Before implementation: five new API regressions and eleven new UI assertions
  failed for the reviewed defects. The other new UI tests protect existing retry
  and editor permission behavior.
- Console: 139 tests passed across twelve affected product suites. Console
  TypeScript passed. Existing React `act` warnings in configuration page/attribute
  tests were visible; no test failed.
- Native MySQL 9.6.0: nine workflows passed against a random schema migrated to
  head 0210: three missing/wrong-company/wrong-tenant references with aggregate/audit
  rollback, child field denial, expired revision recovery, both repaired quantity
  grid regressions, and goods/service create/edit/idempotency replay.
  `tools/verify_product_master_mysql.py` reproduces this check using the existing
  `CATALOG_TEST_MYSQL_SERVER_URL` loopback-only verifier. The random schema was
  dropped and the disposable server started for this run was shut down. Schema
  downgrade traversal was not requested because no schema changed.
- OpenAPI `--check` and generated Catalog client `--check` passed; no schema/client
  regeneration changes are needed.
- Ruff passed for the changed Python sources, tests, factories and native verifier.
  Strict mypy passed for the three changed production files. Both changed factories
  pass strict mypy with imported modules silenced; checking their complete import
  graph also reports three existing untyped functions in `tests/conftest.py`.
- API batch: 33 passed and one activation scenario hit the existing ten-second
  command budget (`test_tracking_activation_without_company_capabilities[batch_tracking]`).
  Its isolated rerun passed in 12.17 seconds for the complete test, with no code,
  assertion or production timeout change. All 34 distinct cases passed across the
  batch/rerun. XML evidence is retained in ignored
  `apis/catalog/.test-results-product-master-review-fixes.xml` and
  `apis/catalog/.test-results-product-master-review-retry.xml`; native output is in
  `apis/catalog/.product-master-native-review.log`.
- Manual equivalents of `/simplify` and `/security-review` were completed because
  those slash commands are unavailable here. Reviewed CLAUDE sections 5/6, basic
  versus authoring access, field policies before references, tenant/company
  rejection, audit/aggregate rollback, idempotency and uncertain retry preservation,
  revision binding/expiry, schema/client compatibility and barcode immutability.
  No unresolved findings in these changes. No dependency, shared-library, model,
  migration, permission catalogue or event contract changed.
- Scoped diff checks passed with CRLF-aware whitespace checking for the existing
  CRLF-tracked product command file. Other in-progress workspace edits were left
  untouched. No commit or publication was performed. Live browser testing and
  whole-repository coverage were not rerun for this correction.

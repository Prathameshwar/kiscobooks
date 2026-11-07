# Simple product simulation results

Execution started: 2026-11-07. Local work only; no VM update or deployment.

## Todo

- [x] Establish baseline: 142 UI checks passed, 12 failed; 64 native Catalog checks passed, 1 failed.
- [x] Prepare and execute the 10 component configuration fixtures and negative cases.
- [x] Reproduce defects with regression tests, fix, and retest.
- [x] Review native persistence, recovery, pricing and authorization evidence at the levels below.
- [x] Review presentation and browser feasibility; browser geometry remains unverified.
- [x] Complete final review and summarize verified outcomes and limitations.

Baseline logs are under `.review-tmp/simple-baseline.log` and `.review-tmp/simple-native-baseline.log`. Existing files are being changed concurrently; recheck current versions before classifying failures. Native baseline uses SQLite and controlled owner transport, not real stock posting. Several baseline tests assume older opening-cost or optional-command-hash shapes.

## Final verification

- **202 UI checks passed across 12 files**, including all 10 successful configuration simulations, missing-name negatives for each, configuration/access drift, serial/batch boundaries, submission, progress, recovery, directory/settings and proxy policy. Final log: `.review-tmp/simple-final-verified.log`.
- **111 unique native checks passed across the baseline and targeted retests**: 64 already-passing native Catalog checks, the repaired older-hash fixture, 10 captured-client schema checks, 35 negative schema checks, and one native quantity-admission integration test. The targeted run reports 47 passed in `.review-tmp/simple-native-new.log`; the earlier 64 are recorded in the baseline log.
- **Console TypeScript passed**, including new tests. Ruff checks on the affected Python tests and task whitespace checks passed. No shared UI implementation/version change was needed for these app-level fixes.
- Exact opening valuations independently checked with Python Decimal: S02 `1600`, S07 `1600`, S08 `40000`, S09 `524.6625`. These are request/admission calculations, not assertions that real owner services posted stock.
- The UI bodies are captured in `.review-tmp/simple-product/client-bodies.json`; a reproducible native schema fixture is saved at `apis/catalog/tests/fixtures/simple_config_client_bodies.json`.

## Configuration ledger

All ten successful paths and their missing-name rejection checks passed in component simulations. Reference choices and effective form metadata are controlled fixtures, not ten live published companies. Existing native suites provide separate policy, publication, persistence and owner-command checks.

| Scenario | Verified configuration behavior | Additional negative/disabled evidence |
|---|---|---|
| S01 minimal Goods | No pricing/stock/detail inputs in request; automatic-code input remains blank | Disabled/retained-stock clearing; no fabricated pricing milestone; native empty-name rejection |
| S02 required prices and stock | Separate purchase `85`, sale `120`, MRP `150`, opening cost `80`, quantity `20` | Zero purchase/cost/MRP, negative sale/quantity, missing opening cost; required native pricing policy tests |
| S03 optional details | Default-off groups omitted; optional toggles/defaults and omission preserved | Existing detail tests exercise opt-in, opt-out, denied fields and parent changes |
| S04 required details | Required brand/model/barcode/category/manufacturer captured | Required-field gates; category/parent relationships; native series/site-without-parent rejection |
| S05 Services | SAC/prices; no stock or Goods-only tracking in request | Service stock rejected; Goods stock retained across kind change until explicit clearing |
| S06 multiple selling levels | Required Retail/Wholesale; optional level omitted; single sale input omitted | Missing Wholesale; negative/mixed/duplicate level inputs; native sale-level and access tests |
| S07 batches | Two distinct batch costs/prices/quantities and required dates captured | Invalid/missing dates, expiry order, normalized duplicates, invalid codes, 65 batches, retained disabled expiry |
| S08 serials | Derived quantity and separate cost; batch-plus-serial coverage | Invalid IMEI/slots, blank/duplicate identifiers, cross-batch duplicates, 201 serials and aggregate overflow; same-command throttling retry |
| S09 decimal quantities | Exact decimal body and valuation; native three-decimal/0.005 grid admission | Native `12.346` rejected before receipt, `12.345` admitted; excess precision/negative quantities; native mass-unit eligibility tested separately |
| S10 custom fields/access | Required typed defaults retain integer zero and boolean false | Required inaccessible/conditional fields blocked; existing custom type, conditional, reference and server-error checks |

The form simulations do not prove every proposed configuration combination can be published together. Native source IDs, unit eligibility and publication rules remain authoritative; mass-unit eligibility and quantity-grid checks were exercised separately rather than as one fully provisioned Kg company.

## Findings and fixes

| Finding | Fix and regression evidence |
|---|---|
| Invalid batch dates could reach submission | Validate actual calendar dates before creating a request; tests cover impossible February/month/year values and expiry order. |
| Batch duplicate checking differed from native Unicode casefold | Reuse existing native-compatible identifier normalization; `Straße` and `STRASSE` are caught as duplicates. Printable spacing remains covered. |
| Client batch/serial preparation lacked defensive limits | Reject more than 64 batches or 200 serials, including aggregate serial count across batches, before submission. Native schema limits remain intact. |
| Required inaccessible custom fields could be omitted from client validation | Check applicable required fields independently of writable fields; show an access blocker and prevent submission. Preserve valid false/zero defaults. |
| Initial/recovered statuses were used before checking company scope | Verify company and creation identity before displaying or driving work; keep uncertain recovery state when verification fails. Native authorization remains unchanged. |
| Reload automatically drove an editable rejected command | Stop at the verified editable receipt and offer Correct details. Existing same-key recovery continues for uncertain work. |
| Selecting the current group erased the base unit | Ignore unchanged reference selections; no extra options refresh or related-field reset. Changed parent references still invalidate dependent selections. |
| Disabled stock could leave hidden quantity blocking the form | Include retained opening quantity/cost in explicit unavailable-data clearing. Clear resolves the blocker without dropping unrelated input. |
| Goods-to-Service switching silently discarded opening/tracking data | Preserve incompatible quantities, prices, batches and serials. Surface unavailable-data resolution; switching back preserves entries until they are deliberately cleared. |
| A no-price product still showed a completed Prices milestone | Omit uncaptured pricing stages; include them when a native pricing stage provides evidence. Keep server-confirmed completion and opening-posted messages. |
| Older tests no longer described the current contracts | Update fixtures for separate opening unit cost, additive optional hash exclusions, restored record links and retained uncertain-review keys. No monetary or server idempotency behavior was changed to satisfy them. |

Regression-first evidence: the initial new regression run reported 15 failures; later targeted runs reproduced two dropdown/config-drift failures, the Goods/Service preservation failure and the no-price milestone failure before their fixes. All corresponding checks are green in the final run.

## Final review and remaining limits

Reviewed field labels/focus, required and disabled gates, native decimal separation, command-key reuse, company/creation response validation, reload/edit behavior, parent selection preservation and token-based shared styling. No further findings in those reviewed paths. Existing style/DOM evidence cannot establish actual viewport alignment or paint behavior.

The repository requests `/simplify` and `/security-review`; those commands/skills are not available in this session. Performed the corresponding manual code and security/invariant review instead. Scope checks cover client response handling plus existing native tenant/field authorization tests; no server authorization, money posting, audit or immutable feature rules were weakened.

Browser execution was previously blocked on this workstation, and no browser connector is available here. Desktop/tablet/mobile geometry, all-theme screenshots and real network navigation remain **unverified**. Component checks confirm bounded requests and value preservation for unchanged/changed dropdown selections; they do not prove browser paint performance.

Native integration uses SQLite and controlled Accounting/Vouchers readiness/transport. Real stock posting, MySQL/RabbitMQ behavior, worker deployment, maximum-volume performance and live source propagation are **unverified**. The new quantity test mocks only opening-owner readiness and exercises native configuration, admission and stored receipt data.

Local fixes and the listed automated checks are complete. Full production reliability signoff remains pending the browser and actual owner-service checks. No VM update, deployment, commit or publication was performed.

# Advanced product configuration scenario execution

Scope: execute the approved [10-scenario plan](advanced-product-scenario-test-plan.md), fix reproduced compatibility/stability issues, and review the result. Local work only; no VM update.

- [x] Phase 1: Prepare configuration/input fixtures and reproduce negative cases across scenarios 01-10.
- [x] Phase 2: Fix configuration, field and feature compatibility; rerun regressions.
- [x] Phase 3: Test saved creation, progress, recovery and native contracts; fix reproduced stability failures.
- [x] Phase 4: Final affected checks, simplification/security review and evidence summary (scope limits below).

Execution distinguishes simulated UI/payload checks, native API tests with a local SQLite database, and actual multi-service stock/browser tests. Pending/blocked checks are not counted as passed.

## Scenario execution

The scenario fixtures exercise the real client validators, native command builders and creation driver. The driver receives controlled simulated owner responses. Each exact generated request was separately validated by the current Python schemas. This does not mean ten products were created on a live company.

| Scenario | Client validation / simulated creation | Python request schemas | Independent expected opening valuation | Negative coverage |
| --- | --- | --- | --- | --- |
| 01 Minimal non-stock Goods | Passed; one SKU, no invented prices/opening | Passed | 0.0000 | Disabled retained Profile data; incompatible SKU bounds |
| 02 Required prices and stock | Passed; purchase reference remains separate from opening cost | Passed | 1600.0000 | Missing price references/jurisdiction/cost/date, unavailable required pricing |
| 03 Variant apparel | Passed; four distinct SKUs, two openings and two skips | Passed | 3600.0000 | Duplicate code/combination, required brand, disabled axes and explicit removal |
| 04 Service and price levels | Passed; service estimate, two selling levels, no stock | Passed | 0.0000 | Goods-only Type, retained physical MRP and unavailable fields |
| 05 Required batches and expiry | Passed; separate costs and references on two batches | Passed | 1600.0000 | Duplicate/normalized codes, expiry ordering, impossible dates, stale price levels and disabled MRP |
| 06 Serialized Goods | Passed; two serial rows retained with exact costs | Passed | 40000.0000 | Duplicate and missing serial identifiers; existing native serial-shape checks |
| 07 Alternate units and precision | Passed; exact 1/1000 and 25/1 ratios, fractional base quantity | Passed | 524.6625 | Binding increment/precision mismatch; stale/mismatched unit defaults; explicit clearing of disabled units |
| 08 Required fields and access | Passed; Boolean false and Integer zero retained | Passed | 0.0000 | Required custom fields and native-field access, missing/denied pricing; existing native field/scope denial tests |
| 09 Configuration change / recovery | Passed in controlled source and receipt simulations | Passed | 1600.0000 | Stale pricing, partial setup locks, same-request retries, unmount, definite initial rejection, source refresh |
| 10 Extended pricing options | Base-price creation passed; scope limitation confirmed | Passed for captured inputs | 0.0000 | Additional enabled options identified without inventing their values or authoring controls |

## Reproduced findings and fixes

1. **Disabled saved Profile details could be submitted.** Brand/series, model, categories and physical manufacturer details now receive configuration/kind checks. Removal is explicit and preserves allowed data. A deliberate Goods-to-Service change retains entered details for review.
2. **Required configuration and metadata were incomplete in client validation.** Added brand/model/category requirements, core-field and required-field access checks, and custom-field checks using the same defaults and visibility conditions as the shared editor. False and zero remain valid values.
3. **Incompatible Product Types and variant structure could pass local validation.** Validate Type kind, disabled/required axes, the bounded SKU count and axis count. A single retained SKU can explicitly remove obsolete axes and their values; extra SKUs are not silently collapsed.
4. **Pricing could be missing or silently omitted.** Required prices fail clearly when levels/access are unavailable. Disabled purchase/MRP values and stale selling-plan entries are blocked, with an explicit removal action. Service MRP and prices for unavailable trade directions are rejected.
5. **Unit precision could disagree with its increment.** Binding increments must fit their configured decimal places. Existing exact whole-number conversion and pack-type checks remain in place. Disabled retained bindings now have an explicit clearing action.
6. **Per-unit defaults could remain stale after source changes.** Refresh on source/policy version changes, verify unit and version identity, expose a reload action, and hold Business Continue until current defaults are verified. Saved completed setup does not need to re-enter its already confirmed rules.
7. **Batch pricing and tracking changes could leave inaccessible retained values.** Validate stale/disabled batch prices and tracking details, and offer explicit removal while retaining valid opening quantities, valuation costs and purchase references.
8. **Batch validation missed normalized duplicates and impossible dates.** Reuse native-compatible Unicode identifier normalization and valid-calendar-date checks before creation.
9. **Recovery revalidated locked completed work against new authoring rules.** Validation now targets remaining editable work, verifies receipt/item correspondence before excluding completed fields, and keeps native checks and immutable-definition/revision guards authoritative.
10. **A definite initial validation rejection trapped the user in progress.** Before a creation receipt exists, a 422 rejection can return to editable details with retained work and field errors. Uncertain results keep the same frozen request; they do not offer an unsafe restart. Returning unsaved work is marked dirty.
11. **Extended pricing coverage was unclear.** Enabled alternate-unit prices, tiers, channels, currencies and formulas are explicitly described as outside this creation form. No extra prices/formulas/currency conversions are fabricated. This is a disclosed coverage limitation, not an implementation of those missing inputs.

Existing duplicate code/variant checks, missing price source errors, serial normalization/count rules, owner wait retries, request identity, completion focus and company-bound reference checks were also exercised. No changes were made to native posting or monetary calculations.

## Evidence and verification

- Initial configuration matrix: **14 passed, 8 failed**; all ten valid baselines passed and the negative failures reproduced the first compatibility gaps.
- Additional regressions reproduced stale defaults, completed-work revalidation, hidden retained-data traps, invalid normalized batch/date inputs and initial-rejection recovery before their fixes.
- Local Catalog API suite: **27 passed** in 110.78 seconds across definition, setup, opening and private draft tests. This suite uses SQLite and controlled source/owner transports. It covers authorization/scope, field denial, exact prices, rollback, variant progress, opening retries and draft/mode stability. A pytest cache write warning was non-blocking.
- Exact client bodies: **36 Python schema checks passed** across ten definitions, thirteen SKU setups and thirteen opening choices. **10 independent Decimal valuation checks passed** with the values shown above.
- Scenario tests are in `advanced-config-scenarios.test.ts`, `advanced-config-creation-flow.test.tsx`, `advanced-config-ui.test.tsx` and `advanced-config-recovery.test.ts`, alongside the existing Advanced suites.
- Final Advanced suites: **105 passed, 4 browser tests skipped** across 18 files. This includes the ten-scenario creation simulations and the new compatibility/recovery regressions.
- Console TypeScript check and task whitespace check: **passed**.

## Final review and scope limits

Manual simplification review consolidated compatibility/removal helpers and validation of remaining work. Manual security/invariant review checked tenant-bound requests and metadata, protected references, immutable completed work, exact decimal strings, separate purchase-reference/opening-cost values and same-request recovery. No native permission bypass, arbitrary request target, monetary calculation, posting, migration or API contract change was introduced. The unavailable slash-command review integrations were covered through direct source/test review.

Four browser tests remain skipped because of this workstation's browser process restrictions. Actual desktop/tablet/mobile geometry and all-theme screenshots remain open. No live Accounting/Vouchers stock-ledger or MySQL end-to-end run was performed; simulated progress and schema validation are not evidence of a real stock posting.

Additional unit/tier/channel/currency/formula authoring inputs, the separate compound/measured conversion flows, performance at maximum bounds and exhaustive configuration combinations remain outside the verified creation coverage. Full compatibility across those features and live production stability are **not** signed off.

No VM access/update, deployment, commit or publication was performed.

State: planned local simulation, native contract/API checks and reproduced fixes are complete. The limitations above prevent an unconditional full-feature or production stability sign-off.

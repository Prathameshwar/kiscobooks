# Advanced product creation UI fixes

Authorized plan: implement locally in sequence; do not update the VM. Preserve existing concurrent work. Review baseline: [advanced-product-ui-review-2026-11-07.md](advanced-product-ui-review-2026-11-07.md).

- [x] Phase 1: Keep dropdown refreshes in place; preserve focus and names; avoid redundant default requests. Regression tests.
- [x] Phase 2: Align controls, improve responsive spacing, simplify headers/actions, and provide readable labels and descriptions. Regression tests.
- [x] Phase 3: Clarify and group purchase/sale/MRP entry, numeric handling, requirements and unavailable states. Regression tests.
- [x] Phase 4: Resolve review references and policy names, include typed variants and complete batch prices, deduplicate errors. Regression tests.
- [x] Phase 5: Run executable local tests/type checks; final simplification/security/correctness review; record remaining limitations.
- [ ] Browser geometry and screenshots at desktop/tablet/phone widths in all themes. Blocked by this workstation's browser process restrictions; no VM used as a fallback.

## Verification and progress

Initial standard Vitest execution could not launch esbuild (`spawn EPERM`). Tests subsequently ran locally using Vitest with a TypeScript transform and a single worker thread at a time. The runner disables only Vite's optional Windows network-drive probe and avoids esbuild's unavailable child-process pipes. Production source and test assertions are used unchanged. No VM access or update was performed.

Phase 1: regression tests reproduced disappearing fields and a second default-driven options request. Fixed form retention and default request deduplication; existing wizard plus refresh tests pass (6 tests). Context selectors remain operable during refresh; dependent metadata fields and continue/save remain blocked.

Phase 2: replaced native selects with shared controls, reset grid sibling margins, improved tablet SKU layout and wrapping, reduced nested padding/header repetition, added sticky actions and multiline Description. Readable native labels preserve tenant overrides. Restored references resolve via scoped detail reads, with unavailable labels for denied/mismatched records. All 9 affected tests pass; browser layout verification remains in Phase 5.

Phase 3: grouped purchase/sale/MRP, explained purchase-reference versus opening valuation, added conditional required markers and field-specific source/jurisdiction errors, explanatory unavailable/disabled states, shared amount inputs, and batch tax hints. Wizard and SKU navigation/save are blocked for unstorable visible amounts. Pricing/draft/creation progress suites pass (9 tests); added numeric regression for the final pass. Batch-only entry stays in opening or subsequent batch management, as the existing workflow defines.

Phase 4: replaced raw reference identifiers with scoped readable names, respected visible Profile fields, displayed scalar variants including false values, completed batch purchase reference/MRP/dates/tax summaries, and retained serial identifiers. Removed duplicate inline errors and kept batch-level errors visible. Added Goods/batch, ordinary opening, Service, hidden-field, and typed-variant regressions.

## Final review and verification

- Advanced: 42 distinct tests pass across the full suite and final affected reruns. The full run before the last four regressions was 38 passed / 4 browser tests skipped; subsequent affected runs passed all additions (18 tests across five files, then 5 review tests).
- Shared UI: 53 tests pass across numeric fields, wizard layout, setup layout, and the new product wizard CSS contracts. The three new CSS contracts reproduce failures against the original stylesheet and pass against the updated stylesheet.
- Product navigation/restoration checks: 6 tests pass.
- Console TypeScript check: passes. A parallel final attempt encountered a transient Node memory allocation failure; the sequential retry with a 2048MB heap limit passed.
- Changed-file whitespace check: passes, with Windows CRLF treated as line endings.
- Broader Simple comparison: 41 tests pass / 7 fail in the existing Simple ready suite. Opening-stock success fixtures supply Purchase price and quantity but omit the separate Opening unit cost. The reviewed files do not import the changed Advanced helpers, and CSS is disabled in these tests. Simple creation implementation and fixtures were preserved; these failures are outside this Advanced task.
- Browser checks: unavailable. Automatic approval review rejected starting Chrome with a debugging port (`blocked by policy`). A standard headless Chrome attempt then failed with denied crashpad/Mojo IPC. Four existing browser tests remain skipped; actual geometry, screenshots, and production E2E persistence are not signed off.

Manual simplification review: consolidated numeric error tracking; removed stale labels and redundant default requests; cleared stale revision choices while loading. Fixed returning to a previously resolved context leaving loading active.

Manual security/correctness review: tightened reference response validation by resource type, checked company/id/parent on detail reads, kept mode/access locks active during refresh, retained native field metadata and configured labels, and preserved decimal strings and separate purchase-reference/opening-cost values. Definition submission, native authorization, idempotency, activation, and stock posting contracts are unchanged. No new unresolved finding in the changed paths. The `/simplify` and `/security-review` slash-command integrations were not available, so these reviews were performed directly against source and regression tests.

Native whole-draft preflight, full published policy terms, and carrying-value previews remain existing product-roadmap work in `advanced-product-creation-todo.md`; this UI task resolves policy names and captured review facts.

State: all planned local implementation phases complete. Browser sign-off and the existing Simple-suite failures remain explicitly open. No VM update, deployment, or repository publication.

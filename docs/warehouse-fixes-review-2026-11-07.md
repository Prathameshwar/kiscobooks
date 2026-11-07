# Warehouse fixes: local review, 2026-11-07

All eleven findings in `warehouse-config-stock-management-review-2026-11-07.md` have local fixes. VM deployment remains deferred. The maintained checklist is `warehouse-fixes-todo.md`.

## Result

- Warehouse settings now provide company policy publication, delivery state, same-day delivery retry, history and consumer acknowledgements. Writes use the existing audited, versioned owner commands.
- Group memberships ending today or in the future still prevent warehouse retirement. Historical closed memberships do not prevent it.
- Uncertain standalone creation freezes the identity and retains the original idempotency key. Additional warehouse creation follows native feature and field access gates.
- Native writes validate IANA timezones and signed, current company-owned tax references, including jurisdiction. Inventory-off enrollment provisions Main/Transit metadata without moving stock.
- Stock contracts carry warehouse address, country/state, timezone and tax reference. Purchase goods calculation validates the receiving warehouse registration and retains its evidence. The existing goods execution scope is Purchase; this change does not add a Sales GST engine.
- Products expose location permissions, activity defaults and replenishment maintenance. Reviewed replacement commands preserve stock/history and use generation/source guards.
- Reports receive dated warehouse groups and memberships, with group nodes excluded from transactional destinations and sale eligibility. Warehouse operation policy and product policy constrain eligible stock without changing recorded quantity or value.
- Reservation quantities and reservation availability remain unknown and visibly unavailable, as the user requested. No stock reservation engine was added.

## Review corrections

Review found and corrected loss of unsaved replenishment after saving location permissions, preservation of dirty-editor generations against concurrent replacement, accidental clearing of an uncertain command key, stale creation permissions, incomplete policy review summaries and missing warehouse labels. Charge-editor visibility also keeps denied fields read-only instead of allowing writes when component metadata is absent.

Native command permissions, company/tenant scope, signed preflight expiry, exact quantity strings, audited replacements and source fences were checked manually. No new ORM columns, tables or DDL were introduced. Reporting and execution contract versions, consuming editable lock records, OpenAPI and generated TypeScript clients were synchronized.

## Validation

- Catalog warehouse API/default/reference/reporting/source suites: 29 passed.
- Catalog operations/groups/policies/releases/resolution: 70 passed on the broad run; one existing retirement test lacked the native-owner fixture. Adding that fixture preserved the owner safety guard. The affected policy and tax suites then passed all 14 tests.
- Catalog warehouse address/tax fact handoff suite: 5 passed.
- Reports warehouse eligibility/group regressions and inventory suite: 64 passed.
- Accounting warehouse registration/evidence and stock summary suites: 6 passed; the earlier goods invoice suite also passed.
- Identity signed warehouse gateway context: 1 passed.
- Voucher domain, including actionable missing-section errors: 42 passed.
- Actual React/JSDOM checks: uncertain standalone creation; product policy draft preservation; read-only releases; uncertain release publication; BFF route restrictions; new product Purchase charge visibility/access. All passed.
- Scoped Ruff and strict mypy checks passed. API exports and generated clients were checked after regeneration. Console TypeScript was checked, including the new screens.

The normal Vitest runner cannot start in this Windows sandbox: esbuild fails with `spawn EPERM`. Standard regression tests are present, and corresponding actual-component checks run in `docs/testing/warehouse-fixes/regressions.cjs` and `docs/testing/warehouse-review/probes.cjs`. This is targeted verification, not a claim that the complete UI suite or coverage floor ran. The requested simplify/security skills are unavailable in this session; their checks were performed manually.

Python tests used a workspace temporary directory with a process-local directory-mode workaround for the sandbox ACL. The uv launcher could not resolve local locks in this environment; the lock update changed only editable local contract version records and verified TOML parsing. Some earlier private temporary directories could not be removed because automatic approval review rejected cleanup; application paths and unrelated work were preserved.

## Live side checks

Read-only checks on BTCL confirmed that P&L initially requested April 1 although retained history begins November 6. The local P&L fix and evidence are recorded in `profit-loss-loading-review-2026-11-07.md`.

BTCL's Purchase draft was bound to the current type revision, with Charges and Tax marked required, no entered charge, and an accepted calculation. Local changes make charge entry conspicuous below the product grid, show its field-access state, distinguish optional charge enablement from required sections, offer Make charges optional for conflicting configuration, and name missing sections. Enabling Allow Purchase charges removes the contradictory required/forbidden Charges selections. Existing live configuration and financial records were not rewritten.

# Company product configuration consumer review — 2026-10-30

Authorization: review the complete configuration workflow and every place its
settings are consumed; reproduce and fix gaps, retain reusable findings.

## Quick plan for the adoption/version correction

1. Reproduce Company profile VALUE/CLEAR being lost after a successful adoption.
   Cover old historical pins as well as preview → adopt → read → readiness and
   unit/price default consumers. Also check publication against its configured
   default product types before new-product usage.
2. Add a native adoption resolution-version column with one additive Catalog
   migration. Existing rows default to the original semantics; new adoption writes
   bind the Company-only semantics. The marker is server controlled and included
   in adoption review evidence. Reject unsupported versions and retired sources
   in new-version pins; never rewrite saved history.
3. Trace and verify new product/service/family/SKU creation, setup, profile
   defaults, units/quantities/prices, activation/readiness, bulk/import and the
   console entry links. Fix medium/low findings directly with fail-first checks.
4. Regenerate contracts; run affected native/UI tests and a disposable migrated
   MySQL verification. Review security, field policy, exact values and immutable
   snapshots; update the CSV and final report with deployment requirements.

## Todo

- [x] Trace current/proposed resolution and persisted adoption consumers.
- [x] Fail-first adoption and configured-type publication regressions.
- [x] Versioned adoption model/migration, native guards and matching contracts.
- [x] Consumer/UI flow findings and fixes.
- [x] Native/UI/MySQL/static verification and final review/CSV.

Final evidence: 159 distinct native cases passed; the optional Docker roundtrip
was skipped. Four dedicated MySQL checks, 405 UI cases and 72 browser checks
passed. The 91-case integration run initially passed 90 and found one obsolete
Type-scope fixture; its corrected three-case profile suite passed. The final
31-case publication/consumer batch passed after simplification. Ruff, mypy,
TypeScript and generated contracts passed. The CSV records 27 PASS and two
NOT_RUN deployment/live-VM cases, with no unresolved functional review finding.

The combined VM remains shut down. Verification uses isolated databases and
browser fixtures; no live tenant data or grants are manipulated. A migration
must run before deploying the changed Catalog API. Existing published/adopted
documents must retain their original configuration and exact numeric rules.

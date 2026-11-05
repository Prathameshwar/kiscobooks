# Tenant administrator fixes: steps 4-6

Steps 4-5 are implemented and the supported step-6 workflow is verified through
submission. Actual posting remains blocked by the existing release prerequisites.
The original acceptance findings remain historical evidence; this batch is recorded
separately in [the results CSV](tenant-admin-fixes-4-6-results-2026-10-29.csv).

## Implemented and verified changes

- Return-policy condition metadata now keeps its parent `revision_id` readonly in
  ordinary forms. Child publication continues checking its field authority through
  the existing aggregate transaction. The original readonly regression failed
  before this fix; the affected Catalog security/return suites passed nine tests.
- Invoice-designer gallery tests retain pointer checks but cache them per target,
  enter publication summaries using a real paste event and give the two-publication,
  restore-and-undo scenario its own ten-second budget. This fixes measured jsdom
  timing, with publication/restore/undo assertions preserved. All 26 gallery tests
  passed. Product-attribute tests passed 24, including an explicit valid-dirty Save
  eligibility assertion; no production attribute change was needed.
- The live designer exposed an additional gap: native publication reloaded version
  metadata without historical layouts, so restore was unavailable. The editor now
  loads only the selected published version through the existing company/template
  API, validates identity and editable format and records one undoable edit. Failures
  preserve the current layout. Concurrent restore, editing, undo and writes are blocked
  while loading. The live retained template restored grid 20 and one undo returned
  grid 2; three native-editor and five version-read regressions passed.
- Sales UI modes now intersect the effective type's `allowed_modes` with supported
  supply kinds and use its configured default when available. Two added regressions
  reproduced the prior disallowed Mixed mode and ignored Accounts default before
  the fix. Sales wire/connected tests passed 24.
- Configuration reference options for `items` reach their own closed policy rather
  than being captured by ordinary item-route classification. A composed-policy
  regression failed before the fix. Configuration suites passed 89 tests; supported
  lookup methods/sources/queries remain bounded and unsupported requests are refused.

## Retained tenant and business configuration

The same active QA tenant and three company profiles are reused. Their exact display
and account differences remain in [the current fixture register](testing/tenant-admin/business-fixtures-2026-10-29.csv). Synthetic customers and
receivable accounts are active in all three companies, with active native Sales
types constrained to supported account/service entry. Published official seeded
HSN 8471 or SAC 998313, TAXABLE treatment and 18% rule bindings resolve for purchase
and sale. Retail has a published FIFO inventory profile; Distribution has published
moving-average valuation. Both block negative stock. Services uses no stock profile.

Publishing another company-default revision intentionally suggests a later effective
date. The inventory company defaults start after today's initial defaults; their
history is preserved. The activation setup uses a permitted product override effective
2026-10-29, then explicit draft adoption and activation. All three products are ACTIVE.
No posted product history or immutable company setting is rewritten.

An ignored local environment connection pairs Vouchers with Accounting for exactly
the three QA companies. Credentials remain in environment files and are never included
in reports. Existing execution flags remain disabled. This connection permits signed,
scoped read-only invoice preview with the real actor authority; it is not financial
release activation. The managed Catalog, Accounting and Vouchers APIs were restarted
for live verification. Catalog's initial startup exceeded the harness readiness budget
and then became ready; the existing process was retained.

## Live Sales coverage and remaining release boundary

All three UI account-bill paths passed draft creation, exact idempotent replay,
authoritative readback, calculation, acceptance and submission. Authoritative payable
was 123.4500 in Retail, 125.1250 in Services and 99.0000 in Distribution. These use the
explicit supported `UNTAXED_ACCOUNT` profile, with zero tax and rounding. They do not
demonstrate a taxed product sale. Wrong-company reads and self-approval were refused,
and the document/version remained unchanged. Final owner reads verified zero posted
journals, invoice records and open items, plus zero stock positions/movements/postings
for the stock companies. Published GST components total exactly 18% in each product
resolution. Keyboard and click command-palette
navigation passed in all three companies. Live readonly metadata checks also passed.

Actual Sales posting, goods stock effects and statutory issuance remain unavailable:
invoice and stock execution are disabled, C2/C3 prerequisites remain unverified, and
the statutory Sales profile is not released. A successful draft/preview/submission
does not satisfy those release gates. Accounting's isolated invoice/tax/reporting
suite passed 11; Vouchers invoice-capture/posting tests passed 41. Those tests cover
their named fixture effects and cannot be relabeled as posted live-tenant evidence.

## Reuse

Run these from the repository root after starting the local services:

```powershell
node docs/testing/tenant-admin/configure-business.cjs
node docs/testing/tenant-admin/configure-sales.cjs
node docs/testing/tenant-admin/verify-business.cjs
node docs/testing/tenant-admin/verify-designer.cjs
node docs/testing/tenant-admin/verify-business-readback.cjs
```

`QA_COMPANY_KEY` optionally restricts a run to `retail`, `services` or `distribution`.
Runs use real provider UI login and retained DPAPI-encrypted credentials. Ordinary
native APIs are used only when needed; non-Identity native calls are restricted to
the retained QA companies, and real provider tokens stay in memory. Existing IDs and
owner readback are used to resume setup; writes retain idempotency keys. Live result
JSON, screenshots and fixture IDs remain in ignored artifacts. Harness navigation,
dialog scoping and response-body timing failures are preserved as harness evidence,
separately from confirmed application defects.

No direct application database manipulation, release activation, commit or publication
was performed. Full unrelated feature suites and the original individually unexecuted
UI cases were not reclassified as passing.

## Verification and review

The affected Console files passed 205 unique tests in focused runs: design editor/read/
canvas 57, product attributes 24, Sales wire/connected 25, configuration 89 and ordinary
classification policy 10. Catalog's affected security/return suites passed 9; Accounting
invoice/tax/reporting passed 11; Vouchers invoice-capture/posting passed 41. Console
TypeScript, Catalog metadata strict mypy/Ruff and script syntax/whitespace checks passed.
These counts do not claim a full Console or repository rerun. The final CSV records
28 live PASS cases and two blocked release gaps. Final owner readback completed at
2026-10-29 15:40 UTC; all six fixture/reconciliation cases passed.

Manual simplification and security review walked CLAUDE.md sections 5 and 6. The named
`/simplify` and `/security-review` commands are unavailable in this session; equivalent
manual review was performed. Review found the missing native restore action and its
loading-state race, both corrected with regressions. No unresolved issue was identified
in the changed scope. Existing company/object/field authorization, immutable published
versions, exact decimals, idempotency, posting admission and transaction/outbox boundaries
remain intact. No model, migration, permission catalogue, shared library, dependency or
API response schema changed. The native API helper reads current encrypted session cookies
and uses the real Auth refresh boundary when needed, preserving the same write key on retry.

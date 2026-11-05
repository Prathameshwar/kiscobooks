# GSTR-3B delivery and review

Authorized 2026-11-02: implement the approved eight-phase plan, then review and fix
findings. Existing dirty and staged workspace changes are preserved. Publication
was not requested.

| Phase | Status | Acceptance |
|---|---|---|
| 1. Official form/rules | Implemented | GSTR3B_2025_10; prescribed mappings, October 2025 advance change, exact INR |
| 2. GST setup/readiness | Implemented | Native registration UI and dated Monthly/QRMP preferences; incomplete setup refused |
| 3. Statutory source records | Implemented | Audited immutable allocations; native supplies, credit actions and legacy GST journals |
| 4. Calculations | Implemented | Tables 3.1, 3.1.1, 3.2, 4, 5, 5.1 and 6.1; separate cash/ITC/offset workings |
| 5. Reconciliation/review | Implemented | Frozen preparations, missing evidence and comparison exceptions, reviewer proof and external filing history |
| 6. Workspace | Implemented | GST card, statutory selectors/sections, amount drill-down, search, columns, kebab and drawer |
| 7. Print/exports | Implemented | Statutory PDF, exact Excel, full-detail CSV and private preview/download; portal upload JSON remains unavailable |
| 8. End-to-end review | Reviewed | Native MySQL, owner APIs, artifacts, UI, permissions, live eligibility and fixture-assisted populated browser review |

The GST Portal FAQ retrieved for the plan documents the October 2025 Table 3.2
advance mapping change. GSTIN and filing periods are separate from company fiscal
year and posting-date controls. Statutory source gaps must remain visible rather
than being represented as zero or a filed return.

The subsequent [GST/GSTR-3B final review](gstr3b-final-review.md) records additional
source commitment, ITC classification, coverage, rounding, ECO and Nil fixes and
their verification separately from this original delivery.

## Delivered workflow

For an Indian GST company, the dedicated Company GST settings page exposes GST registrations
using Identity's state, regime and field schema. Registration history remains
dated. GSTR-3B filing setup records a confirmed Monthly or QRMP preference per
GSTIN; frequency is never inferred from turnover or accounting financial year.
Only complete statutory months or calendar quarters are accepted.

Accounting captures reviewed allocations through its native financial command,
with idempotency and audit in the same transaction as source publication. The
workspace accepts reviewed batches of 1–200 records and offers the owner's field
guide. Native supplies must match their posted source amounts, treatment, GSTIN,
reverse-charge status and, for 3.2, recipient/place of supply. Credit actions must
match their native amount/head and reversal/reclaim lineage. Legacy journals need
retained native GST Tax Analysis. External certificates, portal comparisons,
opening ledgers and actual offsets require retained proof hashes and explanations.

Reports uses a verified frozen Accounting cut, selected GSTIN and allocated return
period. Current credit actions on older invoices and unallocated native GST
journals are included in readiness checks. Registration, rules, source identity,
amounts and statutory row order are retained with the preparation.

The workspace at /reports/workspace?report=GSTR3B has fixed statutory form
columns and selectable supporting columns. Amounts open filtered contributors;
global search includes the entire frozen result. Row actions open a drawer, with
source voucher navigation when authorized. Refresh, source refresh and all
exports share one compact action row. Saved preparations reopen their frozen
result and separate review/filing history.

Missing coverage, stale source evidence, reconciliation differences, invalid ITC
utilisation or an unallocated GST source produce Needs attention. Explicit
no-activity evidence is required for a Nil return. A cash deposit is never treated
as payment. RCM, section 9(5) ECO liability, interest and late fee use cash.
Interest/fees and ordinary, RCM and ECO unpaid balances remain separate.

Internal review requires a retained evidence reference/hash. The UI computes the
hash from a chosen local file; the original remains with the working papers.
Externally Filed records an actual acknowledgement and filing date after review
and reconciled offsets. It performs no filing. Filing proof is immutable, and a
filed GSTIN/period cannot be prepared again; corrections use subsequent periods.

PDF uses statutory section order, tax-head order, fixed Table 5/6.1 layouts,
prior-period liability breakup, signatory/declaration placeholders, provenance
and paginated contributors. Excel contains corresponding form, comparison,
exception, offset, ledger and verification sheets. Exact decimal strings avoid
Excel's precision loss. CSV contains the complete supporting result.

## Access and review fixes

All discovery, capture, preparation, review and downloads check current
tenant/company authority. Complete-input reports refuse hidden contributing
fields. A report reader can inspect authorized history; preparation additionally
requires scoped ledger.post_journal, accounting.finance.manage or
report.definition.manage. Capture needs ledger.post_journal; review and recording
external filing need accounting.finance.manage; export needs report.export.
Company GST setup needs company.tax_registration.manage. Support impersonation
cannot prepare, capture, configure or review.

The manual simplify/security review covered native scoping, complete inputs,
source closure, immutable evidence, audited idempotency, exact money, download
revocation and bounded source/search/export processing. The slash-command tools
were not available; this was a manual equivalent review.

Findings fixed include undeclared audit events, missing native source references,
UUID conversion in MySQL lookups, action scans missing older invoices, arbitrary
journals masquerading as offsets, ordinary purchases relabelled as RCM,
unsupported zero-rated/ECO relabelling, fabricated INR conversion rates, ITC
own-head/IGST order, incomplete portal coverage, inaccurate Table 5/6.1 layouts,
reader preparation authority, filed-period re-preparation and MySQL JSON key
ordering changing Table 4 row order. Changing GSTIN, period or verified source
clears the previous form and review proof; saved history restores its own
selectors. Source lookups are batched and bounded;
drawers and menus keep table row height stable. PDF headings remain with their
section, monetary columns align correctly and a trailing spacer cannot produce
an extra blank page.

## Verification and operational readiness

- Disposable native MySQL: Identity 7 tests; Accounting 12 tests; Reports 61 tests
  including tax workspace regressions. New model/column/index parity and
  downgrade/upgrade checks passed. Artifact tests cover actual private PDF,
  Excel and CSV bytes, statutory headings/order and frozen parent identity.
- UI: 55 targeted company configuration/GST tests passed, followed by the final
  7 GST tests after access refinements. Existing tax card/navigation/download
  regressions were also exercised. Scoped Console application/test TypeScript,
  strict owner-code mypy, Ruff, OpenAPI and generated-client checks passed.
- Browser: live GST applicability/catalogue agreement and direct navigation;
  populated fixture-assisted statutory form, search, kebab/drawer, evidence file
  hashing, review/history and actual native-generated downloads; Light, Dark and
  Ledger at 1440 and 390 pixels. The populated case uses explicit intercepted
  test responses over the authenticated shell, not synthetic live postings.
- Local owned migrations are Identity 0096, Accounting 0228 and Reports 0039.
  Managed APIs and report workers were refreshed; readiness endpoints passed.
- Ignored evidence is under .test_artifacts/tax-reports-review/GSTR3B/.

The currently selected live company has no eligible GST registration. Its GST
card is therefore hidden, and direct navigation explains the required setup.
Configure the company's actual India/GST profile, GSTIN and confirmed dated
filing frequency before preparing its real return. No synthetic GSTIN, filing
frequency or operational posting was added to that company.

## Explicit capability boundaries

Reports revision 0039 adds gst_return_review with standard native scoped/audit
columns, a scoped report_job reference, registration_id, statutory period, state,
reference, evidence_hash, optional filed_date and optional filed_period_key.
Unique tenant/company/job/state prevents duplicate transitions; the nullable
tenant/company/filed-period key prevents two filed versions. Before-flush guards
forbid edits/deletes. Review references the immutable job result; it never
updates frozen financial amounts or source evidence.

The implemented rule version supports October 2025 and later periods. Earlier
periods are refused until a dated historical rule contract is delivered.
Composition, ISD-only, TDS/TCS and unregistered company profiles cannot file this
GSTR-3B workflow.

Imports, ISD, section 9(5), special treatments and portal/ledger reconciliation
need retained statutory evidence; an ordinary domestic invoice cannot stand in
for that evidence. Missing evidence and comparison differences cannot be waived
into an apparently ready return. Negative net ITC is surfaced for resolution.

GST Portal upload JSON is unavailable because no verified official import
schema/workflow was established. PDF/Excel/CSV are preparation artifacts, not
portal upload payloads. Verification and legal filing remain on the GST Portal.
No direct portal filing or payment integration was added.

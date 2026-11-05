# GSTR-3B and GSTR-1 joint end-to-end review

Authorized 2026-11-02: review both implemented returns together and fix findings.
This extends the approved implementation plans and individual final reviews.
Preserve existing local paths and unrelated edits; no publication is requested.

## Review phases

1. Trace company/GST eligibility, dated filing setup, owner capture, source cuts,
   statutory calculations and common workspace state. Add failing regression
   cases for confirmed findings.
2. Correct the findings while retaining immutable histories, exact money,
   native owner boundaries and current tenant/company/field authority.
3. Exercise both returns from the same native source cut: reconciliation,
   separate approvals/filing locks, mismatches, protected histories and downloads.
4. Review browser interactions, print/export artifacts, themes, mobile layout,
   static contracts, security and simplification; fix remaining findings.
5. Refresh affected local services/workers and record final verified outcomes
   and live-company limits.

All five phases are complete. Native, UI, contract, paired browser and final
artifact checks passed. Affected local APIs and report workers are ready.

## Findings and fixes

| Finding | Final behavior |
|---|---|
| GSTR-3B chose completeness proofs by document date | Both returns select the highest covered sequence, reject conflicting statuses at that sequence, and require it to equal the selected native cut. GSTR-1 also rejects a proof claiming a future source sequence. |
| Cash payment bypassed own-head credit priority | GSTR-3B checks own-head credit order before cash payments. Cash cannot disguise credit being diverted to another tax head. |
| GSTR-3B historical calculations could receive new approval | Calculation revision 1 is required for new GSTR-3B review/filing. GSTR-1 revision 3 protects the new exact-cut check. Historical copies remain readable and existing identical review replays remain idempotent. |
| A new GSTR-1 comparison could use outdated GSTR-3B calculations | Admission and worker extraction require a current GSTR-3B preparation for the same actor, company, GSTIN, period and source cut. |
| Company switching retained the previous return | The common workspace remounts on company/return changes. Old results, source drawers, proofs, approvals and selections cannot remain in the new company workspace. |
| Opening/preparing could load rows with a previous filter | Completed-job effects own contributor loading and cancellation. The overlapping imperative reads were removed. |
| Invalid evidence replacement retained the old hash | Selecting or clearing a file clears its previous hash/name immediately. A version check prevents a slower earlier file hash from replacing newer proof. |
| GSTR-3B filing was offered while liabilities were unpaid | The UI explains the unpaid offsets and disables external filing; the server independently enforces reconciled normal, reverse-charge, ECO, interest and late-fee payments. GSTR-1 keeps its separate filing requirements. |
| Prepare was enabled without a covering filing preference | Both workspaces require one matching dated Monthly/QRMP preference covering the full selected period. Missing or mismatched dates/frequency remain visible with setup guidance. |
| Source capture accepted an explicit non-Indian GST registration or third-month IFF | Accounting rejects both before immutable evidence is created. Existing legacy owner contexts without a country field retain their Indian jurisdiction compatibility; explicit foreign countries are denied. |
| The comparison-enabled GSTR-1 PDF put verification alone on an extra page | Reconciliation row spacing is compact while retaining the body font and alignment. A native regression checks that comparison data and verification share the final page for this paired example. |

Confirmed calculation, capture and UI defects were reproduced in failing
regression cases. New revision/approval controls and shared loading cleanup are
covered by integration/UI checks. PDF and Excel preparations identify
their local calculation revision; government form versions stay unchanged at
`GSTR3B_2025_10` and `GSTR1_2025_10`.

## Joint workflow evidence

The paired native test creates one verified Accounting cut containing detailed
outward evidence and reviewed GSTR-3B allocations. Both returns use the same
company, GSTIN and October 2026 period. It checks:

- Identical outward totals reconcile with zero differences.
- A one-rupee tax mismatch appears in reconciliation and blocks GSTR-1 approval.
- GSTR-1 can be reviewed/filed independently of GSTR-3B payments. Unpaid GSTR-3B
  can be reviewed but cannot receive external filing evidence.
- Once fully offset, both returns can be filed independently, with immutable,
  replayable approval evidence and separate period locks.
- Both filed preparations still produce actual PDF, XLSX and CSV downloads.
  Other actors cannot obtain their download tokens; field denies block records
  and export admission for each return.
- Old GSTR-3B calculations cannot become a new GSTR-1 comparison.

## Verification

| Check | Result |
|---|---|
| Reports native MySQL | 141 passed: both return calculations/APIs/artifacts, existing tax-workspace regression and the six paired workflow cases |
| Paired native artifact capture | Six paired cases passed again after the PDF fix, with the exact JSON, records and six downloaded files saved for browser/visual review; five standalone GSTR-1 export cases also passed |
| Accounting native MySQL | 24 passed: GST allocations, outward source capture, committed native invoice/credit sources and the new country/IFF rejection cases |
| Identity native MySQL | Seven passed: native dated filing preference and outward-profile setup, authority and overlap/close rules |
| Native schema | All three owners checked model/column/index parity and owned downgrade/upgrade; heads remain Identity 0097, Accounting 0229, Reports 0041 |
| Static/contract checks | Scoped Reports/Accounting Ruff and strict mypy passed; Reports OpenAPI and API-client 0.2.54 regenerated; Identity/Accounting freshness checked |
| UI | 49 passed, including company reset, legacy approval, proof replacement, unpaid filing, missing preference and preference date-range checks; the 12 GSTR-3B cases passed again after the test TypeScript correction |
| Types | Console application/relevant test TypeScript and API-client types passed; full repository TypeScript is not claimed |
| Browser | Live GSTR-1 applicability/revision check and both populated paired native fixture checks passed: comparison selection, sections, search, kebab/source drawer, proof hashing, review, external filing, saved history and actual PDF/XLSX/CSV downloads; Light, Dark and Ledger themes at desktop/mobile widths |
| PDF and Excel inspection | Both final paired PDFs are three pages. Statutory tables, comparison, payment offsets and verification were inspected; GSTR-1 comparison and verification now share its last page. Preparation revisions are GSTR-3B 1 and GSTR-1 3 |
| Local readiness | Identity, Accounting and Reports readiness endpoints returned 200 after refresh; all six report workers are running, including the refreshed render worker |

These are separate runs and counts overlap. No migration, shared reporting wire
version, database restructuring, commit or publication is introduced.

The manual security review checks tenant/company scoping, actor-owned jobs,
field denies on records and exports, current calculation/approval authority,
immutable source/preparation/review evidence, company serialization, same-cut
comparison provenance, idempotent atomic audit/outbox publication and protected
downloads. No unresolved security finding remains in the reviewed changes.

The manual simplification review keeps one shared workspace and the existing
source/job/private-artifact pipeline. Proof selection and credit priority have
one calculation path each. Source lookups remain bounded; integrity checks occur
before export projection. Slash-command review tools are unavailable, so these
are equivalent manual reviews.

Evidence is retained in ignored
`.test_artifacts/tax-reports-review/GST-returns-e2e/`: native service logs,
`paired-evidence-mysql.log`, `paired-final-mysql.log`,
`gstr1-exports-final-mysql.log`, `browser-final.log`, `runtime.log`,
`render-refresh.log`, and paired `native/GSTR1/` and `native/GSTR3B/` artifacts.
Individual browser JSON records and theme/mobile
screenshots remain under the corresponding GSTR1/GSTR3B review folders.

## Live-company and filing boundaries

The real QA company has no eligible GST registration. Live checks validate its
hidden cards and direct-route setup explanations. Populated browser checks use
explicit interception over the authenticated live shell and the same paired
native JSON/file bytes verified above. The two source-owner APIs are also tested
against native MySQL; the paired Reports test uses typed reviewed allocations
in a verified source cut. This does not claim a live registered-company posting,
broker delivery or GST Portal round trip.

No synthetic live registration, voucher, payment or filing acknowledgement is
saved. GSTN upload JSON, direct filing, automatic payment and GSTN HSN catalogue
acceptance remain outside the verified implementation. GSTR-1A remains a separate
correction workflow. PDF, Excel and CSV are preparation/review working papers.

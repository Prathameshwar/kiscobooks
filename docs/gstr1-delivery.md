# GSTR-1 implementation and final review

The subsequent [final review](gstr1-final-review.md) records calculation revision
2, amendment/IFF/completeness corrections and the latest verification results.

Authorized 2026-11-02: complete the nine-phase plan and final review/fixes. Preserve
existing workspace changes and original local paths. Publication is not requested.

| Phase | Status |
|---|---|
| 1. Dated statutory rules | Complete: India/GST applicability, B2CL, HSN/AATO, GST FY and statutory cutoffs |
| 2. Setup/readiness | Complete: dated turnover/Rule 14A profiles, annual freshness, Monthly/QRMP and completeness |
| 3. Immutable outward evidence | Complete: scoped exact/idempotent capture, committed native source validation and atomic audit/feed |
| 4. Supply tables | Complete: registered/RCM, B2CL/B2CS, exports/SEZ/deemed exports and non-taxable supplies |
| 5. Supporting tables/amendments | Complete: notes, advances, HSN, actual document series, ECO, IFF and original/revised/differential evidence |
| 6. Reconciliation/review | Complete: outward 3B bridge, optional authorized comparison, immutable separate review/filing locks |
| 7. Workspace/navigation | Complete: tax-report card, sections, search/paging, Columns, statutory/source views, kebab/drawer and saved history |
| 8. Print/exports | Complete: protected frozen PDF/Excel/CSV; conditional portal JSON remains unavailable |
| 9. Final native/UI/end-to-end review | Complete: native/static/UI/browser/artifact review and fixes, local migration/restart/readiness |

The initial verified form covers October 2025 onward. It retains August 2024
B2C threshold and May 2025 HSN rules; effective-date tests prevent accidental
historical use of the current format. Portal-upload JSON has no verified current
schema/utility contract and remains unavailable under the plan's conditional gate.
PDF/Excel/CSV are preparation/working artifacts, not government filing evidence.

Official references and retrieved guidance are listed in the implementation plan.
The manual GSTR-1 FAQ contains stale September credit-note and B2C threshold text;
current implementation uses the dated form mapping and November statutory cutoff.

Identity 0097 owns `company_gst_outward_profile`; Accounting 0229 owns immutable
`gst_outward_record`; Reports 0040 owns separate outward review evidence and 0041
its registration/period source index. Shared reporting contract 0.12.0 and
generated API client 0.2.54 are synchronized with owner schemas and consumer locks.
The workspace is `/reports/workspace?report=GSTR1`.

Native capture verifies complete source-line IDs, committed sales/notes and posted
journals, number/date/value, recipient registration, retained native place of
supply/HSN, actual GST components/rate and explicit INR conversion evidence.
Special export/SEZ/ECO and external statutory evidence require retained proof;
capture does not invent missing profiles. Missing/stale coverage, unallocated
outward sources or unresolved differences block review. GSTR-1 does not require
the GSTR-3B payment/offset workflow. Purchase/ITC/payment activity does not create
outward liability or suppress a genuine Nil return.

Final review corrected invoice-rate rounding before presentation; grouped B2CS,
non-taxable, advance and supplier-ECO layouts; note/adjustment presentation;
amendment differential totals; document membership and document-only Nil status;
annual profile freshness and QRMP limits; credit-note deadlines; comparison
ownership and denied-field access; native rate/currency/POS checks; per-table
column defaults; nested drawer evidence; accessible record captions; and PDF
pagination, numeric alignment and repeated HSN identity. Native test cleanup now
handles self-referenced outward evidence only inside a validated disposable schema
while retaining FK enforcement.

| Verification | Result |
|---|---|
| Reports native MySQL regression | 114 passed, including existing GSTR-3B and tax-workspace checks |
| Latest GSTR-1 native MySQL acceptance | 49 passed after final fixes: rules, calculations, scoped API/review and actual PDF/XLSX/CSV download |
| Accounting native MySQL | 19 passed; exact columns/indexes and reversible 0229 migration verified |
| Identity native MySQL | 7 passed; setup/profile authority, overlap/close rules and reversible 0097 migration verified |
| Console UI | 42 targeted tests passed; final shared workspace recheck passed 15 tests |
| Shared Columns UI | 21 passed, including defaults when switching statutory tables |
| Static/contracts | Scoped Ruff/mypy, Console application/relevant test types, API client types, OpenAPI/client freshness and consumer lock checks passed |
| Browser | Live applicability/card/direct navigation and populated native-evidence fixture passed; sections/search/kebab/drawer/downloads/review/history checked in Light/Dark/Ledger at 1440/390 widths |
| Visual artifacts | All three final PDF pages inspected; workbook statutory/control sheets and complete CSV verified |
| Runtime | Identity 0097, Accounting 0229, Reports 0041 applied; APIs and all six report workers restarted and readiness verified |

Regression and focused test counts overlap; they are separate verification runs.
Security/simplification review checked tenant/company scope, actor-owned jobs,
denied fields, idempotent atomic rollback, immutable evidence, bounded native
sources, private artifacts and explicit capture/review authority. Shared GST UI,
artifact framework and centralized styles are reused; statutory filing locks
remain separate.

Evidence is retained in ignored `.test_artifacts/tax-reports-review/GSTR1/`:
`reports-final-mysql.log`, `reports-acceptance-final.log`,
`accounting-final-mysql-fixed.log`, `identity-final-mysql.log`, `live-review.json`,
`fixture-review.json`, theme/mobile screenshots and `native/` artifacts. Runtime
restart recovered an inaccessible launcher identity through the verified
workspace's graceful shutdown marker, without signaling an unverified PID.

The real QA company currently has no eligible GST registration. Live review
confirmed its hidden card and direct-route setup explanation. Positive browser
review uses explicit fixture interception over the authenticated live shell and
disposable native backend evidence. No synthetic live registration, posting or
filing acknowledgement was saved.

HSN format/UQC/turnover requirements are checked, but no current GSTN HSN catalogue
or portal acceptance service is claimed. GSTR-1A remains a separate correction
workflow. Official upload utility/schema and a portal round trip remain
unverified, so portal JSON is unavailable. PDF/Excel/CSV are review working papers
and do not establish government filing or acceptance.

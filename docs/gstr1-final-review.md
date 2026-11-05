# GSTR-1 final review — 2026-11-02

The subsequent [joint end-to-end review](gst-returns-e2e-review.md) supersedes
the calculation revision below with revision 3 and records the latest checks.

This review follows the [nine-phase delivery](gstr1-delivery.md) and covers
calculations, immutable source capture, permissions, saved preparations, UI,
and actual downloaded working papers. The government form rule remains
`GSTR1_2025_10`; the local calculation revision is now **2**.

## Findings and corrections

- Repeated amendments now use the latest amended values. For an invoice revised
  from 1,000 to 1,100 and then to 1,200, the second return reports a 100
  differential. Referencing the already amended root is blocked. Scoped, bounded
  extraction retains the parent chain and detects earlier forks.
- Amended unregistered large-invoice notes retain Table 9C using the original
  invoice classification. Further credit reductions use the original supply
  financial year for the section 34 cutoff. Linked notes must retain the
  original recipient and statutory supply profile.
- Table 11B and its amendment show positive advance-adjustment disclosures while
  the liability bridge applies the reduction. Service advance amendments do not
  require an invented HSN. Coverage uses the effective document kind.
- IFF evidence is checked for eligible registered invoices/notes, dated QRMP
  applicability, the first two quarter months, filing after the supply month,
  future proof dates, and the monthly 50 lakh taxable-value limit. Owner capture
  rejects unsupported kinds and invalid filing/profile evidence.
- Completeness checks select the highest covered source sequence. Conflicting
  statuses at that sequence require attention; a fresh higher-sequence proof
  supersedes older conflicts. Native tests confirm that all eight proofs
  captured together retain the same committed feed sequence.
- Preparations from older calculation revisions remain readable as archives.
  The API rejects new review/filing approval for those copies; the UI explains
  that a current preparation is required and disables approval. Existing
  identical review replays remain idempotent.
- Structured amendment/source history stays intact in frozen results and is
  encoded as JSON text in export cells. PDF, Excel and CSV support lineage
  without changing source fingerprints or weakening scalar validation for
  other reports. PDF and Excel identify the calculation revision.
- The optional GSTR-3B comparison selector shows its preparation date and a short
  identifier. Statutory sections, columns, search, row menus, source drawers,
  review evidence, and read-only filed history retain the established layout.

## Verification

| Check | Result |
|---|---|
| GSTR-1 native MySQL | 64 passed: rules, calculations, scoped API, legacy approval protection, PDF/XLSX/CSV downloads and repeated-amendment CSV |
| Accounting native MySQL | 22 passed: outward capture, existing GST/credit paths, exact schema/index parity and downgrade/upgrade |
| Existing export regression | 25 passed: framework exports, GSTR-3B exports and tabular rendering |
| Console UI | 43 passed: GSTR-1/GSTR-3B workspaces, GST setup and tax pages/workspaces |
| Shared column UI | 51 passed: 21 column-picker and 30 field-column cases |
| Static checks | Scoped Ruff/strict mypy, Console application/relevant test types and API-client types passed |
| Contracts | Reports/Accounting/Identity OpenAPI and generated clients checked; API-client 0.2.53; consumer lock resolution retained |
| PDF | All three native-rendered pages visually inspected: summary, statutory details, bridge, completeness and verification |
| Browser | Live applicability and calculation revision 2 verified; native-evidence fixture passed sections, search, kebab/drawer, actual downloads, proof hashing, review/filing history and Light/Dark/Ledger at 1440/390 widths; no browser errors |
| Runtime | Accounting/Reports and all six report workers restarted with the final code; Identity 8001, Accounting 8011 and Reports 8013 readiness returned 200; all workers running |

Counts are separate runs and may overlap. Identity's seven native owner tests
from delivery remain applicable; this review changes no Identity models or
migrations. Heads remain Identity 0097, Accounting 0229, Reports 0041.

The manual security review checked tenant/company scoping, actor-owned jobs,
field denies, current approval authority, immutable originals, atomic audit/outbox
publication, idempotent replay, private artifacts and source integrity. Capture
retains the existing company setup lock before validation; the amendment baseline
check runs within the serialized command. No unresolved security finding remains
in these reviewed changes.

The simplification review retained the shared GST workspace and export framework.
Relationship lookup is bounded by depth, rows and bytes; amendment-child detection
uses a precomputed index. Export conversion operates only on bounded GSTR-1
batches after frozen-result integrity verification.

Evidence is in ignored `.test_artifacts/tax-reports-review/GSTR1/`, including
`final-review-reports-mysql.log`, `final-review-accounting-mysql.log`,
`final-runtime-after-export.log`, browser JSON records, theme/mobile screenshots
and `native/` PDF/XLSX/CSV and preparation evidence.

## Product boundaries

The real QA company has no eligible GST registration. Live checks verify
applicability and the direct-route explanation. Populated browser checks use
explicit fixture interception over the authenticated live shell with evidence
and files produced by disposable native MySQL tests. No synthetic live GST
registration or filing acknowledgement is saved.

GSTN portal-upload JSON stays unavailable until the official utility/schema and
portal import are verified. HSN format, UQC and turnover rules are validated;
GSTN catalogue acceptance is not claimed. GSTR-1A is a separate correction
workflow. PDF, Excel and CSV are review working papers, not government acceptance.

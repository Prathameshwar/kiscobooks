# Voucher batches: two-pass review, 2026-10-11

This review covers the recorded scope of **B01–B45**. Pass 1 compared every batch's
scope, prerequisites and status with the live checklist and activation gates. Pass 2
checked the implemented service boundaries, tests and fail-closed release behavior.
For a planned batch, pass 2 is a readiness/gap review, not a claim that an
end-to-end implementation exists. No C0–C4 activation was performed.

The status ledger remains [the delivery tracker](voucher-delivery-tracker.md). Its
45 rows and the [todo](voucher-implementation-todo.md) agree: **14 VERIFIED,
9 IN_PROGRESS, 22 PLANNED**. All listed prerequisites refer to earlier batches;
no VERIFIED batch depends on an incomplete batch. B31 remains conditional and
B42–B44 are selected but incomplete. The native money and invoice switches still
default to disabled.

| Batch | Pass 1: plan/status check | Pass 2: implementation/evidence check |
|---|---|---|
| B01 | Baseline/compatibility is VERIFIED. | Historical baseline is retained; current owner regressions passed. |
| B02 | Foundation contracts are VERIFIED. | Shared scope and owner boundaries remain represented in code and docs. |
| B03 | Signed execution/source contracts are VERIFIED. | Current Vouchers execution tests passed; stock extensions remain separately gated. |
| B04 | Service scaffold is VERIFIED. | Full Vouchers suite passed; no service-layout change. |
| B05 | Common document/type schema is VERIFIED. | Full Vouchers suite passed; no per-kind voucher table added. |
| B06 | Configuration/custom-field foundation is VERIFIED. | Full Vouchers suite passed; later kind-specific effects are not inferred. |
| B07 | Durable operation protocol is VERIFIED. | Full Vouchers suite passed; Accounting legacy protocol has no executable default. |
| B08 | Numbering/artifact foundation is VERIFIED. | Full Vouchers and Console suites passed after the test timing fix. |
| B09 | Reports foundation is VERIFIED. | Full Reports suite passed; later stock/job feeds remain open. |
| B10 | Journal/Contra money slice is VERIFIED. | Full Vouchers and selected Accounting money tests passed. |
| B11 | Bill/advance allocation slice is VERIFIED. | Full Vouchers and selected Accounting money tests passed. |
| B12 | Instrument/history slice is VERIFIED. | Full Vouchers and selected Accounting money tests passed. |
| B13 | Payment/Receipt slice is VERIFIED. | Full Vouchers and selected Accounting money tests passed; tax extensions stay gated. |
| B14 | Financial/money reports are VERIFIED. | Full Reports suite passed; B14a–d remain checked separately in the todo. |
| B15 | IN_PROGRESS; B13 prerequisite satisfied. | Calculator/deal and Catalog fact tests passed; protected publication and Accounting projection are absent. |
| B16 | IN_PROGRESS; B15 prerequisite remains open. | Existing tax/date/credit slices do not cover all advance, withholding or free-supply effects. |
| B17 | IN_PROGRESS; B16 prerequisite remains open. | Account/service posting and untaxed source notes are narrower than tax/component notes and returns. |
| B18 | IN_PROGRESS; B17 prerequisite remains open. | Invoice/tax report grains exist; producer coverage and complete bridge acceptance remain open. |
| B19 | PLANNED; B17/B18 must finish first. | Statutory issuance and service-invoice release have no completion evidence. |
| B20 | PLANNED after B19. | Native stock position/origin contract is not implemented. |
| B21 | PLANNED after B20. | Stock-period/count/hold/expiry/first-use guards are not implemented. |
| B22 | PLANNED after B21. | FIFO/average choice is recorded; native valuation and conservation are not implemented. |
| B23 | PLANNED after B20–B22. | Receipt/delivery/challan/transfer effects are not implemented. |
| B24 | PLANNED after B23/B16. | Goods/mixed invoice and deal-to-stock posting are not implemented. |
| B25 | PLANNED after B24. | Source-capped stock returns, counts and damage effects are not implemented. |
| B26 | PLANNED after B24/B25. | Revaluation/backdate/repair effects are not implemented. |
| B27 | PLANNED after B26. | Stock report producer is absent; B27a–e remain unchecked. |
| B28 | IN_PROGRESS; B15 upstream gate remains open. | Non-posting capture exists; order lifecycle and downstream claims do not. |
| B29 | PLANNED after B28. | Fulfillment schedules and source claims are absent. |
| B30 | PLANNED after B29/B26. | Order-to-movement/bill effect acknowledgements are absent. |
| B31 | Conditional, PLANNED after B30. | No reservation is claimed; release gate excludes B31/AC21 only when unselected. |
| B32 | PLANNED after B09/B30. | Order register producer is absent; missing data cannot be called zero. |
| B33 | PLANNED after B08/B30. | Optional/memorandum conversion effects are absent. |
| B34 | PLANNED after B33/B09. | Scenario-only reversing journal effects are absent. |
| B35 | PLANNED after B34/B27/B32. | Actual-versus-scenario reporting is absent. |
| B36 | PLANNED after B35. | 18-kind core activation and client review have not occurred. |
| B37 | IN_PROGRESS; B30 upstream gate remains open. | Exact BOM requirement preview exists; published process/template readiness does not. |
| B38 | PLANNED after B37/B23/B25. | Both-direction custody/material effects are absent. |
| B39 | PLANNED after B37/B38/B26. | WIP, output/scrap genealogy and actual cost effects are absent. |
| B40 | PLANNED after B38/B39/B18. | Job/custody/WIP report producer and ITC-04 export are absent. |
| B41 | PLANNED after B40/B19. | Processing settlement and statutory handoff are absent. |
| B42 | IN_PROGRESS; B19 gate open. | Razorpay signature/capture preflight tests pass; live adapter/refunds/chargebacks do not exist. |
| B43 | IN_PROGRESS; B19 gate open. | Mapped CSV/match preflight tests pass; durable imports/grouped BRS do not exist. |
| B44 | IN_PROGRESS after B12. | Cheque/cash validation tests pass; native book/leaf and denomination lifecycle does not exist. |
| B45 | PLANNED after core/job and selected optional batches. | Evidence parser is fail-closed; two-year native rehearsal and C4 evidence are absent. |

## Findings and fixes

| Finding | Fix / disposition |
|---|---|
| R1: Phase 3 note still said committing was outside the task after the 2026-10-11 checkpoint was published. | Corrected the note to distinguish source publication from deployment and company migration. |
| R2: The B45 tracker parser accepted a row marked VERIFIED even when its listed prerequisite was incomplete; it also ignored invalid forward dependencies. A first fix incorrectly made conditional B31 mandatory for B32. | Added prerequisite validation and regressions for incomplete, forward and unselected-reservation paths. The current 45-row tracker passes. |
| R3: The dormant B15 stored-promotion reader surfaced a Pydantic exception for malformed persisted policy terms. | Normalized it to the service's controlled validation error and added a malformed-policy regression. This does not activate schemes. |
| R4: One customer-list test timed out in the concurrent full Console run, then passed alone. | Raised only its initial-load wait to five seconds; the full 335-test Console rerun passed. |
| R5: Planned batches have no runnable end-to-end path. | Kept their status and C0–C4 gates unchanged. B45 cannot be claimed from design or preflight evidence. |

## Verification and limits

Vouchers: 157 passed, two skipped before the gate edit; its eight release-gate
tests passed after the edit. Reports: 85 passed, one skipped. Accounting: 110
selected money/invoice tests and 16 banking/manufacturing preflight tests passed;
an exploratory full Accounting run was stopped near 10% without a failure and is
not counted as full-suite verification. Catalog:
47 promotion/BOM/source tests, then 12 promotion-storage tests after the reader fix,
passed. Identity source tests: three passed. Console: 335 passed on full rerun;
TypeScript typecheck passed. Generated API clients matched OpenAPI, with eight
client tests and their TypeScript check passing. A full Catalog run was not completed; whole-Catalog
metadata parity has pre-existing in-progress drift outside the promotion tables.
These results do not replace native acceptance for B15–B45 or activate posting.

## Final verification pass

After publication of the review fixes, the eight B45 release-gate regressions
and twelve Catalog promotion-storage regressions passed again. The disposable
loopback MySQL verifier reached Catalog head 0170, checked all promotion tables'
scoped columns, foreign keys and indexes, ran five native isolation/fact checks,
then downgraded to 0131 and upgraded back to 0170. No further defect was found
in those paths. The remaining status is still 14 VERIFIED, 9 IN_PROGRESS and
22 PLANNED; source publication is not C0–C4 activation.

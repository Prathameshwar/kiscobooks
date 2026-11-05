# Voucher configuration v2 backend execution record

**Date:** 2026-10-11. **Status:** Scoped backend slice implemented and verified; the full
[VC2-01 through VC2-06 plan](voucher-remaining-configuration-plan.md#81-configuration-work-packages-and-exit-evidence)
remains open. UI and company activation are out of this slice.

## Implemented scope

- Added sparse policy schema v2 while retaining the exact v1 policy wire and accepted digest.
  An omitted v2 child default or approval flag now inherits; an explicit restriction remains
  explicit. Nested financial, invoice, order and money controls preserve supplied-field
  identity through storage and resolution.
- Added typed `order` controls for the existing non-posting quotation/order/indent capture:
  purpose allowlist, maximum validity/required-by windows and required delivery/payment terms.
  Company `COMMON` order controls are ignored for unrelated kinds.
- Added typed `money` controls for existing Journal/Contra/Payment/Receipt capture: purpose
  allowlist, tender-mode allowlist and tender count. They narrow the existing Accounting-owned
  money entry contract; they do not create a new tax, FX, bank or posting recipe.
- V2 company money/financial bindings resolve on the supplied posting date; document defaults
  remain on document date. Missing required posting-date context fails closed. Every write,
  action, preview, posting and execution-worker recheck passes the stored posting date.
  V1 bindings retain document-date selection and digests. Irrelevant v2 subpolicies do not
  alter another kind's effective policy or revision list.
- Type-specific bindings validate the target kind/profile before publication, so an order
  or money control cannot be silently bound to an incompatible voucher type.
- Updated OpenAPI and the generated voucher TypeScript client. Storage remains the existing
  versioned JSON policy/revision/binding tables; no SQLAlchemy model or migration changed.

## Verification and two review passes

| Evidence | Result |
|---|---|
| Vouchers local suite and domain coverage | 190 passed, 2 skipped; domain coverage 92% |
| Native MySQL verification | 190 passed, 1 skipped; migrations, model/index parity and downgrade/upgrade passed |
| Ruff / mypy strict | Passed for Vouchers source and tests / 58 source files |
| Generated client and transport tests | Generated contract current; 8 client tests passed |
| Review pass 1: applicability and digest | Found future money-only bindings could affect an unrelated voucher digest; fixed by discarding inapplicable v2 slices and tested against Memorandum and Quotation. |
| Review pass 2: compatibility and security | Confirmed tenant/company-scoped binding query and owner gates; added an API regression proving v1 digest is unchanged when a different posting date is supplied. Fixed explicit v2 `null` default clearing, rejected incompatible type bindings, and made empty/disjoint purpose sets fail validation rather than publishing unusable settings. |

## Remaining gates

This is **not** completion of VC2-01 through VC2-06 or of B15-B45. The v2 work still needs a
full descriptor/applicability registry, publish-impact and historical migration cases, and
date contexts for stock, statutory and bank reconciliation settings. Account/group closure,
approval thresholds with FX, source and bill selection, legal challan identity, fulfillment,
stock/count, Purchase/returns, provisional scenarios, job work/manufacturing and selected
provider/bank controls require their separate owner implementations and acceptance evidence.
No new execution capability or company activation is claimed from adding policy fields.

## Final voucher and Sales configuration review

The final review checked sparse policy storage/reload, Sales-family inheritance, type/class
applicability, capture and Accounting preview enforcement, tenant-scoped account references,
document/posting-date selection and the legacy digest boundary. It found that schema-v2
invoice controls could be attached to a `SALES/PRO_FORMA` type even though invoice capture
and the Accounting owner only accept `STANDARD`. Type validation now rejects that policy;
the regression covers API creation and sparse Sales credit-rule inheritance. Existing schema-v1
Pro Forma policy reads are left intact for historical compatibility. This does not enable
Pro Forma invoice execution or change statutory Sales issue numbering.

## Manufacturing/job-work policy checkpoint

Schema v2 now accepts bounded `manufacturing` settings only for manufacturing
Stock Journals and `job_process` settings only for job-work vouchers. Sparse
company/type/class resolution narrows output roles, limits, permissions and job
direction; COMMON policies do not alter unrelated kinds. A job-work type must
pin its principal/worker role. Combined consumption is rejected at policy
validation because the atomic Accounting owner is not yet implemented. This
checkpoint represents configuration only, with no BOM publication or stock,
WIP, tax or GL execution authority. See the
[focused plan](voucher-manufacturing-job-work-plan.md) and Phase 6 tracker.

## Decision log

- 2026-10-11 final review: Closed zero-day order-limit inheritance, blank
  supplier-reference acceptance and policy publication paths that allowed
  order/money purposes incompatible with their kind/profile. Publication also
  rejects required parties with a zero party limit and required invoice/order
  references forbidden by the same policy. The final Vouchers suite passed
  212 tests with 2 skips; Ruff, strict mypy and OpenAPI check passed. These
  are validation corrections; they do not add posting recipes or change
  batch/activation status.
- 2026-10-11: Added the optional `sales_workflow` child to sparse policy v2.
  Standard Sales alone uses the due-date bound and required customer order
  reference; unrelated kinds discard common settings. V1 wire/hash behavior
  and money-owner effects remain unchanged. See the
  [QuickBooks-informed coverage review](voucher-quickbooks-coverage-plan.md).
- 2026-10-11: Delivered the safe sparse-policy and existing-capture subset first. Kept the
  new controls in the shared `COMMON` binding family and preserved v1 wire/digest semantics.
  Deferred controls without an implemented Accounting, Catalog, tax or bank owner recipe.
- 2026-10-11: Final review closed the schema-v2 Pro Forma invoice-policy applicability gap.
  Kept the v1 read/hash contract intact and left the full VC2 and Sales release gates open.
- 2026-10-11: Added a bounded manufacturing/job-work policy representation in
  existing revision/binding storage. Kept combined consumption and all physical
  effects closed pending the Catalog and Accounting owner gates.

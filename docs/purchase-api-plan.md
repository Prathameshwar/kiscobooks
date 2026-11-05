# Purchase API integration plan

Prepared: 2026-10-31. Status: all API phases authorized for implementation.
The user authorized uninterrupted execution of A0–A9, including tests, review,
fixes and the maintained checklist. Intermediate phase confirmations are superseded.
Print/PDF and production activation remain separate workstreams.

## Outcome and boundaries

Connect the approved Purchase workspace to real company-scoped configuration,
masters, durable vouchers, authoritative calculations, approvals, stock and
financial effects, settlements and secure supporting files. Preserve the desktop,
compact, keyboard, focus, error and recovery experience already reviewed.

Reuse the existing Console proxy, service-command primitives, Vouchers aggregate
and lifecycle, Catalog masters, Accounting execution/calculator and Reports.
The UI draft is presentation state, not a service payload. Do not introduce a
second Purchase calculator, parallel workflow engine or new service.

This plan does not certify current backend readiness or advance any B01–B45 or
C0–C4 status. The [voucher tracker](voucher-delivery-tracker.md) remains authoritative.
Implement missing owner contracts under its prerequisite gates, with matching
models/migrations, OpenAPI and generated clients where applicable. Existing
concurrent stock/unit/opening work must be preserved.

## Findings from the current source

| Area | Existing evidence | Integration implication |
|---|---|---|
| Approved UI | [Readiness report](purchase-ui-readiness.md), PurchaseWorkspace and PurchaseWorkflowWorkspace | Broad UI is synthetic; replace the fixture adapter through an explicit mapping. |
| Live Purchase | [purchase-entry.ts](../mfes/apps/console/app/lib/purchase-entry.ts) | Current builder supports STANDARD account purchases and UNTAXED_ACCOUNT. It does not establish readiness of every preview feature. |
| Configuration | [Vouchers routes](../apis/vouchers/src/vouchers/api/routes.py) | Type/class, effective configuration, field-set and capabilities already have source contracts. Readiness/permissions must still be checked against running services. |
| Save and read | VoucherInput, VoucherEdit and VoucherDetail in [OpenAPI](../apis/vouchers/openapi.json) | Create/edit and saved revisions exist. Track row_version, revision_id and revision_number separately. |
| Calculation | [invoices.py](../apis/vouchers/src/vouchers/api/invoices.py) | Preview requires a persisted voucher and expected_version. Acceptance writes a new revision. UX and concurrency must follow that sequence. |
| Corrections | [documents.py](../apis/vouchers/src/vouchers/tasks/documents.py) | Editing an eligible unposted voucher preserves its ID and creates a DRAFT revision. The demo's new-ID correction is not the wire contract. Posted changes require supported reversal/correction. |
| Execution | [posting.py](../apis/vouchers/src/vouchers/api/posting.py) | Post/reverse return asynchronous operation evidence. A 202 response is not proof of completed financial effects. Activation is independently gated. |
| Attachments | AttachmentInput contains object_key, content_hash, media_type and size_bytes | Metadata does not prove secure byte upload/download exists. Establish the storage/transport owner and lifecycle before enabling uploads. |
| Artifacts | [artifacts.py](../apis/vouchers/src/vouchers/api/artifacts.py) | Generated document artifacts are a separate contract; do not use them as an assumed supplier-file upload API. Print remains excluded. |
| Transport | [product-fields route](../mfes/apps/console/app/api/product-fields/route.ts), [voucher allowlist](../mfes/apps/console/app/lib/voucher-request-policy.ts) | Keep authenticated, CSRF-protected calls through the existing proxy. Add only exact reviewed methods/paths when missing. |

These findings are source inspection, not authenticated runtime verification.
Global capability flags, published schemas and successful draft capture alone do
not prove a particular goods/tax/settlement profile can execute correctly.

## Phase sequence and completion gates

### A0 — Contract audit, supported profiles and decisions

Deliver:

- A field-by-field map of header, supplier, registrations, dates, lines, discounts,
  charges, tax, receipts, tracking, settlement, attachments and custom fields.
  Mark each as existing and verified, needing extension, unsupported or undecided.
- Runtime endpoint/capability/permission checks in an isolated test company;
  distinguish draft, calculation, approval and execution support for every profile.
- A service-owner and dependency ledger for schema, policy, duplicate checks,
  source balances, tax, stock and file transport gaps. Reconcile with B15–B18,
  relevant stock batches and the authoritative tracker rather than treating them
  as completed prerequisites.
- An agreed release matrix covering Items, Accounts and Mixed; direct/reference/
  deferred receipts; supported tax profiles; quantity-difference purposes; advance
  and tender types. Record intentionally unsupported profiles and their UI behavior.
- Decisions on duplicate identity/normalization/scope and authorized exceptions,
  supplier mismatch tolerances, credit-term date basis and attachment storage.
  Reuse already-ratified owner rules; escalate only genuinely unresolved choices.

Exit: every visible UI feature has a documented contract and owner or an explicit
gap. No critical path relies on a demo field, guessed endpoint or silent business
decision. The agreed matrix becomes the acceptance baseline for A1–A9.

### A1 — Live context, configuration, permissions and masters

Deliver:

- Resolve company/year, capability, Purchase type/class, effective configuration
  and native/custom field access automatically; retain policy/version evidence.
- Live supplier, payable, expense account, item, unit, registration and eligible
  location/source lookup adapters using the proper owners and server filters.
- Verify company, kind/role, active/effective dates, source versions and ownership
  at selection; revalidate at write. Labels are display facts, not identity.
- Preserve selections and line input during refresh. Add loading, empty, unavailable,
  denied and retry behavior. Cancel/discard late responses after context changes.
- Respect field-level read and write denies; never fetch a forbidden cost merely
  to hide it afterward. Disabled actions explain actual capability limitations.

Exit: real company data populates the approved workspace; wrong-company, stale,
inactive and unauthorized choices are refused. Context changes cannot leak data.

### A2 — Durable drafts and the first complete save/reopen slice

Deliver:

- A typed adapter from UI state to VoucherInput/VoucherEdit and from VoucherDetail
  to the workspace; start with the existing untaxed account-bill contract.
- Real create, edit, draft list/resume and pinned-revision reads, including custom
  fields and historical labels. Reopening after reload/browser restart restores
  the server record. Unsaved edits remain explicitly unsaved.
- Preserve stable line UUIDs; keep row_version distinct from revision ID/number.
  Send expected_version for edits, and verify returned company/type/record/version.
- Use an immutable command body and idempotency key for exact uncertain retries.
  Reject double submits; never turn an uncertain create into a second voucher.
  Establish the recovery contract for interrupted/reloaded commands in this phase.
- Handle field errors, permission refusal, deleted/changed masters and stale writes
  without discarding edits. No automatic overwrite/merge of financial changes.

Exit: a real account bill can be saved, edited and reopened with identical canonical
facts. Two editors and lost-response/retry cases do not create duplicates or lose
input. Unsupported profiles remain explicitly unavailable until their phases pass.

### A3 — Authoritative calculation, tax and supplier comparison

Deliver:

- Map supported discounts, charges, rounding and tax inputs to the native invoice
  recipe; Accounting remains the calculation authority. Preserve decimal strings.
- Implement the current sequence: save current draft → request invoice-preview for
  its version → show owner breakdown/differences → accept calculation hash → use
  the returned new revision/version. Keep saving distinct from final acceptance.
- Prevent stale preview responses and invalidate accepted evidence after relevant
  input/configuration changes. Refuse submission with absent/stale acceptance.
- Resolve supported dated company/party registrations, classifications, supply
  locations and statutory dates separately from posting dates. Unsupported tax
  cases must not silently become untaxed bills.
- Implement supplier-declared totals, signed differences and authorized resolutions;
  retain original evidence. Add authoritative duplicate enforcement at the owner's
  relevant write/accept/post boundaries, not merely an advisory client lookup.
- Preserve supplier payable versus recipient liability and any separately supported
  credit-eligibility evidence. Do not infer recognition from the preview.

Exit: owner results, accepted hash, exact revision and supplier evidence agree.
Changed input, concurrent duplicate attempts, mismatches, tax denial and unavailable
calculation-owner cases all fail safely with actionable UI recovery.

### A4 — Goods, Mixed mode, receipts and tracking

Deliver:

- Connect item/unit/version facts, expense and purchase accounts, invoice supplies,
  item-line links and stock capture without parallel or duplicated line identities.
- Capture receipt versus billed quantity, exact unit conversion, paid-bundle/free
  purpose distinctions and the supported valuation evidence; refuse missing policy.
- Implement direct receipt, existing-receipt allocation and deferred receipt only
  where their owner contracts are supported. A linked bill must not receive goods
  already received. Concurrent claims must revalidate eligible source balances.
- Integrate applicable warehouse/bin/lot/expiry/serial controls and server checks
  for required tracking, duplicate serials, unit eligibility and exhausted sources.
- Re-run A3 calculations and acceptance for goods/Mixed, charges and quantities.

Exit: supported goods and Mixed bills round-trip correctly; partial receipt balances
remain consistent. Drafting and calculation alone create no stock movement, and
one later execution cannot double-receive the same source goods.

### A5 — Real lifecycle, approvals, corrections and concurrency

Deliver:

- Use the service's draft/submit/approve/reject/cancel transitions and effective
  permission/separation-of-duties rules; preserve server reasons and history.
- Map unposted rejection edits to real immutable revisions rather than copying the
  demo's new-ID behavior. Approved/submitted edits follow documented invalidation
  and reapproval rules. Historical revisions stay readable under current read policy.
- Separate posted reversal/replacement from ordinary editing; retain lineage and
  respect closed periods. Unsupported posted correction stays blocked.
- Cover concurrent approval/edit, stale calculation, policy changes, revoked rights,
  and pending/uncertain commands across context changes and reconnects.

Exit: lifecycle and action availability match server evidence for each role.
Unauthorized/self approval where forbidden, stale transitions and changes to
posted content are refused; original revisions and audit lineage remain intact.

### A6 — Credit terms, advances and payment instructions

Deliver:

- Integrate live eligible open items, current balances and source versions; define
  supported allocation and cash/bank tender mappings under owner policy.
- Save due dates/terms and advance/payment intent, with separate proposed, recognized
  and cleared states. Preserve the full bill amount independently of settlement.
- Enforce residual limits, supplier/company/currency eligibility, partial settlement
  and concurrent double-application refusal at the owner, not only in the browser.
- Show refreshed balances and recoverable conflicts after a source changes. Gate
  unsupported tender/provider/FX cases; external banking-provider work is not implied.

Exit: the PU09 advance/payment case uses real source facts and cannot over-allocate
or misrepresent an instruction as money paid. Actual effects are verified in A8.

### A7 — Secure supporting-file transport

Prerequisite: A0 confirms an existing platform transport/storage contract or records
the needed approved owner work. The [Design open questions](invoice-design.md#9-open-questions)
already distinguish metadata from byte storage; do not silently choose a provider.

Resolved 2026-10-31: the user selected private local disk on the deployment VM for
Purchase. [Storage contract](purchase-supporting-files.md); Design storage stays separate.

Deliver:

- Authorized upload initiation/transfer/completion, server-issued object identity,
  verified content hash/type/size, validation/scan status and voucher/revision binding
  according to the agreed storage contract.
- Retriable failures, progress, cancel/removal and reload-safe metadata; do not mark
  a local file as uploaded or accept a caller's arbitrary object key as ownership.
- Private, authorized download/preview with the platform's signed/expiring access
  contract, safe response headers, deletion/retention and orphan cleanup policy.

Exit: supporting bytes survive reload and have verified ownership; cross-company
access, unsafe content, incomplete transfer and removed permissions are refused.
Required evidence blocks progression until validation completes. Print is untouched.

### A8 — Actual execution and cross-service reconciliation

Deliver:

- Integrate capability-gated post/reverse and asynchronous operation read/recovery.
  Show pending, failed and committed outcomes from evidence. Do not mark a bill
  posted because its command returned 202 or a timeout elapsed.
- Execute the agreed scenarios in an authorized isolated test company: real invoice,
  receipt/valuation, payable, supported supplier/recipient tax and settlements.
- Reconcile Accounting facts to party/open-item/stock ledgers and relevant reports;
  verify references, amount/quantity identities, dates and reversals per contract.
- Exercise duplicate clicks, lost responses, message replay, worker interruption,
  prior-company late results, closed periods, stale sources and partial failures.
  Audit and outbox effects must remain atomic at their owner boundaries.
- Respect activation and batch prerequisites. Green test execution is not authority
  to switch production flags or promote C0–C4 readiness.

Exit: one intended command produces one intended set of consistent effects;
replay produces no duplicate posting, receipt, liability or settlement. Failures
recover or remain explicitly blocked without corrupting balances or audit history.

### A9 — Connected UI acceptance and release handoff

Deliver:

- Repeat PU01–PU09 against real contracts for every agreed supported profile, plus
  all permission, validation, stale/uncertain and historical-revision cases.
- Re-run the approved responsive/themes/zoom/keyboard/large-document experience
  with actual lookup latency, validation and server response sizes. Complete the
  supported hardware/human assistive-technology acceptance or record its release gate.
- Verify typed contracts, owner tests, authenticated browser E2E, full typechecks,
  production build, proxy allowlists and schema/generated-client consistency.
- Produce deployment prerequisites, capability matrix, operational recovery,
  observation/rollback steps and a concrete production-route cutover for approval.
  Retain the synthetic preview for regression. No silent production activation.

Exit: every agreed API feature has verified evidence or an explicitly approved
scope change; no stub is labelled complete. The approved UI is ready for the
authorized production rollout. Print/PDF remains separately planned.

## Cross-phase rules and acceptance matrix

Every phase closes with affected unit/contract/integration tests, relevant browser
checks, simplification and CLAUDE.md sections 5/6 review, fixes and an updated
[API checklist](purchase-api-todo.md). Financial failures need regression tests
before fixes. Required migrations/models, OpenAPI, clients and docs land together.
Use authenticated, scoped test data; never rely solely on mocked UI success.

| Case | Required verified outcome | Main phases |
|---|---|---|
| PU01 | Untaxed account bill saves/reopens and executes exact payable facts | A2, A3, A5, A8 |
| PU02 | Goods, discount, freight, supported tax and advance reconcile | A3, A4, A6, A8 |
| PU03 | Goods/service Mixed facts survive round-trip and execute once | A4, A8 |
| PU04 | Partial receipt allocation leaves correct residual; no second receipt | A4, A8 |
| PU05 | 11 received/10 billed uses an explicit supported purpose and valuation | A4, A8 |
| PU06 | Declared/calculated mismatch requires an authorized retained resolution | A3, A8 |
| PU07 | Supplier duplicate identity is enforced under concurrency | A0, A3, A8 |
| PU08 | Supported recipient tax stays distinct from supplier payable/recognition | A3, A8 |
| PU09 | Eligible advance/proposed payment cannot exceed available/residual amounts | A6, A8 |

Dates, profiles and numerical example values come from versioned test fixtures and
owner policy; synthetic UI tax values are not imported as authoritative results.
No delivery-date estimates are assigned before A0 establishes backend gaps and
external decisions. Account-Purchase implementation and review are now recorded in
[the live todo](purchase-api-todo.md) and [evidence](purchase-api-progress.md).
Broader owner profiles and authenticated reconciliation remain pending; these
records govern current phase status.

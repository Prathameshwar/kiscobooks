# Company voucher type defaults

2026-10-31. User authorized provisioning all applicable company voucher types with
appropriate names, stable codes and common native rules, followed by review and fixes.
Purchase printing remains a separate pending delivery. Preserve parallel entry UI work.

## Phases and todo

1. Catalogue and rules
   - [x] Trace company creation, Identity enrollment, Vouchers source discovery and rules.
   - [x] Confirm company scope and that no automatic voucher types currently exist.
   - [x] Define and validate every applicable kind/profile and invoice entry variant.
2. Provisioning
   - [x] Provision through authenticated Identity discovery for every client.
   - [x] Add a permission-checked, retryable company setup step after feature selection.
   - [x] Preserve existing types, custom policies, retired types and immutable revisions.
   - [x] Commit definitions, native section rules and audit evidence atomically.
3. Verification and review
   - [x] Reproduce current missing-default and section-rule defects before fixing.
   - [x] Test no-inventory, inventory, BOM and approval combinations.
   - [x] Test signed source authority, stale versions, company/tenant scope and retries.
   - [x] Test onboarding recovery without creating a second company.
   - [x] Run native database, focused UI, generated contract and static checks.
   - [x] Review CLAUDE.md sections 5/6 and simplify; fix findings and record evidence.
   - [x] Finish the isolated SQLite recheck after an overloaded broad run: all 3 passed.

## Decisions

- Vouchers owns company-scoped definitions; Identity owns company facts and enrollment.
  Use the existing signed owner/discovery mechanism, with no cross-service database
  access or network call in the provisioning transaction.
- Sales and Purchase receive separate Account, Product and Mixed types. Product means
  catalog goods/services; non-stock products do not require inventory. Physical stock
  types require inventory; manufacturing additionally requires BOM definitions.
- Cover all 22 native kinds when applicable, plus common explicit profiles such as
  advances, quotation, pro forma, requisitions, challan and physical transfer stages.
  Material In/Out have separate principal and worker definitions to freeze ownership.
- Rules use typed native policy, fixed entry modes, party roles and purposes. Approval
  follows the company's approval-workflow feature. Keep existing native date/cardinality
  bounds; do not invent tax rates, account mappings, legal numbers or financial caps.
- Provisioning never enables a feature, financial/stock execution, an external provider,
  statutory automation, automatic consumption or a custom field. Readiness remains per
  consumer; definitions do not imply every entry UI or owner recipe is implemented.
- Stable codes are additive. Existing authored rows/revisions are preserved. Incompatible or
  retired code collisions require review rather than replacement or reactivation.
  Feature enablement can add newly applicable definitions; disabling preserves history
  and the normal feature gates continue to restrict new physical operations.
- The discovery worker is additive only. Explicit setup can create a new immutable
  revision for an untouched system type when approval/currency features changed during
  onboarding. This requires a system-created type and revision, the exact starter name
  and a verified starter-policy hash. An authored revision is never reconciled. A late
  worker snapshot cannot undo the setup revision. Pending execution blocks reconciliation.
- Explicit setup conflicts return 409 and roll back the whole bootstrap transaction,
  including its audit/outbox writes. They do not store a successful idempotency receipt,
  so the same key can retry after resolution. Worker provisioning preserves conflicting
  definitions and may create other missing defaults independently.
  Type identity (code/kind/profile) is immutable; review never means silently renaming
  or recategorizing a conflicting row. A real reserved-code collision may require a
  separate maintenance decision. Fresh companies have no such user-authored collisions.

## Catalogue v4

The baseline has **20 types**, inventory adds **18** (38 total), and BOM definitions
with inventory add **1** (39 total). Approval and currency flags change rules, not counts.
Across applicable configurations the catalogue covers all 22 registered native kinds.

| Code | Name | Kind / profile |
|---|---|---|
| `CTR` | Contra | CONTRA / STANDARD |
| `JRN` | Journal | JOURNAL / STANDARD |
| `PAY` | Payment | PAYMENT / STANDARD |
| `REC` | Receipt | RECEIPT / STANDARD |
| `PAY_ADV` | Supplier Advance | PAYMENT / ADVANCE |
| `REC_ADV` | Customer Advance | RECEIPT / ADVANCE |
| `PUR_ACC` | Purchase - Account Bill | PURCHASE / STANDARD |
| `PUR_PRD` | Purchase - Product Bill | PURCHASE / STANDARD |
| `PUR_MIX` | Purchase - Mixed Bill | PURCHASE / STANDARD |
| `SAL_ACC` | Sales - Account Invoice | SALES / STANDARD |
| `SAL_PRD` | Sales - Product Invoice | SALES / STANDARD |
| `SAL_MIX` | Sales - Mixed Invoice | SALES / STANDARD |
| `CRN` | Credit Note | CREDIT_NOTE / STANDARD |
| `DBN` | Debit Note | DEBIT_NOTE / STANDARD |
| `PROFORMA` | Pro Forma Invoice | SALES / PRO_FORMA |
| `SO` | Sales Order | SALES_ORDER / STANDARD |
| `QUOTE` | Quotation | SALES_ORDER / QUOTATION |
| `PO` | Purchase Order | PURCHASE_ORDER / STANDARD |
| `MEMO` | Memorandum | MEMORANDUM / STANDARD |
| `RVJ` | Reversing Journal | REVERSING_JOURNAL / STANDARD |

Inventory-only additions:

| Code | Name | Native behavior |
|---|---|---|
| `GRN` | Goods Receipt Note | Physical receipt |
| `DN` | Delivery Note | Physical dispatch |
| `RIN` | Rejections In | Customer return |
| `ROUT` | Rejections Out | Supplier return |
| `STK_OPEN` | Opening Stock | Opening quantities and values |
| `STK_TRF` | Stock Transfer | Direct transfer |
| `STK_SEND` | Stock Transfer Dispatch | Dispatch into transit |
| `STK_RECV` | Stock Transfer Receipt | Receive from transit |
| `STK_COUNT` | Physical Stock Count | Count and reconciliation |
| `DC` | Delivery Challan | DELIVERY_NOTE / DELIVERY_CHALLAN |
| `REQ_PUR` | Purchase Requisition | STOCK_JOURNAL / REQUISITION, PROCURE |
| `REQ_MAT` | Material Requisition | STOCK_JOURNAL / REQUISITION, INTERNAL_ISSUE |
| `MAT_IN_P` | Job Work Return In | MATERIAL_IN, principal owns material |
| `MAT_OUT_P` | Job Work Material Out | MATERIAL_OUT, principal owns material |
| `MAT_IN_W` | Customer Material In | MATERIAL_IN, worker holds customer material |
| `MAT_OUT_W` | Customer Material Return Out | MATERIAL_OUT, worker returns customer material |
| `JWI` | Job Work In Order | JOB_WORK_IN_ORDER, worker role |
| `JWO` | Job Work Out Order | JOB_WORK_OUT_ORDER, principal role |

With inventory and BOM, `MFG` / **Manufacturing Journal** uses STOCK_JOURNAL /
MANUFACTURING. The generic STANDARD stock journal has no concrete native stock action;
it is not provisioned as an ambiguous duplicate of transfer/manufacturing/requisition.

## Common rule values

- All definitions use schema v2, immutable revision 1 and ACTIVE status initially.
  Approval follows `approval_workflow`; self-approval is disabled. Without
  `approval_workflow` a submit approves in the same step, so a company with one user can
  post. Native defaults retain
  200 lines, 20 parties, 3,650 backdate days and 365 future days unless narrowed below.
- Account invoices use ACCOUNTS mode and ACCOUNT and SERVICE supplies: GST is recorded on
  service supplies (the tax profiles are service profiles), so without SERVICE the default
  Purchase bill (v3) and Sales invoice (v4) could not carry GST. Product
  invoices use ITEMS mode and GOODS/SERVICE supplies; mixed invoices use MIXED mode and
  all three supply kinds. Mixed permits both kinds without forcing an artificial minimum of each.
  Sales/Purchase allow one customer/supplier respectively and require party/account
  sections. Product requires items; Account forbids items. Purchase requires a supplier
  invoice reference. Line descriptions are optional (v4).
- Invoices and notes allow manual discounts and charges (v4); the native limits (100% and
  200 components) and Accounting's calculation still bound them. Freebies, deals,
  unapproved supplier differences, account mappings, rate overrides and custom bindings stay
  off; configure those company-specific exceptions explicitly in Voucher types/rules.
- Money types use ACCOUNTS only. Contra permits TRANSFER; Journal permits GENERAL and
  BILL_ADJUSTMENT; Payment/Receipt permit GENERAL, SETTLEMENT and REFUND and allow
  settlement adjustments (v4). Advances permit ADVANCE only, with supplier/customer roles respectively.
  Journal requires native financial details on submission, rather than a static account
  section: GENERAL requires balanced account lines, while BILL_ADJUSTMENT uses allocations.
  Foreign money entries are allowed only with `multi_currency`; normal company currency
  allowlists still apply.
- Credit/Debit Notes use customer/supplier roles. Native note validation
  requires the original invoice; an additional external reference is not mandatory.
  Orders/quotation use ITEMS,
  one appropriate party, required items/party, and a fixed PURCHASE/SALE/QUOTE purpose.
- Physical stock types require items, retain the native stock policy and
  cannot receive zero quantities. Challans/requisitions remain their own profiles.
  Job work freezes principal/worker roles, requires material-order references and keeps
  consumption SEPARATE. Manufacturing requires BOM and keeps manual variance/partial
  runs disabled. From v4 no starter type requires narration; `default_narration` may still
  be configured.
- No print template, tax rates, ledger defaults or authority grants are invented. A non-invoice
  type (invoices are numbered on posting) whose policy names no series and no allowed list
  issues from its own automatic,
  financial-year series (`D-<type code>`, numbers `<type code>/<year>/000001`), created on
  first issue and audited; a configured default or allowed list always wins, and a retired
  automatic series is named in the refusal rather than reused. Creation of definitions does not activate posting, stock, tax or printing.

## Delivery and activation

The Console wizard calls the Vouchers bootstrap after selected features are enabled,
before opening the company. Retry retains the same company and idempotency key.
Existing company administrators can use **Company settings > Voucher types > Prepare
default voucher types**. This action reads current signed company capabilities; the browser
does not supply feature authority. Onboarding can still send expected features to detect
feature-selection races. Lost responses retry the same command and key.
Other company-creation clients use existing Identity enrollment and the Vouchers source
worker, whose discovery runs approximately every 30 seconds. Deploy the matching Identity
company snapshot, Vouchers service/worker and Console together for this behavior.
This feature adds no table or migration. It does not alter the parallel Purchase entry UI;
having Product/Mixed definitions does not imply those entry flows are complete.

## Review findings and evidence

- Reproduced and fixed the missing-default endpoint and native section writer defect:
  supported ACCOUNTS sections were incorrectly persisted as FORBIDDEN because the old
  writer intersected them with foundation-only sections. Shared user/system revision
  creation now uses the registered kind's actual sections. Old revisions remain intact.
- Reconciliation handles discovery-before-feature-selection and late-source races.
- Conflict rollback keeps setup retries usable and avoids partial explicit bootstrap.
- Security/correctness review follows CLAUDE.md sections 5/6: signed owner/company
  authority, tenant-session filtering, company predicates/fence, strict input, bounded
  catalogue queries, permission checks and audit/outbox atomicity. No financial write,
  external effect or cross-service network call occurs inside the provisioning transaction.
- Automated `/simplify` and `/security-review` commands are unavailable in this session;
  equivalent manual reviews are recorded here. Final check results are recorded below.

### Checks

- Fail-first evidence: `.tools/company-voucher-defaults-red.log` reproduced the missing
  endpoint and incorrect native ACCOUNTS requirement. The first green run passed both.
- Native MySQL: `.tools/company-voucher-defaults-mysql-final.log`, **21 passed** including
  concurrent bootstrap and saved Purchase Account capture; the harness also reports
  **PASS** for migrations, model/index parity and complete downgrade/upgrade. It used
  only its own disposable loopback schema, which it removed afterwards.
- Identity signed sources: `.tools/company-voucher-defaults-identity.log`, **3 passed**;
  export scope, signature and feature-version changes verified.
- Company UI/proxy/bootstrap: `.tools/company-voucher-defaults-console-final.log`,
  **152 passed**. The additional four negative proxy-policy cases were then checked
  with the complete **93-case** policy suite; all passed (156 unique UI cases overall).
- Console `tsc --noEmit`, Vouchers strict mypy (8 affected modules, then the final 3
  changed modules), Identity strict mypy, affected Ruff checks and generated Vouchers
  contract freshness all passed. API client is version **0.2.46**; consumer lockfile
  regeneration/offline frozen install succeeded (its directory reference needed no
  textual lockfile change).
- The broad SQLite run passed 57 cases and skipped the MySQL-only concurrent test.
  Two obsolete test assumptions (identity renaming and cross-company 404) were corrected
  and passed on MySQL. One existing foundation flow returned a temporary request-busy
  conflict under load; the isolated final recheck is recorded separately below.
- `.tools/company-voucher-defaults-sqlite-recheck.log`: **3 passed in 28.71s**, clearing
  all three cases from that broad run. The existing foundation approval/issue/replay flow
  passed without application changes. No unresolved implementation finding remains from
  the security/correctness/simplification review; runtime activation remains separate.
- Runtime inspection: the currently running local Vouchers OpenAPI still lacks the new
  bootstrap route. This is tested source delivery, with local activation still pending
  a coordinated service/worker restart. Purchase printing has its own deployment checklist;
  its pending live migration/runtime must be considered before restarting that service.

## Usability and provisioning follow-up

User authorized a further review and fixes after reviewing the other voucher types.

1. [x] Exercise the default rules with native Money, Invoice, Order and Stock payloads;
   check every default's field-set and current entry-screen support.
2. [x] Fix conflicting requirements and provisioning/recovery issues, preserving authored
   policies and immutable historical revisions; keep parallel Purchase UI files intact.
3. [x] Run focused native database and UI tests, review security/correctness, and record
   the remaining runtime/entry limitations precisely.

Review reproduced and fixed four entry defects: Journal bill adjustment's contradictory
account requirement, redundant generic references on notes, Material Requisition's
incorrect PROCURE initial purpose, and Pro Forma appearing in the standard Sales picker.
The requisition purpose control now offers only the type's permitted native purposes.

Catalogue v2 changes the Journal and note recipes. Explicit preparation recognizes the
exact v1/v2 system recipes and creates new immutable revisions only for untouched system
types. Authored policies and historical revisions remain unchanged. The discovery worker
remains additive, preserving the explicit setup result when an older snapshot arrives.

### Entry support reviewed

| Defaults | Current usable capture path / remaining work |
|---|---|
| Standard Sales variants | Connected native invoice entry supports Account, Product and Mixed; statutory issue gates still apply. |
| Purchase variants | Account entry is connected. Product/Mixed definitions are provisioned; the user's parallel Purchase entry work must complete those paths. |
| Contra, Journal, Payment, Receipt and advances | Generic entry has native money capture, including bill allocations and configured purposes. |
| Nine physical stock types | Native stock capture, with opening/count workflows; owner execution remains separately gated. |
| Sales/Purchase Orders, Quotation and requisitions | Item capture and native fulfillment terms; purposes follow the selected type. |
| Credit/Debit Notes | Native invoice API is available; a complete dedicated note invoice editor is still required. |
| Pro Forma, Challan, Memorandum and Reversing Journal | Foundation capture/configuration exists; specialised legal output and effect workflows are not implied. |
| Job work and Manufacturing | Typed rules are provisioned. Dedicated native capture/effect workflows remain pending. |

Provisioning all applicable definitions is complete independently of these entry/effect
gaps. This review does not mark every provisioned type as a completed end-to-end workflow.

### Follow-up checks

- Fail-first backend run reproduced all five original cases (including existing-company
  preparation); the first corrected run passed all five. Extended API coverage passed
  seven cases, including all 39 field-sets and immutable v1 upgrades.
- UI regression checks: **197 passed** across seven affected suites, including
  permission handling, wrong-company response rejection, same-key retry and list refresh.
- The final static check caught an unsupported button variant and two mock-helper call
  signatures. Corrected these and reran the affected UI suites: **28 passed**. The final
  Console `tsc --noEmit` passed.
- Affected Ruff checks, strict mypy (five modules), Vouchers generated-contract freshness
  and consumer lockfile regeneration/offline frozen install passed. API client **0.2.47**
  includes the optional expected-features contract.
- Native MySQL regression suite: **44 passed in 568.43s**, covering provisioning,
  actual Journal bill-adjustment save/submit, all 39 field-sets, immutable v1 upgrades
  and existing money/order/stock capture. The complete harness also passed migrations,
  model/index parity and full downgrade/upgrade, then removed its own disposable schema.
  Evidence: `.tools/voucher-defaults-usability-native.log` (exit 0).
- Final manual security/correctness/simplification review found no further source issue:
  expected features are optional assertions, never grants; existing actor/company/tenant
  checks and command fencing remain in force. Reconciliation recognizes exact system
  recipes only, and writes immutable revisions/audit events atomically. The proxy opens
  only the exact company-scoped POST without query parameters. UI result verification
  rejects another company and preserves the same retry key. No new table, authority
  grant, financial effect or cross-service call inside a write transaction was added.

### Local activation follow-up

- [x] Obtain valid local migration credentials from the user without saving them in source.
- [x] Back up the existing Vouchers database, then apply only pending migration `0111`.
  This is the previously authorized print-job table, not a new requirement of defaults.
- [x] Restart only the managed Identity and Vouchers APIs and Vouchers source worker;
  confirm API readiness, live bootstrap route and signed automatic discovery.
- [x] Observe worker provisioning before any explicit preparation: the local database now
  contains the 38 inventory defaults plus the existing custom `PUR` type (39 rows).
- [x] Confirm authenticated preparation/replay and responsive directory rendering.
- [x] Complete authenticated browser verification after activation. Final live check
  passed at 1440 px and 390 px, with loaded directory rows, no horizontal overflow and
  no JavaScript errors. The UI preparation returned READY with 0 created, 0 updated and
  38 preserved; another preparation made no changes and retained exactly 39 types.
  Evidence: `.tools/voucher-defaults-usability-browser-final-active.log` (exit 0) and
  `.test_artifacts/voucher-defaults-review-20261031/review.json`.

Earlier browser attempts used the wrong company display-name assumption and clicked
before the client handler was attached. Corrected the task-local runner to verify company
selection through the application's authorized endpoint, await the completed Console
redirect, and wait for loaded rows/hydration. Those failed attempts were not counted as
passing verification; no application change was needed for those runner failures.

The user subsequently supplied working migration credentials. A fresh private backup was
completed, only `0111` was applied, and all pre-existing document/type row counts were
retained. The two APIs and source worker were restarted through the existing ownership-
checked launchers; other services and the parallel UI processes were preserved. Both APIs
are ready and the live bootstrap route is present. No posting or print renderer was enabled.

## Decision log

## Follow-up decision log

- 2026-11-03: Owner direction, "no unnecessary blockers": a company with its parties and
  accounts must be able to create and post without extra configuration. Selected
  **catalogue v4**: `SAL_ACC` takes SERVICE supplies (so a GST company can post a taxed
  Sale); invoices and notes allow manual discounts and charges; Payment and Receipt allow
  settlement adjustments; no type requires narration or line descriptions. v1-v3 recipes
  are kept exactly (their hashes recognise untouched types, which follow v4 on the next
  voucher setup; authored types are never replaced). Issuing without a series now uses a
  per-type automatic series instead of refusing. Approval for administrator-created types
  was **not** changed: the type form shows approval on by default and it can be switched
  off there; the starter catalogue already follows `approval_workflow`.

- 2026-11-02: User asked that the Purchase account bill take service lines by default, so a
  new company can record GST without editing its type. Selected **catalogue v3**: `PUR_ACC`
  allows ACCOUNT and SERVICE; nothing else changes. Earlier recipes (v1, v2) are kept
  exactly, because their hashes are how an untouched system type is recognised. New
  companies get v3 from discovery. An existing company's untouched `PUR_ACC` follows on the
  next explicit voucher setup as a new immutable revision (the first revision stays as
  issued); an authored or edited type, such as one changed in the type editor, is never
  replaced. Sales account invoices still allow ACCOUNT only; the Sales console picks a
  service tax profile when the company has a GST registration, so the same one-line change
  is the likely follow-up there.

- 2026-10-31: Accepted the user's authorization for company-level automatic defaults,
  separated invoice entry variants from base kinds, and selected existing signed Identity
  discovery plus an explicit onboarding bootstrap for reliable, retryable provisioning.
- 2026-10-31: Further usability review selected catalogue v2, safe immutable upgrades
  for untouched v1 system rules, an administrator preparation action for existing companies,
  and policy-driven requisition purposes. Specialised entry/effect gaps remain explicit.

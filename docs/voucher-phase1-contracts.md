# Phase 1 implementation contracts

Recorded 2026-10-10. These are implemented foundation contracts, not approval of later
business policies. The authoritative batch statuses remain in the delivery tracker.

## Ownership and schema

Vouchers owns stable document/revision/line identity and immutable accepted configuration.
Accounting owns all actual GL, bill/advance, tax and future stock/custody/value effects.
Catalog owns items, units and inventory policy definitions; Identity owns actors/company
calendar and custom definitions. There are no cross-service foreign keys or database reads.

The initial Vouchers migration chain has 36 one-statement revisions: 33 shared voucher
tables plus outbox, inbox and idempotency. It is a Phase 1 subset/expansion of the candidate
table inventory, not a replacement of the complete future 51-candidate design.

| Area | Tables |
|---|---|
| Concurrency/identity | voucher_company_guard, voucher_type, voucher_type_revision, voucher_type_section, voucher_class, voucher_type_origin |
| Native configuration | voucher_configuration_profile, voucher_configuration_revision, voucher_configuration_binding |
| Document content | voucher, voucher_revision, voucher_line, voucher_item_detail, voucher_party, voucher_reference, voucher_attachment, voucher_link |
| Workflow | voucher_approval, voucher_transition, voucher_operation, voucher_posting_reference |
| Issue/print | voucher_number_series, voucher_number_counter, voucher_number_assignment, voucher_template, voucher_template_revision, voucher_artifact |
| Custom values and owner evidence | voucher_definition_projection, voucher_field_adoption, voucher_custom_claim, voucher_custom_sequence, voucher_custom_index, voucher_master_evidence |
| Platform | outbox, processed_message, idempotency_key |

Every business row carries tenant/company identity. Composite foreign keys enforce scope.
Stable line keys distinguish a logical line across immutable content revisions. Exact
quantities are DECIMAL(19,4); no posting/balance tables are introduced in this service.
Scope/identity/revision immutability is enforced by the API and ORM flush guards.

## Mutation and publication

Commands require signed, fresh actor/company context, scoped action permission, object
ownership, current field authority, expected version and an idempotency key. The company
guard serializes document/configuration/numbering/adoption writes; successful commands and
reference-only audit events commit together. Replays recheck current authority and render
current protected resources from references, not a cached unmasked response.

Configuration intersects allowed sets, tightens limits and combines requirements.
Unknown controls fail validation. Common/Sales/Purchase bindings are effective-dated and
cannot overlap in the same company/type/family scope. Type/class revisions are immutable;
publication or type changes require a new accepted voucher revision and approval before
further execution. Rejection/cancellation can still abandon a draft after its type retires.
Custom fields never determine accounting behavior or bypass native configuration.

Configuration precedence is company COMMON, company family, type COMMON, type family,
type revision and class, independent of creation order. Allowed series/template revision
sets intersect; explicit narrower defaults override inherited defaults within those sets.
Publication validates company ownership and active references. Issue requests may omit the
series to use the effective default. Artifact requests may omit the template to use the
accepted document revision's default; later configuration cannot rewrite historical output.

`domain/custom_copy.py` supplies explicit, bounded header/item value mappings for later
conversion producers. It checks source-read/target-write authority, compatible types and
option/dependency identities, target scalar bounds and static choices. Auto-numbers and
unique target claims cannot be copied. The normal target write must still check current
visibility, dynamic options and requiredness, allocate new identities and atomically retain
source revision/line references. This is a conversion primitive; actual order, challan,
return and job-work conversions remain in their own batches.

## Signed owner transport and operation identity

Signed transport binds issuer/audience/operation, HTTP method, path, query and body.
Credentials name explicit tenant/company grants. Snapshot responses additionally bind the
original request. Only Identity can supply custom definitions; only Catalog item/unit
facts and Accounting party facts are accepted. Same source version with different content,
or same message identity with a different body, fails. Stale versions are ignored.

Future execution identity includes tenant/company/voucher/revision/operation/execution,
content/configuration/request hashes, separate posting/stock/statutory dates, period
versions, actor, approval references and expiry. Result states are PENDING, COMMITTED,
REJECTED or CANCELLED. Terminal results are immutable and exact duplicates are harmless.
COMMITTED requires an aware commit time and an Accounting source receipt, including
zero-GL future profiles. Owner effect references are deduplicated.

The shared wire package is `clients/voucher-execution`. Vouchers persists the exact command
with its operation before delivery. Queueing checks fresh user/company context, posting
permission, approved current revision, approval IDs, effective configuration, typed common
content and owner master evidence under the company fence. An unresolved attempt blocks
content/workflow changes and configuration publication/adoption. Ordinary cancellation
cannot release it; operation cancellation remains PENDING until Accounting answers.

Accounting owns `voucher_source_guard` and immutable `voucher_execution` receipts in migrations
0109-0110. Its private signed command/status adapter serializes on Accounting's existing
company lock, then source/attempt identity. A terminal receipt wins before fresh-authority
checks, so replay after expiry, a period close or a year boundary returns the original result.
Cancellation before delivery creates the attempt tombstone. A conflicting attempt cannot
claim a committed source. A new commit and its owner generation, source receipt, callback
effects and audit outbox are one transaction; failure rolls all of them back. Open-period
status, exact period versions, books-begin date and company configuration are checked inside
that fence. Local committed delivery adds a POSTED transition and durable effect references.

The delivery worker first reconciles status; only an unknown execution sends the original
command/cancel. Network/signature failures do not release an operation or change its identity.
Requests and responses are signed and request-bound with explicit company service grants.
The owner adapter's production dispatcher has **no enabled financial/stock profile**. Native
contract tests exercise its transactional callback boundary without inventing a GL entry.
B10 and subsequent profile batches must add native typed effect executors, current Identity
first-use/reservation authority and their full monetary/stock failure-injection cases before
activation. Passing the C0 protocol tests is not evidence that those future profiles work.

## Years, numbering, artifacts and reporting

The signed company calendar derives the document's fiscal start; it is not period-posting
authority. Number assignments use company + series + fiscal start + sequence, allocate
under the company/series counter fence, and remain with the issued revision. Supplier,
issue, internal journal and future statutory identities are separate concepts.

Artifact work pins document/template and disclosure evidence. Lost acknowledgments retry
the same work. Rendering escapes content, hashes its output and cannot allocate financial
or stock effects. Downloads expire and recheck current authority/disclosure fingerprint.

The public voucher export is a masked current-document feed using the platform page envelope.
It is not a financial statement or committed Accounting export. B03 fixes the following
D11 contract for the B09 implementation, rather than treating this draft feed as a report feed.

## Initial decision slices and dependent contracts

These decisions resolve the **foundation slices** of D01/D04/D05/D06/D07/D11/D12. Later valuation,
VAT-jurisdiction, bank-recognition and statutory-provider decisions remain in their existing
gates. No unimplemented control is accepted as executable configuration.

| Contract | Foundation decision and later obligation |
|---|---|
| D01 authority | Vouchers owns content/approval/configuration; Accounting owns all effects and source receipts, including future zero-GL stock. No cross-service SQL, foreign keys or independently editable balances. Source cancellation is definitive only after an owner tombstone; committed effects require a supported correction. |
| D04 atomic financial intent | The owner receives immutable revision/source-line identity, hashes, dates, captured policy and original source distribution. A future native executor must validate its discriminated payload and write journal, subledger, allocation, tax and value effects atomically as applicable. Exact decimal strings and explicit currency/unit bases; custom values cannot substitute for account/tax/quantity fields. Unknown profiles remain rejected. |
| D05 document identity | Document identity, issue number, Accounting internal number, legal invoice identity and supplier reference are separate. Fiscal dates use the signed company calendar. C0 allocates only issue numbers; existing Accounting numbering stays compatible. Statutory registration/series uniqueness and legal invoice-year allocation are B19 obligations, not an implied C0 statutory invoice. |
| D06 configuration | Native COMMON/SALES/PURCHASE profiles bind at company/type scope with non-overlapping half-open dates; type/class constraints narrow them. Historical accepted revisions and clone origin are retained. Registered C0 settings are bounded native policy; future commercial, bank, stock, scheme and tax settings require the corresponding owner implementation before acceptance. |
| D07 grains | One header per stable voucher; one immutable revision per edit; stable logical line key across revisions; one ITEM detail per item line; reusable party/reference/attachment/link children. Company-scoped unique keys/FKs protect all aggregates. Native effect/distribution and stock dimension extensions belong to their later manifest slices; no per-kind/per-year tables. |
| D11 reporting | Owner exports carry complete immutable source facts and classified opening/history coverage under the barrier contract below. Registers/summaries are rebuildable projections, never balance authorities. The existing Accounting cumulative balance API keeps its meaning; date/current/currency summaries get separate explicit contracts. |
| D12 fiscal authority | Document, posting, stock, statutory and credit-term dates are distinct. The effect owner verifies each applicable period and version at commit; reopen changes the version and invalidates pending previews. Retry of a committed identity returns its old receipt/year/number. Distributed close/readiness and stock-period extensions are required in B10/B21, not inferred from issue numbering. |

### D11 committed export and projection barrier

An owner begins an export with `(tenant_id, company_id, contract_version, scope_hash,
permission_hash, snapshot_id, generation, schema_hash, coverage_start, coverage_kind)`.
`coverage_kind` distinguishes complete history, reviewed opening plus later history, and
incomplete history. Incomplete coverage cannot silently produce a complete statement.
The owner must freeze the snapshot at the committed company generation; live keyset paging
alone is insufficient. Feed pages and end markers are bound to this identity and each grain.
A terminal source receipt's `committed_generation` is retained even when later company
transactions/close transitions advance the live generation.

Required grain identities include journal line, account/party/dimension allocation, dated
open item/advance/allocation/reversal, tax component, stock quantity leg, stock value leg,
origin/cost allocation and classification/opening evidence. Each has its own immutable
owner ID and source revision/logical-line references. A header total is counted once;
joining a financial line to multiple taxes/locations/allocations must not multiply it.
Classification versions must preserve statement section, nature, sign/contra treatment,
netting and unmapped-balance diagnostics; account group labels are not statement authority.

Changes after the snapshot use an ordered committed change sequence with transaction ID,
source receipt, generation, event ID and explicit tombstone/correction relationships.
A consumer commits all facts from one owner transaction, dedupe receipt and checkpoint
atomically. It publishes a report generation only when every required feed reaches the
same declared end barrier; gaps, incompatible versions, changed field authority or partial
owner transactions invalidate readiness. Cross-owner report runs declare their compatible
checkpoints instead of pretending distributed commit time is a single database snapshot.

Rebuilds write a shadow generation from a verified snapshot plus ordered catch-up. Compare
control totals (debit/credit, open-item/advance allocation, tax and stock quantity/value),
validate coverage and then switch the active generation atomically. Never overwrite source
facts or mix old/new summary generations. Historical financial outputs pin classification,
opening bridges, as-of allocation evidence, fiscal periods and source/checkpoint provenance.
B09 implements this export/barrier; later report batches extend its required grains.

### D12 and future stock execution extensions

Fiscal close preparation must enumerate producers, unresolved attempts, pending corrections,
valuation/import work and report checkpoints by company/effect period. Freeze admissions,
reconcile every accepted attempt, and commit the close under the same owner company/period
fences used by execution. Missing producer evidence blocks close; legitimate outstanding
bills, advances, custody and transit balances carry forward without synthetic settlements.
Reopening is versioned and invalidates cached readiness and dependent projections.

Future stock executors use company/period fences, source/return/fulfillment claims, sorted
canonical position keys, origin/lot/serial locks and then value/cost allocations. Physical,
owned, third-party, reserved, eligible and available quantities are separate declared scopes.
No nullable-key duplicate positions or independent stock-balance edits. Repairs/imports are
staged, fenced and reconstructible from immutable quantity/value histories; valuation and
original-return caps remain mandatory in B20-B27. Non-posting orders/quotes/requisitions
cannot produce stock/GL effects merely by selecting an inventory-capable system kind.


### B09 implementation of the D11 foundation slice

[B09](voucher-b09-execution.md) implements the barrier above for Accounting's 15 existing
financial/classification/fiscal/opening/settlement grains. Its v1 coverage categories are
RETAINED_LEDGER and INCOMPLETE; neither certifies imported full YTD or a complete statement.
SOURCE_RECONCILIATION is the only available definition. Native head nature, hierarchy,
netting/gross-profit flags and frozen labels are retained; statement mappings/earnings/netting
and full opening bridges remain B14. Per-company committed bundle UUID/sequence replaces a
broker-message dependency for ingestion identity. Broker audit delivery remains separately
confirmed and deduplicated. Future stock/tax/dimension grains extend the same contract.

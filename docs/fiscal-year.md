# Fiscal Year & Period Control

**Status:** Monthly fiscal controls, the guided next-year Console workflow and verified financial/bill/advance continuity reviews are implemented. Wider Vouchers/stock/tax producer readiness remains gated; automated annual earnings transfers and special calendars remain deferred.
**Date:** 2026-10-26
**Owned by:** `accounting` service (calendar config originates in `company`)
**Related:** [tech-stack.md](tech-stack.md) rules 4.5 (ledger as audit trail), 4.11 (reports) · [org-model.md](org-model.md)

## Decision log — 2026-10-26

The approved next-year UI/API delivery implements calendar preview, generation/reuse,
readiness checks, explicit period opening and browser year selection. Financial continuity
uses cumulative retained ledger history and original open-item identities. It is available
as a verified frozen Reports review; it does not create an annual opening or profit-transfer
journal. This clarifies the older deferral of annual carry automation: ordinary balances
already continue without that automation. Deferred earnings transfers, special calendars,
inventory and additional producer evidence remain governed by their existing gates.

These rules constrain every financial posting. Accounting owns actual posting authority;
the planned Vouchers API submits documents through the [Vouchers contract](vouchers-plan.md).
The enforcement mechanism belongs in the shared platform library.
The [posting/reporting design](voucher-posting-reporting-design.md) defines financial
statements, entered-opening versus derived-carry semantics and reproducible report runs.
The [company financial-year design](voucher-financial-year-design.md) governs the required
next-year workflow, cross-year settlement/stock continuity, D12 contracts and FY01-FY24 checks.

---

## 1. Scope

The console company lists link to `/companies/{id}/years`. This provides a paged
year directory, generation from company settings, and year details with twelve monthly
periods and scoped open/close/reopen/lock actions. The [management review](company-year-management.md)
records the end-to-end fixes and verification. Dates/codes are generated; period
transitions require a reason, current row version and an idempotency key.

Choose **Start next financial year** from the directory or a year's action menu. The
guided page reviews the company-scoped Accounting `next-preview`, generates or reuses
the target, checks posting prerequisites, opens only explicitly selected future periods,
then offers **Use this year**. **Review opening balances** on year details opens the
Reports `BALANCE_CONTINUITY` workspace with frozen source results, search, bounded
pagination, signed row/ledger/bill actions and exports. Report pages default to the selected
year, offer the previous year and preserve explicit custom dates per company.
Delivery evidence and review findings: [workflow TODO](financial-year-workflow-todo.md).

**Fiscal calendars are per company, not per tenant.** A group can hold an Indian entity on Apr–Mar and a US entity on Jan–Dec under one tenant. `company.fiscal_year_start_month` / `_day` ([org-model.md](org-model.md) §4.2) is the source; fiscal years are generated from it.

### 1.1 Ownership and replication

`accounting` is the **master** for `fiscal_year` and `fiscal_period`. Closing and locking a period is an accounting act bound to the ledger, so it belongs with the ledger — not in `identity`, which only holds the calendar *configuration*.

- `accounting` owns the tables, generates years and periods, and executes all status transitions.
- Transitions emit the implemented `accounting.fiscal_period.changed` contract through the
  transactional outbox. Publication happens after commit; the broker is not a transaction lock.
- Vouchers and Reports may keep read-only period projections for validation previews and display.
- Accounting calls the shared posting guard against authoritative local fiscal state under
  the same company lock as close/lock transitions. A stale Vouchers preview cannot authorize
  a late posting; a queued command reaching a closed period fails the current guard.
- Future stock/value posting follows the same authoritative owner and defined inventory
  period policy. No separate Payments service or distributed close window is assumed.

---

## 2. Entities

The implemented [models](../apis/accounting/src/accounting/models/fiscal.py) use the common
Record identity, tenant/company scope, version and actor/timestamp fields plus:

```text
financial_setup        (base_currency, books_begin_date, fiscal_year_start_month,
                        fiscal_year_start_day, amount_precision, rounding_mode,
                        timezone, configuration_hash, first_posted_at)
fiscal_year            (code, start_date, end_date)
fiscal_period          (fiscal_year_id, sequence, code, start_date, end_date, status)
fiscal_status_transition (period_id, from_status, to_status, reason)
```

`fiscal_year` has no implemented `status` or `is_current` column. Posting authority and
transitions are at period level; a year summary is derived from its twelve periods and can
be mixed. The transition's Record fields identify its actor and creation time. There is no
implemented adjustment-period flag or annual year-close transition. A selected year is a
planned user/session preference, never another posting gate.

Accounting also owns the implemented `document_sequence`, journals and once-only entered
opening batches. A future `account_opening_balance` would be a derived cache, not a second
posting. Proposed readiness evidence and numbering extensions are listed in the
[financial-year design](voucher-financial-year-design.md); they require D07/D12 manifests.
Do not create a table or a new company for each year.

### 2.1 Explicit recovery of unused financial setup

Accounting exposes `POST /v1/companies/{company_id}/financial-setup/reconcile` for
an explicit correction using current, signed company settings. It requires finance
read/manage authority, a reviewed configuration digest, an expected setup version,
a reason and an idempotency key. Calendar-anchor changes additionally require
`period.manage`, fiscal read access and authorized field changes.

Reconciliation is refused after first posting or when financial records, used accounts,
numbering or closed periods depend on the old setup. Existing complete calendars retain
year/period IDs and statuses while receiving corrected date ranges, new versions and
transactional revision/audit evidence. Ordinary initialization and posting still reject
configuration drift. The command does not automatically open another period.

This is Accounting recovery, not the complete cross-service company edit workflow.
Identity prevention before unsafe edits commit and reservation/concurrency integration
remain pending. See [remediation evidence](company-financial-year-fixes.md).

---

## 3. Status lifecycle

| From | To | Required permission |
|---|---|---|
| FUTURE | OPEN | `period.manage` |
| OPEN | SOFT_CLOSED | `period.close` |
| SOFT_CLOSED | CLOSED | `period.close` |
| SOFT_CLOSED | OPEN | `period.reopen` |
| CLOSED | OPEN | `period.reopen` |
| CLOSED | LOCKED | `period.lock` |

These transitions, reason/version checks and preceding-period restrictions are already
implemented. `LOCKED` is terminal. Opening the next year does not close the old one.

| Status | Posting permission | Meaning |
|---|---|---|
| FUTURE | None | Generated period; a draft may refer to its date but cannot post |
| OPEN | `period.post` | Ordinary posting window |
| SOFT_CLOSED | `period.post_adjustment` | Authorized adjustment window |
| CLOSED | None | Requires an explicit authorized Accounting reopen before posting |
| LOCKED | None | No application reopen path |

Filing a tax return does not automatically lock the GL period. Filed-return correction rules
and an authorized terminal GL lock are separate controls. Reports/Vouchers projections do
not grant posting or reopening authority. Default role assignment is a separate policy gate.

---

## 4. Posting rules

### 4.1 Posting date is not document date

Three dates, deliberately distinct:

| Field | Meaning |
|---|---|
| `document_date` | The date on the face of the invoice — what the customer sees |
| `posting_date` | The date that determines **which accounting period this hits**. Drives fiscal posting enforcement |
| `created_at` | When the row was written. Audit only, never used for period resolution |

An invoice dated 31-Mar and entered on 5-Apr uses its explicitly requested posting date.
A requested March posting is rejected if March is closed; the system must not silently
change it to April. An authorized Accounting reopen or an explicit permitted April
adjustment is a separate action, preserving the original document and tax evidence.

The planned [India tax contract](voucher-tax-recording.md#3-native-tax-facts-and-dates) also
records statutory supply/invoice/payment dates and derived tax events. Posting to April does
not automatically move the legal tax event into April. Tax reporting periods and filed-return
locks are distinct from GL close; corrections preserve original evidence and use the applicable
tax adjustment procedure. Extending the current posting-date tax resolver is explicit future
compatibility work, while `assert_postable` continues to use the accounting posting date.

### 4.2 One guard, in the shared library

```python
assert_postable(company_id, posting_date, actor)
```

Resolves `posting_date` → `fiscal_period`, then admits or rejects based on period status and the actor's permissions. Every financial write calls it. Not per-endpoint checks — those get forgotten in exactly the code paths that matter.

Also reject `posting_date < company.books_begin_date`, and reject dates falling in no generated period at all.

### 4.3 Overlapping open years are normal

Do **not** require year N to be closed before year N+1 opens. You will be trading in FY27 while still adjusting FY26 for months. Forcing sequential year close is a common design error that only surfaces at the first year end, by which point it is expensive.

Sequential close *within* a year is a different matter and should be enforced: period 4 cannot close while period 3 is open.

### 4.4 Corrections after close are new entries, never edits

A correction uses append-only reversal/adjustment facts referencing the original. For a
`CLOSED` period, Accounting already supports an explicit authorized reopen; a permitted
current-period adjustment is another option. `LOCKED` cannot reopen. Neither option edits
an original posted journal or silently changes its date (tech-stack.md rule 4.5).

No code path anywhere may mutate a posted document in a closed period.

### 4.5 Selected year is a UI default only

The implemented company-scoped browser selection decides which year a view opens on.
There is no implemented fiscal-year `is_current` field. Enforcement always resolves date
to period. Treating the selected year as a posting gate breaks legitimate use of two open years.

---

## 5. Close preconditions

Implemented Accounting checks include a finalized initial opening before closing a period
that reaches books-begin, in-period draft/prepared journals, pending opening batches and
charge assessments, failed unpublished company outbox rows, undelivered company
posting confirmations and party-control reconciliation. See
[closing checks](../apis/accounting/src/accounting/tasks/reconciliation.py). These are not
proof that a future Vouchers/stock/tax producer has completed all work.

Required D12 integration adds a durable readiness checklist: relevant document/effect
intents, recovery of unknown outcomes, producer fences/versions, complete source evidence,
GL/subledger and selected inventory/value reconciliation, plus explicit blocker versus
warning policy. Do not block merely because an invoice is unpaid, an order unfulfilled,
goods legitimately in transit or stock with a job worker. Those balances carry forward.
Unselected recurring billing or optional bank automation cannot become silent prerequisites.

Prepare producer evidence before taking the final Accounting company lock; recheck local
period versions and fencing state inside that lock. Never wait on a remote service while
holding it. Missing or stale required evidence blocks close; a late queued posting rechecks
the authoritative period and is rejected after closure. Contract details remain D12 gates.

---

## 6. Year-end switch

**Normal calendar and financial continuity are implemented in Accounting, Reports and
Console.** The guided flow checks Accounting prerequisites. Wider producer readiness
remains part of the Vouchers integration gates. Neither depends on annual profit-transfer
automation or closing every old period:

1. Use Accounting's existing idempotent generation command to create the next year and
   twelve monthly periods. Generation leaves them `FUTURE`; no scheduler or automatic
   activation is currently implemented. Validate dates, overlaps and the company calendar.
2. Validate numbering policy and the new sequence namespace for each enabled profile.
   Current internal journal sequences are created lazily; statutory identity is a separate
   D05 contract. Do not reset an old counter or renumber issued documents.
3. Explicitly open authorized new periods. Change the user's selected year/date defaults
   without changing company books-begin or financial-year configuration.
4. Verify financial, bill/advance, bank, stock/cost/age and order/job-work continuity from
   existing facts. Create no duplicate annual opening journals, bills or stock receipts.
5. Review/close old periods independently when their readiness gates pass. Multiple years
   can remain open. A multi-period operation is resumable, not a distributed atomic year switch.

Automated earnings-transfer journals, derived opening caches, special calendars and
unrealized FX revaluation remain separately selected future work. Reports must already
bridge prior unclosed earnings into equity and show only the selected year's operating
income/expense. If a later classified closing transfer is introduced, never count its
profit again through that bridge.

### 6.1 One company, many years

TallyPrime explicitly supports continuing in the same company by changing the current
period, carrying balances and keeping the original books-begin dates. Creating a new
company or splitting data are alternatives, not mandatory year-end actions.
[Official TallyPrime guidance](https://help.tallysolutions.com/moving-to-the-next-financial-year-india-change-current-period/).

Our design retains one company and continuous history across all fiscal years. Year/period
filters change views; they do not change ownership or break bill/stock lineage. A company
may have multiple legal document series and tax registrations. Cross-year receipts,
returns, advances, challans and job work retain their original references. Details and
worked examples are in the [financial-year design](voucher-financial-year-design.md).

---

### 6.2 First year — entered opening balances, not generated

A company migrating mid-year has `books_begin_date` after `fiscal_year_start`, and its opening balances are **entered by a human from the previous system**, not derived from a prior year we do not have.

The implemented authority is `opening_batch` with once-only posted opening journal/open-item
facts, as specified in the [finance contract](accounting-finance-contract.md). Entered
debits and credits and party bill details must reconcile. These are financial facts, never
overwritten by a cache regeneration job. `account_opening_balance` is only a deferred derived
carry proposal; the older `generation_version = 0` sketch is not the entry contract.

A correction to the initial opening requires its period to be postable and no later CLOSED
or LOCKED period. Explicitly reopen affected later CLOSED books before reversing a posted
opening or reopening a finalized zero opening. LOCKED books remain terminal, so the
correction cannot proceed through this workflow.

Migration must record balances-covered-through date, originating fiscal year and supported
YTD provenance. A trial balance may move explicitly identified initial-opening facts into
opening columns only when the same facts are excluded from movement columns. YTD amounts
without monthly history do not support invented monthly comparisons. Report coverage and
opening/earnings treatment are explicit D11 contracts, not implied by a fiscal-year row.

### 6.3 Back-dated posting limit

An open period legitimately accepts back-dated entries — that is what makes it open. But an open period with no restraint means a clerk can post to April in December by typo.

`company.backdated_posting_limit_days` (nullable, default null = unrestricted) rejects a posting whose `posting_date` is more than N days before today, **even when the period is open**. Holders of `period.post_adjustment` bypass it (section 3).

This is a softer control than period status and complements it: status answers *is this period accounting-open*, the limit answers *is this date plausible for routine data entry*. Both are checked in `assert_postable` (§4.2). Forward financial posting requires a generated period whose status and permissions allow
posting; existence alone is insufficient. The stock-effective-date policy is separately
gated under D03. Evaluate the backdate limit using the company timezone.

### The trap: opening balances go stale

If a permitted backdated adjustment changes source history after a carry snapshot was
generated, that snapshot becomes stale for a new run. Invalidate/regenerate dependent caches
from authoritative facts and pin source/version manifests. Previously frozen reports retain
their original evidence; entered opening journals are never regenerated.

Current fiscal guards still apply: Reports cannot reopen books. Accounting already allows
authorized CLOSED/SOFT_CLOSED -> OPEN transitions; LOCKED is terminal. Planned D11/D12
integration must invalidate affected derived caches after reopening and permitted changes,
without modifying previously frozen report artifacts.
A lock restricts posting; it does not by itself freeze report formulas, labels or ingestion.

---

## 7. Document numbering

Keep three identities distinct: Accounting's internal journal number, the issued statutory
voucher/invoice number, and an external supplier reference. The current journal allocator
keys on `(company, posting fiscal year, journal kind)` and produces an internal reference;
its existing format must not automatically become the GST invoice number.

The planned statutory identity uses the issuer registration, legal document category,
series revision and legally applicable year/date basis. India IRN identity derives its
financial year from invoice date, which may differ from the GL posting year. GST invoice
numbers support multiple series and a maximum of 16 permitted characters. Pin current legal
rules per enabled profile; do not infer all legal requirements from the internal allocator.
[GST invoice-number FAQ](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm),
[IRP document/FY identity](https://einvoice6.gst.gov.in/content/irn-2/).

D05/D12 must specify the complete uniqueness scope, normalization, allocation and migration
contract. Proposed rules:

- Accounting remains the final posted/statutory number authority. Assign it atomically with
  its authorized effect, with explicit recovery where statutory preparation needs identity
  earlier. Return internal and statutory identities separately when they differ.
- Vouchers assigns separate issue-time numbers to orders, quotations, memos and challans;
  these do not consume an invoice sequence or prove stock execution. Draft/operation IDs
  are not issued invoice numbers.
- A new fiscal year creates a new sequence namespace. Old counters, issued identities,
  cancellations and void reasons remain immutable; never reuse an issued number.
- Lock sequence allocation in the owner transaction, use native scoped uniqueness, and
  bind replay to the original operation/date/policy revision even across midnight/year-end.
- Company-created voucher types must not evade statutory uniqueness through a different
  UI type ID. Migration/import adopts validated original identity without resetting a live counter.
- Effective prefix/suffix/reset changes create policy revisions; reprinting or backdating
  does not renumber previously issued documents.

TallyPrime supports automatic, manual and other voucher numbering methods. These inform
configurable product design; they are not evidence that Indian law permits only automatic
software numbering. Automatic allocation is our default product control. Any selected
manual/override/import mode needs the same legal-profile uniqueness, chronology, cancellation
and audit checks. `none` cannot be used where a statutory number is required.
[TallyPrime numbering methods](https://help.tallysolutions.com/use-voucher-numbering-methods/).

The proposed policy includes method, reset basis, prefix/suffix, width and effective revision.
It is not the current `document_sequence` schema. D07 records exact native columns/tables
before implementation; never create one table per voucher kind or fiscal year.

---

## 8. Reporting interaction

A report is defined by its business period AND a committed source snapshot, classification/
formula/rule versions and history coverage. Period locks alone cannot guarantee reproducible
output. Reports must reach the owner's snapshot barrier, reconcile control totals and freeze
the run manifest and artifact hash. Re-downloading an approved artifact returns that artifact;
recomputation at its pinned inputs must reproduce its financial rows/totals.

Late permitted postings, delayed ingestion or revised presentation create a new run with
explicit comparison/restatement evidence. They do not overwrite the old run. Projections
record posting/tax periods and source identities so affected views and derived carry caches
can be rebuilt. Unclosed prior-year nominal balances enter the Balance Sheet's earnings
bridge; closing-transfer profit already in equity is never added a second time.

---

## 9. Open questions

- [x] **Period granularity:** twelve monthly periods are the implemented scope. Other calendars remain deferred.
- [ ] **Adjustment period 13** — a zero-length period dated at year end, for audit adjustments that must not disturb month 12's reported figures. No `is_adjustment_period` column is currently implemented. Confirm whether it is required
- [ ] **Multi-currency revaluation at close** — is unrealized FX gain/loss in scope?
- [ ] **Consolidated group reporting when companies have different fiscal starts** — genuinely hard; needs a defined approach before multi-company groups are sold
- [ ] Who holds `period.reopen` and `period.lock` by default — which system roles
- [ ] Retention and archival policy for locked years; does an `ARCHIVED` status follow `LOCKED`?
- [x] `FUTURE` periods may be selected on drafts; prepare/post must satisfy the authoritative period guard. Generation does not authorize posting.

## Decision log - 2026-09-15

The approved Accounting finance increment owns fiscal years, monthly periods, journals,
entered openings, open items, credit controls and overdue charges. Special calendars,
adjustment period 13, annual closing/carry-forward and unrealized FX revaluation are
deferred. Monthly scope was explicitly confirmed. Accounting callers use the shared
local posting guard. Period changes and posting serialize on the same company lock.
The older discussion of Billing ownership is superseded by this decision and
[the finance contract](accounting-finance-contract.md). Replication consumers require
versioned events; a pre-commit broker publish is not permitted. External consumers and
their close acknowledgements remain an integration gate before distributed posting.

## Decision log - 2026-10-10

The later financial-reporting review corrected the stale annual-opening sketch: entered
openings are once-only journal facts, carry is a deferred derived cache, and annual-close
automation remains deferred. Added multi-year earnings/YTD coverage and frozen report-run
requirements; removed the claim that period locking alone yields identical reports.

Vouchers replaces the planned Billing/Payments APIs. Accounting remains the posting and
period authority; projections cannot authorize posting after close. Removed the obsolete
replica-lag allowance and pre-close publication suggestion. The new plan proposes the same
transaction owner for financial and stock/value effects, with V0 acceptance gates. Numbered
non-posting documents use separate series from actual posted vouchers. Older entity sketches
and wider fiscal features remain design proposals where the finance contract defers them.
The user's order/quotation/challan clarification extends separate issue-time series to these
explicit document profiles; challan printing cannot allocate or duplicate stock movement.
The India tax extension separates statutory tax events/return periods from fiscal posting.
Late entries retain original tax evidence instead of moving liability solely to match open
books; this requires a versioned future tax-context contract. A tax correction does not
automatically authorize reopening a GL period.


### Company financial-year review - 2026-10-10

The user requested proper company-year behavior across vouchers, transactions and balances.
Added the linked financial-year design, D12 and FY01-FY24. Corrected old sketches against
implemented models/transitions: no year status/current flag, CLOSED and SOFT_CLOSED already
reopen with permission, and generation creates FUTURE periods without a scheduler. Normal
next-year continuity is required; automated earnings transfer remains deferred. Corrected
Tally split-data and automatic-only legal-numbering claims, prohibited implicit redating,
and separated statutory invoice FY from posting FY. RF25-RF32 track remaining integration.

## Decision log - 2026-10-12

Accounting close now enforces the same finalized-first-opening invariant as its readiness
preview. Initial-opening corrections are fenced against later CLOSED/LOCKED periods, even
when the original period has been reopened. Fiscal readiness compares frozen company book
settings with the current signed context; a later configuration digest or timezone change
alone does not make otherwise valid books appear unready, while an inactive company is
explicitly blocked. The two-year journal regression
verifies independent numbering and cumulative balances without annual opening duplication.
The local close checks do not yet constitute D12 producer evidence for every enabled remote
stock/tax/document source; distributed activation still needs that gate.

## Decision log - 2026-10-22

Following the authorized company/fiscal review remediation, added an explicit unused-books
reconciliation command rather than changing normal initialization's configuration guard.
Calendar IDs, statuses and previous revisions remain intact, and financial dependencies
prevent reinterpretation. This implements the Accounting recovery portion of C01 only;
Identity pre-commit prevention, management UI and native cross-service concurrency checks
remain pending as recorded in the linked remediation evidence.

# Company financial years, vouchers and balance continuity

**Date:** 2026-10-10. **Status:** Required fiscal contract with a Phase 2 money implementation.
[Phase 2](voucher-phase2-execution.md) implements ordinary
money readiness, owner close integration and cross-year financial report continuity.
Later producer/stock/tax fiscal evidence remains gated; no real company was transitioned.

**Console delivery, 2026-10-26:** the six-phase [workflow](financial-year-workflow-todo.md)
adds the guided next-year calendar/check/open/select page and the same-snapshot
`BALANCE_CONTINUITY` review for accounts, bills, advances and accumulated earnings.
Selected-year report presets and persistent explicit custom dates are implemented.
Accounting still owns each audited period command; Reports retains immutable sources,
result paging, signed drilldowns and exports. This does not activate deferred producer gates.

The user requires company financial years to govern vouchers, transactions, balances and
reports correctly. Ordinary new-year readiness and continuity are required voucher scope.
Automated annual profit-transfer journals, special calendars and unrealized-FX automation
remain separately deferred; they are not prerequisites for starting the next year.

Read with [fiscal controls](fiscal-year.md), [finance contract](accounting-finance-contract.md),
[financial reports](voucher-posting-reporting-design.md), [stock reports](voucher-stock-recording-reporting-design.md),
[tax dates](voucher-tax-recording.md), [implementation plan](voucher-implementation-plan.md),
[tracker](voucher-delivery-tracker.md) and [todo](voucher-implementation-todo.md).

The [account recording design](voucher-account-recording-design.md) details how daily/period
movements and derived prefix balances are maintained across FY changes. BAL checks extend
the existing FY/RPT evidence for late entries, generation rebuilds and opening-once behavior.

## 1. TallyPrime expectations and our boundary

TallyPrime documents continuing in the same company by changing the current period, with
balances continuing and original financial-year/books-begin settings retained. It also
describes creating a new company or splitting data as alternatives. Our existing architecture
uses continuous years in one company; changing the selected year will not copy transactions,
masters, outstanding bills or stock. [TallyPrime new-year guidance](https://help.tallysolutions.com/moving-to-the-next-financial-year-india-change-current-period/).

Tally also supports dated numbering-series configuration and restarting sequences. We retain
issued identities and cancellation history; our append-only model does not adopt renumbering
or reusing deleted/unused issued numbers. [TallyPrime numbering methods](https://help.tallysolutions.com/use-voucher-numbering-methods/),
[registration/series configuration](https://help.tallysolutions.com/set-up-vch-numbering-and-numbering-series-for-gst/).

These are functional references, not claims about Tally's internal storage or a blanket
compatibility promise. In particular, outstanding unpaid bills need not become zero to start
a new year. Source reconciliation and valid carry-forward evidence are required instead.

## 2. Inspected implementation and corrections to older notes

| Existing source | Implemented evidence | Required integration / correction |
|---|---|---|
| [Fiscal models](../apis/accounting/src/accounting/models/fiscal.py) | Financial setup, company fiscal years, periods and period transition history | `FiscalYear` currently has dates/code, not `status` or `is_current`; report aggregate year state from periods rather than pretending those fields exist |
| [Calendar/transition domain](../apis/accounting/src/accounting/domain/fiscal.py) | Twelve contiguous monthly spans; short-month anchor clamping; permitted OPEN/SOFT_CLOSED/CLOSED transitions | CLOSED and SOFT_CLOSED can already reopen with `period.reopen`; LOCKED has no outgoing transition |
| [Fiscal commands](../apis/accounting/src/accounting/tasks/fiscal.py) | Idempotent generation, overlap rejection, initially FUTURE periods, expected-version transitions and company-lock serialization | Generating a year does not open its periods; no implemented annual scheduler or automatic UI-year switch is established |
| [Shared posting guard](../libs/platform/src/billing_platform/posting.py) | Company/books date, period status, permissions, timezone and backdate limit | Execute again at owner commit; report selection, stale previews and date edits cannot bypass it |
| [Close checks](../apis/accounting/src/accounting/tasks/reconciliation.py) | Pending openings/charges, failed delivery/confirmation checks and party-control reconciliation; fiscal commands also check draft/prepared journals | Extend to actual Vouchers/stock/tax producer scope; this is not already a complete distributed year-end checklist |
| [Journal models](../apis/accounting/src/accounting/models/ledger.py), [number allocation](../apis/accounting/src/accounting/tasks/journal_posting.py) | Period FK and counter per company/year/journal kind; internal number includes kind/year code | Current internal journal number is not automatically a GST invoice number; configured type/registration/statutory series need additive contracts |
| [Open-item models](../apis/accounting/src/accounting/models/subledger.py), [opening workflow](../apis/accounting/src/accounting/tasks/openings.py) | Stable items, source dates, due dates, dated allocations and once-only entered openings | Carry those identities across years; no annual copy/opening journal for already recorded history |

RF25-RF32 record the resulting planning corrections. Existing monthly controls remain the
baseline. D12 makes multi-service readiness/numbering/date/transition contracts explicit;
it does not reopen settled company isolation, common tables or payroll exclusion.

## 3. Company calendar, books start and selected period

Accounting owns fiscal-year/period rows derived from Identity's company calendar. Tenant,
department, warehouse, GST registration and a user's browser timezone cannot each invent a
different company fiscal calendar. India April-March examples do not hardcode that anchor
for every company. Native company calendar/books settings retain their existing immutability;
changing a UI year is never an edit to those settings.

Distinguish:

| Concept | Meaning |
|---|---|
| Company fiscal anchor | Configured start month/day used to generate actual date spans |
| `books_begin_date` | Earliest supported accounting posting date / migration cutover, set once under the current setup contract |
| Fiscal year/period IDs | Authoritative company-scoped generated spans; numeric/calendar labels alone are insufficient |
| Selected/current year | Per-user company-scoped navigation/filter default; proposed preference, not posting authority |
| Working/entry date | An explicit form default evaluated in company timezone; operator confirms actual document/posting dates |
| Statutory financial year / return period | Derived by the relevant jurisdiction/profile; can differ from a company's management calendar |

Generation creates twelve contiguous nonoverlapping monthly periods from the configured
anchor. Existing short-month/leap clamping must be preserved and tested; do not implement
another client calendar algorithm. Dates before books begin remain unpostable even if their
year exists. Missing periods fail with an actionable readiness error, never an implicit year
creation during posting. Multiple years may have OPEN periods concurrently.

The UI fetches the company's calendar and capabilities, provides year/period selectors and
shows derived target dates/years on preview. Separate tabs/users may select different years.
An entry outside the selected display year shows its actual resolved year and requires an
explicit date choice; the server resolves it independently. Changes to dates invalidate the
old calculation/approval as applicable. Midnight does not rewrite a saved draft or change
an already approved operation's year.

## 4. Dates and year association on each effect

| Field / relationship | Governs |
|---|---|
| Document/issue date | Commercial evidence, document-year presentation and the applicable document-series rule |
| Accounting `posting_date` -> `fiscal_period_id` -> `fiscal_year_id` | GL inclusion, postability and internal posting-number year |
| Stock effective/physical date and stock period | Quantity/custody/valuation scope under D03, with explicit GL-date linkage |
| Invoice/supply/payment/tax-event date and statutory period | Tax recognition/return/numbering rules under the enabled profile |
| Allocation/reversal/clearing date | Outstanding bills, advances and instrument history at the requested cutoff |
| Credit-terms effective/basis date and derived due schedule | Supported due-date/aging/interest basis only; never an implicit replacement for posting, stock or statutory dates |
| Recorded/committed time and source snapshot | Audit order and what a frozen report knew |

The [all-voucher configuration contract](voucher-configuration-design.md) resolves and captures these date purposes
separately. Tally's credit-terms effective-date option cannot move every effect to that date.
Accepted terms/basis/due dates stay with the original bill across configuration/year changes;
VCF07 supplements the financial-year acceptance checks.

Journal period linkage already exists. Derive the accounting year through it; if additional
year IDs are denormalized for indexing, enforce date/period/year consistency. Vouchers keeps
resolved local projection/source references with revision/hash evidence, not cross-service
foreign keys. Never trust a client-supplied year ID without comparing the authoritative date.

One document can reference effects in different years: a March order, March dispatch, April
invoice and May receipt. Keep effect-specific references instead of forcing every record into
the header's selected year. Non-posting orders, quotes and memos have document-year filters
without acquiring a fake journal/GL period. Company/source IDs, not display voucher numbers,
join cross-year records.

A March invoice arriving in April may post to March if its period/authority/backdate rules
permit. Otherwise the requested March post fails. An authorized explicitly dated April
adjustment or a permitted Accounting reopen is a separate choice, with original invoice/tax
evidence preserved. Never silently move a rejected posting into April or change its legal
invoice date to make the operation pass. Stock/date mismatches need the approved recognition
profile; they are not resolved by blindly copying the GL date.

## 5. Numbering, identity and fiscal-year resets

Three identities may coexist: internal Accounting posting number, issuer's statutory document
number, and external supplier/bank reference. Each keeps its own date basis and uniqueness
scope. The internal `{kind}/{year.code}/{counter}` format is an audit reference; it can exceed
a legal document length and must not be reused as an invoice number without validation.

Accounting remains the sole allocator for actual posted voucher/statutory numbers under D05;
Vouchers allocates its separate issue-time order/quote/challan series. Where posting and legal
document dates differ, Accounting returns both internal and statutory identities with their
respective year/series keys. This is an additive command/result and schema extension, not
two allocators racing for the same number. Preserve old journal numbers and readers.

Required number assignment fields: issuer/company/registration, document category and
series/rule revision, reset-period key and its date basis, assigned full number and canonical
uniqueness representation, source revision/operation, assignment time, status, cancellation/
void reason and original assignment link. Proposed native policy/assignment detail may extend
`document_sequence` or use Accounting-owned supporting structures reviewed under D05/D07.
Vouchers' issue series/counter/assignment remain reusable across kinds; no table per year/type.

Rules:

- Reset a counter in a new namespace/period; never reset the old year's row or rename its
  assigned numbers. New April posting and permitted late March posting use their own counters.
- Reserve/assign in the owner transaction or its contracted durable issue lifecycle. Retries
  after rollover return the original receipt/number, not a new year's number. Partial failure
  cannot recycle a committed assignment. Draft IDs are not issued document numbers.
- Final posting year comes from the accepted posting date; statutory numbering year comes
  from its legal document/date rule. Human prefix text cannot define either year.
- A company-created voucher type must not bypass uniqueness by starting another identical
  series. Legal uniqueness includes the actual issuer/registration, document category and
  statutory year/full number required by the profile, not only our custom type ID.
- Supplier invoice number/date remain external evidence. Duplicate checks use the proper
  supplier/registration/document/year scope; our purchase journal number does not replace them.
- No arbitrary renumbering after issue, date change on posted content, or reuse after
  cancellation. Imported historical issued numbers are validated/preserved through a
  distinct adoption contract; import is not permission to advance/reset live counters unsafely.

For India GST invoices, the official portal specifies a maximum of 16 characters with allowed
alphanumeric/dash/slash characters and supports multiple series. Validate the enabled rule's
complete number, not just its numeric suffix. [GST Portal invoice/series FAQ](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm).
The authorized IRP documentation bases the IRN financial year on invoice date and identifies
April-March as that year; GL posting-year selection cannot replace it.
[IRP invoice identity](https://einvoice6.gst.gov.in/content/irn-2/).
Version legal normalization/uniqueness checks and reverify on statutory activation. Automatic
number generation is our product control, not a claim that the law mandates one UI method.
Cancellation/void registers explain assigned numbers rather than deleting gaps from history.

## 6. What continues into the next year

Continuity is a read over existing facts, not another financial transaction. At source snapshot
W, closing through prior-year end equals next-year opening before its first movement. Either
read full history or a verified carry cache plus only subsequent movements, never both.

| Area | Required carry behaviour |
|---|---|
| Bank/cash, assets, liabilities and posted equity | Continue balances with original transaction drill-down; no new opening journal each April |
| Income/expenses | New-year P&L includes the new year's eligible activity; prior unclosed nominal profit/loss remains in the Balance Sheet earnings bridge |
| Retained earnings | A future tagged closing transfer moves profit to equity once; reports do not add that profit a second time |
| Customer/supplier bills, advances, deposits and credit notes | Same open-item/source IDs, original bill/due dates, currency and role; new-year settlements allocate against old-year items |
| Bank instruments / opening BRS | Keep instruction, book, clearance and reconciliation dates independently; rollover does not repost cash |
| Inventory | Same lots/units/positions/origins/cost layers and value; expiry/age continues with time, not a new receipt on April 1 |
| Transit / goods at worker / WIP / third-party custody | Same dispatch, owner/custodian, unresolved quantity and genealogy; no fresh challan age or duplicate asset |
| Orders, quotes, challans, unbilled receipts/dispatches and reservations | Original commitments/schedules/expiry and source links persist; new-year execution records its own dates/effects |
| GST/VAT and tax credits/liabilities | Same registration/event/credit/settlement evidence; return cutoffs and amendments remain separate from GL year change |

An outstanding report filtered by settlement date must still find older originating bills.
An order backlog filtered by current due date must still include prior-year orders. Do not
add an unconditional `origin_year = selected_year` filter to such queries. Display origin
and execution/settlement years separately. Cross-year credits/returns link original costs
and tax evidence and post only their supported new effects.

First migration is different: entered openings use the existing once-only opening workflow,
with bill and stock detail reconciled and available-history/YTD coverage stated. Resetting
books begin each year or importing last year's closing balances into the same continuous
company would double history and is prohibited. Missing older detail is unknown coverage,
not evidence of zero transactions. Source migration identities remain stable across years.

## 7. New-year readiness, closing and reopening

**Start next year:** generate/verify its actual periods; validate numbering/profile configuration
and necessary reference-data versions; open the intended periods with `period.manage`; check
opening/continuity reports and unresolved source exceptions; allow the user to select the new
year. The old year need not be closed first. A future scheduler may request generation with
service authority and durable evidence, but must not silently open/close periods or change
another user's selection. The current generator creates FUTURE periods and no financial effect.

**Close the old period/year:** provide an authorized readiness review and execute the existing
period transitions in permitted order. A year summary is derived from its periods, including
mixed states; it is not a second posting gate. A multi-period close is a resumable operation
with each actual transition recorded, not a fictitious cross-service atomic year transaction.

| Check | Completion/evidence rule |
|---|---|
| Draft/prepared financial commands, openings and charges | Resolve, cancel or explicitly redate through ordinary validation; current owner checks remain in force |
| Unknown execution / posted-but-unacknowledged operations | Recover against owner source receipts; include committed effects, never infer success/failure from Vouchers status |
| GL and bill/advance/currency reconciliation | Complete at the period cutoff; explain mismatches, never add a balancing plug |
| Inventory, cost, transit, count and WIP scope | Reconcile quantity/value/GL and pending execution under D03; open orders or legitimate transit are carried, not forcibly zeroed |
| Tax events and return evidence | Reconcile statutory dates, pending credit/RCM and return versions under selected profiles; filing does not automatically lock every GL period |
| Outbox/authority confirmations and producer readiness | Preserve implemented guards; add versioned producer evidence and exact blockers instead of assuming all remote drafts are already visible |
| Required adjustments / review / backups | Record supported adjustment references and review evidence; a required unsupported capability cannot be marked complete by a checklist |
| Optional bank/FX/other automation | Required only for selected scope; no hidden dependency on unselected integrations |

Readiness is not permission to close. No remote API/network call occurs inside the posting
transaction. D12 specifies local close fences/epochs and producer snapshot evidence; final
transition rechecks authoritative state under the same company lock as posting. Missing or
stale required evidence blocks completion. A delayed old-period command arriving after close
fails the guard even if a draft or approval previously passed. Ordinary non-posting orders/
quotations spanning years are not treated as unposted financial journals.

**Reopen:** Accounting already permits SOFT_CLOSED/CLOSED -> OPEN with `period.reopen`, reason,
expected version and audit. It does not delete the previous close evidence. LOCKED is terminal.
Reports cannot invoke a reopen through report permissions. Reopening earlier history marks
dependent opening/valuation/report caches stale for new runs and triggers the supported
reconciliation path; already frozen outputs remain unchanged. Do not automatically reopen
later CLOSED/LOCKED periods or assume stock revaluation is available merely because GL reopened.

An authorized current-period linked correction is the alternative when an earlier period
remains closed/locked and the profile supports that treatment. A legal tax amendment remains
separate; neither branch silently edits issued sources. The UI displays why a period is
unpostable and what authorized actions are available, rather than silently changing the date.

**Annual earnings transfer:** generating automated close journals is still deferred. Required
statements/new-year operation use the continuous-history earnings bridge today in the plan.
If selected later, the automated transfer needs an explicit supported journal classification,
retained-earnings mapping, source uniqueness, reconciliation and reversal/restatement policy;
ordinary adjustments such as accrued expenses must not be confused with that transfer.

## 8. Shared records, APIs and reports

Reuse `financial_setup`, `fiscal_year`, `fiscal_period`, `fiscal_status_transition`, journal
period/source references, existing openings and shared document/numbering/effect tables.
There is no `voucher_2027`, separate ledger database per financial year, annual party copy or
stock-reset table. User selection can be a scoped preference; it cannot mutate calendar facts.

D07/D12 may add reusable `fiscal_review_run` / `fiscal_review_item` or equivalent common-operation
detail for review scope, period versions/fences, actor/authority, producer manifests, blocker
evidence, transition outcomes and report-run references. These are candidates outside baseline
counts, not balances or another year-status authority. A derived carry cache, if introduced,
records cutoff/source/hash/generation and invalidation, not a posting amount to add twice.

Planned company-scoped APIs provide generated years/periods, date-resolution preview, explicit
generate/transition commands, source-backed readiness and reconciliation, and resume/status
for multi-period reviews. Reuse existing Accounting routes and permission keys where possible;
do not expose a generic `reset year` or balance-overwrite endpoint. Voucher APIs carry dates
and resolved effect references; generated clients and forms display both document and posting
years when different. Native fiscal fields are not editable custom attributes.

Required reports include FY-filtered voucher/day book, ledgers/TB, P&L/Income & Expense and
Balance Sheet, opening-to-prior-closing bridge, cross-year bill/advance/stock continuity,
number assignment/cancellation register and fiscal transition/readiness history. A comparison
pins exact periods, history coverage and source/classification/rule versions. A newly reopened
prior year can change a new comparison, never an already frozen report. Report flags identify
partial years, unclosed earnings, incomplete cost/tax inputs and revalidation needs.

## 9. Batch integration and acceptance

Keep the 45 parent batches, 38 work packages and existing B14/B27 sub-batches. Add **D12** for
company-calendar/date association, new-year readiness, cross-year numbering and close/reopen
coordination. Initial contracts are B02/B03; implementation gates apply to each dependent slice.

| Existing batch | Required financial-year scope |
|---|---|
| B01-B03 | Audit current fiscal/numbering/settlement contracts; resolve D12 date/identity/continuity and closure evidence alongside D01/D05/D11 |
| B07/B08 | Commit-time fiscal revalidation, immutable retry identity, split internal/statutory number date bases and explicit selected-year UI defaults |
| B10/B11/B13 | Reuse fiscal generate/transition controls; implement current profile readiness and cross-year bill/advance/receipt/payment allocation |
| B09/B14a-d | Period/source manifests, close/reopen invalidation, multi-year statements and carry bridges without duplicate opening or profit |
| B16-B19 | Fiscal versus statutory year/date, supplier originals, invoice/notes/advances, numbering and return evidence |
| B21-B27 | GL/stock period coordination, preserved stock origins/costs/custody and year-boundary reporting |
| B30-B32 | Orders, open challans, unmatched bills/movements and selected reservations continue without resetting demand |
| B38-B41 | Cross-year job-work age, WIP/genealogy, processing bills and statutory evidence |
| B45 | Two-year setup/post/close/reopen/retry/report rehearsal and recovery/permission evidence for every enabled profile |

FY checks expand existing AC05/AC07/AC08/AC15/AC17/AC18/AC23/AC25/AC26/AC28 and the RPT/INV
matrices; they are future implementation tests, not results inferred from this document.

| Check | Required assertion | Evidence batch |
|---|---|---|
| FY01 | Company-scoped twelve-period generation is idempotent, contiguous and nonoverlapping for April/January and leap/short-month anchors | B01/B10 |
| FY02 | Books begin, calendar settings and selected user year have distinct semantics; another company/tab cannot alter the target period | B03/B08/B10 |
| FY03 | Posting date resolves exactly one company period; client year mismatch, missing/FUTURE period and pre-books dates fail | B07/B10 |
| FY04 | March/April may be open together; backdate limit and company timezone are enforced at commit | B07/B10 |
| FY05 | Internal journal, statutory issue and supplier-reference identities have correct independent year/registration/date scopes | B08/B19 |
| FY06 | Reset creates a new counter namespace; concurrent April and late March posts do not collide or mutate old numbers | B08/B10 |
| FY07 | Retry/unknown result over midnight/year change returns one original effect/number; changed dates require a new authorized revision | B07/B08/B45 |
| FY08 | Custom types/imports cannot bypass legal number uniqueness/format or recycle issued/cancelled assignments | B06/B08/B19 |
| FY09 | Period-close races and stale approvals cannot post after close; producer evidence/fences cover actual financial and stock scopes | B07/B10/B21/B45 |
| FY10 | Permitted reopen requires reason/version/authority; LOCKED remains terminal; period transition order is preserved | B10/B45 |
| FY11 | Late prior-year adjustment invalidates dependent new-run carry/report caches without overwriting frozen outputs | B14/B27/B45 |
| FY12 | New-year opening equals prior closing at the same snapshot; full history plus carry cache never double counts | B14c/B27e |
| FY13 | New-year P&L excludes previous activity while Balance Sheet retains prior unclosed profit/loss; tagged future close transfer counts once | B14b/c |
| FY14 | First/mid-year migration is distinct from annual continuation; YTD and unavailable historical detail are explicit | B14c/B27e |
| FY15 | New-year receipt/payment/advance adjustment settles an old bill using the same IDs and due dates; prior as-of outstanding remains unchanged | B11/B13/B14d |
| FY16 | Cross-year cheque/clearing/BRS retains book versus bank dates and never reposts opening cash | B12/B14d; B43 if selected |
| FY17 | Stock lots/units, cost/origin layers, transit and expiry carry without annual opening or age reset | B23/B27c-e |
| FY18 | March movement/April invoice and cross-year returns/credits preserve source slices, stock cost and separate tax evidence | B24/B25/B32 |
| FY19 | Orders/challans/reservations retain due dates/claims; new-year backlog includes older sources without duplicate commitments | B30-B32 |
| FY20 | Job-work original dispatch age, custody/WIP and tax evidence continue across year-end | B40/B41 |
| FY21 | Tax-event/return/statutory FY stays distinct from GL FY; fiscal reopen cannot unfile or silently amend a frozen tax return | B16-B19/B40 |
| FY22 | Readiness does not require old bills/orders/transit to be zero; real pending commands, mismatches and unknown effects block appropriately | B10/B14/B27/B45 |
| FY23 | FY filters, comparison totals, exports and close diagnostics enforce company/field/location scope and stable run versions | All report batches |
| FY24 | Interrupted generation/multi-period transition, replay and recovery record partial outcomes; no automatic reopen, profit transfer or data split | B10/B45 |

### Worked two-year fixture

Illustrative April-March company and INR fixtures, with valid profiles and periods explicitly
opened. FY2026-27 starts with Bank Dr 20,000 / Capital Cr 20,000. A service invoice on
2027-03-31 posts Customer Dr 11,800 / Revenue Cr 10,000 / Output tax Cr 1,800. Receive and
allocate 3,000 on March 31. Closing Bank is 23,000, Customer 8,800; assets/TB debit total
31,800 equals Capital 20,000 + Revenue 10,000 + Output tax 1,800.

On 2027-04-01, no opening journal is posted. Those balances are the opening facts. New-year
P&L starts at zero activity; prior unclosed earnings of 10,000 remain in the Balance Sheet.
On April 2 receive 4,000 against the same bill: Bank becomes 27,000, Customer 4,800. March
31 outstanding remains 8,800 at its original snapshot. The receipt creates no second sale/tax.

If an authorized later March adjustment records Expense Dr 500 / Bank Cr 500, a new March
run has Bank 22,500, Customer 8,800, assets 31,300 and profit 9,500; April opening follows
that revised source snapshot. After the April receipt, Bank is 26,500 and Customer 4,800.
The frozen original March run remains 31,800. CLOSED requires an explicit permitted reopen;
LOCKED does not allow this March posting. An alternative current-period correction must be
explicitly dated and uses its own accounting/tax treatment.

Separately, a March 31 stock fixture of 30 units/value 300 continues unchanged into April 1
without another opening movement; lot expiry/age and original receipt dates continue normally.
This separate stock example is not added to the service-only financial fixture above.

## Decision log

- 2026-10-10: User required company financial-year behaviour based on TallyPrime review.
  Added D12 and FY01-FY24 within existing batches; continuous-year setup, effect-specific
  dates, separate internal/statutory numbering, cross-year bills/stock/earnings and close/
  reopen/report contracts. Corrected stale Tally split-only wording and distinguished
  already implemented period reopening from deferred annual-profit-transfer automation.
  No periods, numbers, balances, application code or company settings were changed.

### Account-recording review - 2026-10-10

Linked account summary/prefix generation and rebuild rules to the existing cross-year
contract. No change to normal year readiness or deferred profit-transfer automation.

### All-voucher configuration review - 2026-10-10

Separated configured credit-terms effective dates from GL/stock/statutory dates and retained
original due schedules across policy/year changes. VCF07 extends existing D12/FY validation.

### Selected-year preference, first implementation - 2026-10-21

The console implements the §3 "selected/current year" as a **display and filter preference
only**, exactly as proposed: a per-browser cookie carrying `<companyId>.<fiscalYearId>`, read
back only for the company actually open, and resolved as cookie -> the year containing today
(in the company's timezone) -> the latest year with an OPEN period -> the earliest year that
exists. It never reaches a `posting_date`, never writes a calendar fact, and the rail's
selector is absent for an actor without `period.read`. No year-status or "current year" flag
was added to any table, and company calendar/books-start settings are untouched. Generating a
year still does not open its periods; the creation wizard opens every period from the
books-begin period to the year end explicitly, through the existing `period.manage`
transition, and says so (2026-11-03, [company-setup](company-setup.md) decision log).

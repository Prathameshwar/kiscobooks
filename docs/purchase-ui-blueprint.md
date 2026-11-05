# Purchase UI blueprint

Date: 2026-10-31. Baseline: **P1 design**, with P2/P3 implementation decisions below.
Status and the confirmation boundary live in [purchase-ui-todo.md](purchase-ui-todo.md).

The user selected a professional, polished Purchase experience, delivered in five
UI phases with review/fixes and explicit confirmation between phases. Actual API
integration, financial execution and print readiness follow separately.

## 1. Governing contracts and present baseline

Read [CLAUDE.md](../CLAUDE.md), [design system](design-system.md),
[invoice calculation](voucher-invoice-calculation.md),
[commercial configuration](voucher-commercial-configuration.md),
[shared data model](voucher-data-model.md),
[native configuration](voucher-configuration-design.md),
[tax evidence](voucher-tax-recording.md) and
[financial dates](voucher-financial-year-design.md). These continue to govern.
This document chooses presentation and interaction; it does not resolve an open
posting, statutory, costing, numbering or source-claim decision.

The current `/vouchers/new/purchase` renders `VoucherEntry` and `PurchaseInvoice`:
manual type/date/field loading and an untaxed expense-account bill. Its supported
save/preview/acceptance path is real, while goods/mixed invoice posting remains
gated. The new review surface will use synthetic fixtures; it must not route its
unsupported sample bills into that live save path. Its route is a P2 implementation
choice within the existing authenticated ConsoleShell, not a new service.

Reuse shared `EntryGrid`, `AmountField`, `QuantityField`, `SearchSelect`, overlay,
form and file controls. Reuse the visual grammar of Sales entry, not Sales-specific
customer, promotion or tax business rules. Common mechanisms belong in `@janso/ui`;
Purchase screens/state belong in the console. Styles remain centralized and use
existing tokens. No copied Sales pricing/tax engine or new service/table is authorized.

## 2. Visual direction and page hierarchy

The workspace should feel like a carefully typeset bill: quiet surfaces, a clear
reading order, ruled columns, tabular figures, short labels and a single strong
primary action. Use existing Inter typography, modest corner radii, indigo action
colour and existing semantic status colours. Avoid decorative dashboards and
oversized cards that reduce the number of visible lines.

| Region | Contents and behavior |
|---|---|
| Company shell | Existing company/year context remains visible; collapsible navigation, theme and account controls |
| Page heading | Purchases breadcrumb; New purchase/Edit purchase/Review purchase; human-readable status |
| Compact document strip | Supplier identity, supplier invoice reference/date and posting date; stays available as the grid scrolls |
| Main column | Mode selector; line grid; short details sections with counts/completion summaries |
| Summary rail | Provisional amount breakdown, supplier total comparison and settlement intent |
| Action bar | Current save state, Review bill, and the single primary save action appropriate to this surface |

On a 1440px desktop, reserve approximately 300px for the totals rail and let the
grid use the remaining width. The compact strip, grid headings and action bar
must not overlap the shell or hide a focused field. At tablet widths move totals
below the grid and keep a compact total/action strip. On narrow mobile screens
use one column and labelled line cards with a full-screen line editor; retain the
same values, full product/pack descriptions, validation and row order. Keep
company, financial year and currency visible in compact form. Use at least 44px
touch targets for primary mobile actions. Never shrink a desktop grid into unreadable
text or create page-wide horizontal scrolling. A desktop grid may scroll within
its own region, retaining row identity. CSS breakpoints are implemented and tested
in P2/P5 rather than treated as fixed business requirements here.

Static compositions: [desktop light](testing/purchase-ui/desktop-light.svg),
[desktop dark](testing/purchase-ui/desktop-dark.svg),
[desktop ledger](testing/purchase-ui/desktop-ledger.svg),
[mobile light](testing/purchase-ui/mobile-light.svg).
These are design references, not interactive or accessibility-tested screens.
Rendered PNGs, reproduction commands and the static check evidence are in the
[artifact index](testing/purchase-ui/README.md).

## 3. Fields and interaction contract

| Area | Always visible when applicable | Progressive detail / behavior |
|---|---|---|
| Supplier | Search by permitted name/code; selected identity and location | Registration/address and account details; show permitted balance only with as-of evidence; no made-up balance. **Live page:** one figure under the field, read once when a supplier is chosen ([PUI-D05](#10-decision-and-review-log)) |
| Payable account | **Never shown or asked for** ([PUI-D06](#10-decision-and-review-log)): choosing the supplier chooses its one payable account | A supplier with none or several cannot be billed; the Supplier field says so (repair is Accounting's, not a picker on the bill) |
| Invoice identity | Supplier invoice number and supplier invoice date | Internal reference shown separately as Unassigned until a supported allocator assigns it; no invented draft number |
| Dates | Posting date; supplier invoice date | Document date and service/supply dates when applicable; terms basis and due date are explicit; posting date alone selects the GL period |
| Type/class | Sensible permitted default, concise type label | Selector only when useful; changes explain policy impacts rather than clearing the bill |
| Supplier evidence | Supplier bill total, optional unless policy requires | Calculated total, signed difference, evidence/reason and supported resolution; no automatic balancing adjustment |
| Notes/evidence | Notes and attachment count | Reference/attachment panel; custom fields come from the field-set and never drive money |

Configuration loads automatically. Show skeleton/empty/error/retry states rather
than Load fields buttons. Preserve input during refresh. Resolve types and fields
against company/date/class with version evidence. UI preview uses a typed fixture
policy with separate availability, requiredness, default, editability, override
permission/reason and approval threshold. That fixture shape is not a published API.

Supplier changes retain lines, but mark dependent registration, payable, pricing,
terms, source receipts and tax results for review. Responses from a previous
supplier/company/request must be discarded. Date/type changes preserve values and
explain newly invalid fields. Mode changes cannot silently turn an item into an
expense or delete quantity/tax/source details; incompatible rows remain flagged
until explicitly resolved, with cancel/back and undo for destructive actions.

## 4. Line entry

| Mode | Default visible columns | Row details |
|---|---|---|
| Items | Product/description, receipt quantity, billed quantity, unit, rate, discount, net amount | Read-only tax breakdown; warehouse/bin/batch/expiry/serials; purchase account; price/source evidence; explicit quantity-difference purpose |
| Accounts/Services | Account/service, description, amount, tax summary, line total | Classification and service dates; allocation and override evidence; quantity/rate only when the chosen service requires it |
| Mixed | Explicit row kind; appropriate item or account cells in one grid | Same detail panels and totals; no dummy product for an expense |

Receipt quantity is an entry proposal, not evidence of an already posted receipt.
For reference/deferred profiles label it to match that intent. Keep billed quantity
distinct, including manual paid-bundle quantities. Unknown or zero rate does not
mean free: supported zero-consideration lines need a typed purpose and appropriate
tax/cost evidence. The user-facing Net amount is the pre-tax commercial line amount
after line discounts; invoice charges/tax appear separately in the rail.

Start with one empty row. Add a new row from the final editable cell, Ctrl+Enter or
Add line. Enter/Shift+Enter move between rows in the same column; Tab/Shift+Tab
follow normal cell order. Search popovers own Enter/Escape while open; Enter must
not accidentally submit. Use the existing EntryGrid keyboard model. Label icon
actions, show shortcuts in help, restore focus after row deletion/panel close,
and avoid shortcuts that override text editing or browser navigation.

Numeric input uses string-backed shared controls. Preserve invalid text with a
local error; do not round/truncate during typing. Display uses company amount and
quantity precision, separators, currency and date rules. Optional advanced columns
are shown according to policy/user view; read-denied information never enters the
view, tooltips, summaries or accessible labels. Every editable value has a label.

## 5. Purchase detail panels

| Panel | User task | Required distinction |
|---|---|---|
| Discounts & charges | Enter line/selected-line/document discounts and freight/packing/other supported charges | Purpose, basis, targets and dependencies are explicit; supplier payable, taxable allocation and landed cost are separate views of one component |
| Tax details | Review configured jurisdiction, registration, classifications and component evidence | Resolved rates are read-only; supplier-charged tax and recipient liability are separate; RCM is never inferred from India alone |
| Goods receipt | Choose receive-with-bill, reference an existing receipt, or pending receipt when the profile permits | Existing receipt matching cannot receive again; show source, remaining quantity and selected partial slice; planned/deferred quantities are not on-hand |
| Line tracking | Capture required location, batch/expiry/serial facts | Match item policy and entered quantities; missing detail leads back to the affected line |
| Payment & terms | Set credit terms, select eligible advances and prepare payment details | A proposed advance/payment is not recognized/cleared money; show requested values and projected remaining balance separately |
| Supplier bill | Compare declared figures and attach source evidence | Preserve original supplier values; tax/total differences require supported resolution rather than silent edits |
| Notes & attachments | Add notes, permitted custom fields and supporting files | P3 local selection/preview only; secure owner upload/download is a later integration |

Panels show completion summaries on the main screen. Open one editing panel at a
time. Apply validates and returns focus; Cancel restores the prior panel snapshot;
closing dirty panels asks whether to discard. Long panels scroll internally while
keeping their title/actions reachable. On mobile use a full-screen panel. Receipt
and advance choices remain company/supplier/currency scoped even in fixtures.

Attachment design includes selectable file, type/size rejection, pending/error,
remove and preview states. Local preview does not say Uploaded. Never execute
attached HTML/SVG/scripts as page content; revoke temporary object URLs on removal.
Secure scanning, storage, signed URLs and access evidence remain later API work.

## 6. Totals and honest state

Rail order: line amounts, line discounts, document discounts, supplier charges,
taxable/non-taxable breakdown, supplier-charged tax components, rounding, **Bill
total**, supplier-declared total and difference. An expandable component explanation
retains source/basis. Non-supplier charges/capitalization do not increase this bill
twice. Recipient RCM liability is displayed separately and does not automatically
increase the supplier bill total.

Then show advances to apply, payment to record and **Remaining if applied**. These
are intentions in UI fixtures; only later owner results can be called Applied,
Paid or Cleared. A bill total never becomes the net-after-advance amount.

All UI-stage figures are labelled Provisional. Do not copy the Sales preview engine
and treat it as purchase/tax authority. Start with supplied example breakdowns;
P2/P3 must use a bounded presentation adapter for supported edits, reuse an existing
shared exact mechanism where applicable, and show Calculation unavailable for any
recipe it cannot explain. Actual accepted calculation and digest remain Accounting's.

| State | Visible behavior |
|---|---|
| Fixture editing | Persistent Sample purchase / UI preview notice; no claim of persistence; Review bill and Save demo draft actions |
| Simulated save | Explicit Demo draft only result; leave guard still explains data is not persisted; no real posting/issue/print action |
| Validation errors | Inline message plus linked summary; focus first blocking field/row; distinguish warning from error |
| Submitted/approved fixture | Read-only content and allowed simulated transitions; edits cannot silently modify the accepted revision |
| Rejected fixture | Rejection reason, clear Correct purchase action into a new editable fixture revision, re-review required |
| Stale/refused fixture | Keep input; explain conflict/refusal with review/reload options; never silently overwrite |
| Uncertain save fixture | Freeze the command inputs; retry the same body/key; do not create a second bill |
| Read-only/denied | No editable controls or leaking denied costs; explain unavailable capabilities where useful |

P4 demonstrates these states through an injected in-memory adapter. It does not
repair or certify backend workflow behavior. The existing live account-bill path
continues to use truthful persisted states under its current contract.

## 7. Representative examples and acceptance matrix

[examples.json](testing/purchase-ui/examples.json) supplies deterministic synthetic
examples. Rates/taxes are display fixtures, not legal determinations. Amounts and
quantities are strings; the verifier checks arithmetic consistency, not tax law.
The examples call the commercial base `pre_supplier_tax_total`; an untaxed
expense is not labelled a taxable supply merely because it has a positive amount.

| ID | Example | What the UI must make clear |
|---|---|---|
| PU01 | Untaxed account expense | No stock fields or dummy quantity; payable equals bill total |
| PU02 | Two goods lines with discount, freight, tax and an advance | Visible net lines, separate freight/tax, bill total versus projected remaining |
| PU03 | Mixed goods and service | Both row kinds retain correct fields and one coherent total |
| PU04 | Partial match against an existing receipt | Source balance and selected billed slice; no second receipt |
| PU05 | 11 received / 10 billed | Typed paid-bundle purpose; quantity difference does not change billed price |
| PU06 | Supplier total mismatch | Signed difference and blocking review; no unapproved adjustment |
| PU07 | Suspected duplicate supplier bill | Existing-reference review and explicit check outcome; UI does not invent duplicate policy |
| PU08 | Recipient-tax service example | Supplier payable excludes recipient liability; no immediate ITC claim |
| PU09 | Advance plus proposed payment | Full bill total retained; remaining cannot go below zero |

Additional state fixtures to build with the corresponding phases: empty/new;
supplier/account missing; multiple payables; slow lookup and stale response;
restricted purchase cost; missing required tracking; existing source over-claim;
incompatible mode change; unsupported configured tax; rejected correction;
failed/refused/stale/uncertain save; read-only approval; unsaved navigation;
1/50/200 lines; non-English number/date display; mobile and 200% zoom.

## 8. Phase gates and evidence

P1 delivers this blueprint, static compositions, examples, todo and review record.
P2 implements only the core interactive fixture workspace; P3 implements detail
panels; P4 implements lifecycle/recovery; P5 completes the full quality matrix.
Each phase includes its own visual, usability, simplification, correctness and
security review plus fixes before asking for the next phase's confirmation.

P2-P5 require unit tests for new pages/components and conditional branches,
validation/pending/success/failure/accessibility, pure state transitions and shared
mechanisms; affected existing Purchase/Sales/shared suites must remain green.
Browser review supplements those tests. Record browser, viewport, theme, fixture,
actual result and remaining limitation. Never mark UI ready from screenshot
inspection alone or use UI readiness to close C2/C3/backend milestones.

Final acceptance: keyboard-only completion, sensible mobile editing, all three
themes, 200% zoom without lost controls, company formatting, 200-line behavior,
honest state/amount labels, no silent data loss, complete scenario coverage and
no unresolved blocking review findings. Measure performance on the actual build
and machine before making a speed claim.

## 9. Deferred owner decisions and integration backlog

The effective Purchase API shape, duplicate identity rule, statutory tax/date
profiles, direct/deferred receipt execution, cost/clearing/landed-cost contracts,
recognition of advances/payment, real rejected-document correction and immutable
print evidence remain their governing owner decisions. Fixtures can demonstrate
presentation choices; they cannot resolve these policies. When integration depends
on an unresolved choice, ask then, while continuing independent UI work.

No new permission key, statutory number, tax default, persistent local storage,
API request, financial activation or print template is introduced by this blueprint.

## 10. Decision and review log

2026-10-31, PUI-D01: user selected UI-first delivery with phase review/fixes and
confirmation before each next phase. P1 is the blueprint; P2-P5 remain pending.

2026-10-31, PUI-D02: use one Purchase workspace with mode-aware rows and progressive
detail panels. Reuse shared entry/numeric/style mechanisms; keep Purchase policy
distinct from Sales business rules. Desktop plus mobile compositions are design
references; they are not proof of implementation or accessibility.

2026-10-31, PUI-D03: use explicit synthetic fixtures for the new UI review surface.
Provisional totals and planned settlement stay visibly distinct from owner facts.
Keep supplier invoice identity separate from internal numbering. No live save
path for unsupported goods/tax fixture profiles is added by these phases.

2026-10-31, PUI-D04: P1 review preserves full pack/product labels on mobile, keeps
company/year/currency context, uses explicit Save demo draft wording and separates
pre-tax commercial totals from legal taxable classification. These clarify the
existing UI-first boundary and do not select financial policy.

2026-11-02, PUI-D05: the live Purchase page shows the chosen supplier's balance as one
figure under the Supplier field, marked Cr or Dr with "To pay" or "To receive" (Settled at
nil). It is read once, when a supplier is chosen or changed, from Accounting's existing
`GET /ledger/balance` (base currency, the supplier's verified payable accounts, as of the
posting date at that moment) and is labelled with that date and "before this bill". It is
advice only: never saved, sent back or used in a calculation. It is read in the background,
outside the page's busy guard, so nothing waits for it; a newer choice or leaving the page
cancels it, and a refused, failed, slow (15 s) or unprovable answer shows "Not available"
and leaves the bill alone. It needs `ledger.read` (held by `purchase_clerk`) and is not
requested without it. It is hidden once the bill is posting or posted, because the ledger
then includes the bill. The Console proxy gains one GET-only rule for `/ledger/balance`. A
bill reopened from a saved draft shows none (no choice was made); no backend change.
Open: bill-wise ageing/overdue beside it, and the same line on Sales.

2026-11-02, PUI-D06: the Purchase bill has no supplier-payable-account control, value or hint
anywhere (live card, preview card, generic account-purchase form). Every party role has exactly
one account ([party-ledger-mandatory-plan](party-ledger-mandatory-plan.md)), so choosing the
supplier chooses it; the page reads it with one `GET /accounts?kind=PARTY&party_id=…&role=SUPPLIER`
(so a party that is also a customer is never billed to its receivable) and verifies it. A
supplier with none, or with several (older data), cannot be billed and the Supplier field says
why, naming the party ledger repair. The Sales bill follows the same rule for the customer's
receivable (`role=CUSTOMER`; exactly one, never "the first").

P1 review results and fixed findings are recorded in the companion todo.

2026-10-31, PUI-D05: the user authorized P2. The authenticated review route is
`/vouchers/new/purchase-preview`, inside the existing ConsoleShell and company/year
context. It requires company-scoped `vouchers.read` or `vouchers.create`; only
creators can edit. The existing live account-purchase route keeps its service
contract. The new workspace makes no service request and stores nothing locally.

2026-10-31, PUI-D06: P2 uses the shared exact-decimal primitives to calculate line
bases, line discounts and net commercial amounts. Supplied example freight/tax
is usable only while its calculation inputs match. Financial edits invalidate
that evidence; equivalent decimal spellings and row reordering do not. Missing
evidence produces an unavailable bill total. The preview never infers GST rates
from the sample. Fixture money stays explicitly INR even for a differently
configured company, while company separators/date formats remain in effect.

2026-10-31, PUI-D07: P2 browser evidence renders the actual React workspace in a
local isolated component harness. It is not an authenticated end-to-end service
test. Route access, cross-company denial and read-only behavior have unit tests.
The richer purchase detail editors and lifecycle/recovery states remain P3/P4;
the full accessibility/scale gate remains P5.

2026-10-31, PUI-D08: the user authorized P3. Six progressive detail cards open
transactional shared drawers: Apply validates and commits panel changes; dirty
Cancel/Escape requires an explicit discard choice and restores the opening bill.
Fixture panel availability/writability controls presentation, not server authority.
Typed descriptive custom fields reuse the shared field-set renderer/validator and
never affect financial calculations. All amounts use exact decimal strings/BigInt.

2026-10-31, PUI-D09: extend P2's immutable supplied evidence to a bounded synthetic
tax recipe. Core supplier/date/quantity/rate/line-discount edits still invalidate it.
Document component edits may reuse the supplied rates: ordered discounts reduce
eligible line nets, then charges use their selected discounted line base. Percentage
components/taxes round to two places in these explicit INR examples; discount
allocation uses the shared four-place largest-remainder mechanism. This is not the
complete owner calculation graph, statutory resolution or accepted calculation.
Unresolved/unsupported treatment keeps tax and bill total unavailable. Supplier
charges/tax enter the supplier bill once; recipient liability and additional costs
remain separate. Overflow beyond DECIMAL(19,4) never produces a usable bill total.

2026-10-31, PUI-D10: receipt intent distinguishes direct, existing-reference and
deferred receipt. Existing references match billed slices in the same supplier,
currency, item and unit and share an aggregate supplied residual; they create no
second receipt. Required location/batch/expiry/serial fields apply to directly
received tracked items. Inactive reference/tracking inputs are retained. Terms,
advances and payment instructions project a remainder without changing the full
bill or implying settlement. Supplier comparison retains the original declared
total; a supported matching supplier revision requires both original and reason.
No arbitrary balancing adjustment is offered.

2026-10-31, PUI-D11: supporting files stay in browser memory. Reuse shared FileUpload
with a distinct selected status, labelled Selected locally. Validate count, size,
extension/MIME and basic file signature; provide local raster image preview, explicit
decode failure, retry/removal and object-URL cleanup. PDFs show guidance/metadata,
not embedded active content. This is not malware scanning, upload or secure storage.
Async checks cannot reintroduce files after panel discard. Full document upload,
protected download and any PDF preview service remain the later integration stage.

P3 evidence and review fixes are in the [delivery ledger](purchase-ui-todo.md) and
[interactive review artifacts](testing/purchase-ui/README.md).

2026-10-31, PUI-D12: the user authorized P4. The authenticated preview now uses
one controlled Purchase draft for new/edit/resume/read-only states. A company/year
key remounts the entire session, adapter, local files and draft selections. Existing
company-scoped create/edit/submit grants control available actions. Submitted and
approved examples are frozen; approval is only a fixture status. Rejection requires
a correction reason and creates a separate draft with original ID/revision lineage.
Submission reviews the exact saved draft; changed inputs must first be saved.
Missing supplied calculation evidence permits a draft, but never submission.

2026-10-31, PUI-D13: a scoped, injected memory adapter models revision conflicts,
validation refusal, known failure, permission refusal and uncertain completion.
Reuse the existing service-command hook for synchronous duplicate protection and
same-body/same-key retries. No service reader/client is invoked. The adapter caches
one effect per command key, verifies scope/revision/transition, and never overwrites
a newer revision. Unconfirmed responses freeze edits and context changes until
recovery. Result verification precedes visible replacement; responses from an
unmounted prior-company/year session are ignored. Stale reads allow keeping inputs,
copying them to a separate new demo, or explicitly confirming replacement.

2026-10-31, PUI-D14: preserve saved supplier/item/receipt labels and compare them
with current masters. Unchanged selections keep their snapshots; changed supplier
or source selections receive new snapshots. Saved labels appear in the selected
controls and submission review. Tab records and immutable File references remain
in memory only. Leaving/reloading loses them, even after a demo save; leave guards
therefore remain active until explicit disposal. No draft content is written to
localStorage, sessionStorage, IndexedDB or any service.

2026-10-31, PUI-D15: compose the existing company-change/beforeunload guard with
same-tab anchor capture and cancellable browser Navigation API events. Preserve
Next/browser history without synthetic entries or internal state mutation. Dirty
departure requires an explicit choice; pending/unconfirmed commands and open/raw
invalid editors must first be resolved. Cancellable same-document Back is verified
in Edge. Native beforeunload remains the fallback for reload and other supported
document departures. Browser traversal cancellation is not universal: see the
[WHATWG navigate-event contract](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-navigate-event).
Cross-browser behavior, browser-restored pages, full keyboard/screen-reader matrix,
zoom, locale and large documents remain P5 checks, not an unconditional navigation
guarantee.

[P4 browser evidence](testing/purchase-ui/phase4/review.json) and review fixes are
recorded in the delivery ledger. P5 final usability/accessibility/scale and the
separately authorized API/end-to-end/attachment-transport/print stages remain pending.

2026-10-31, PUI-D16: the user authorized P5. Compact entry now uses labelled
native line lists and a staged full-screen editor; desktop retains EntryGrid.
Keep the invalid numeric grid mounted across resize and require an explicit card
switch after correction. Keep line type fixed while a numeric buffer is invalid.
One reducer and decimal representation serve both compositions. Add a sticky
invoice/line-count strip, aligned compact actions and collapsed example controls.

2026-10-31, PUI-D17: P5 adds bounded mixed/bundle/mismatch examples, supplied
duplicate-candidate presentation, an injected delayed supplier lookup and a
supplied cost-read-denial state. None resolves production duplicate policy or
field authorization. Duplicate results apply only to their supplier/invoice
snapshot; changed identity does not become a successful duplicate check.

2026-10-31, PUI-D18: fix shared overlay keyboard scrolling and empty lookup
landmarks after failing regressions; remove unsupported generic ARIA labels.
Memoize resolved formatting so an invoice-text edit does not broadcast to every
numeric cell. The [P5 readiness report](purchase-ui-readiness.md) records the
34-case visual/axe review, Edge/Chrome keyboard/navigation checks, 1/50/200-line
measurements, build limitation and remaining native assistive-technology/zoom
acceptance. P1-P5 are complete within their synthetic UI scope. User confirmation
is required before Purchase API/effective-policy integration or print work.

2026-10-31, PUI-D19: the user authorized all remaining phases except API integration
and print. P6 closes remaining independent UI gaps and verification without
another inter-phase confirmation. Server persistence, effective authorization,
authoritative calculation, financial E2E and secure file transport remain part of
the excluded API work. Preview state is never a published service payload.

2026-10-31, PUI-D20: desktop Net amount follows the blueprint's discounted pre-tax
definition and agrees with mobile cards. Account bases remain editable. Invalid
numeric text suppresses its derived net amount until corrected. Native 400% zoom
revealed collapsed dialog content: short Purchase sheets now scroll as one unit.
WebKit exposed partial focused fields beneath pinned actions; the shared overlay
reveals the full field after native focus scrolling, while ignoring portalled
controls outside its body. Regression and actual-browser checks cover both fixes.

2026-10-31, PUI-D21: expand verification to Firefox/WebKit viewport profiles,
actual Chromium zoom, browser accessibility trees and the full Next production
build. Physical Safari/iOS and human NVDA/VoiceOver acceptance are external release
checks; engine emulation and automated trees are labelled accordingly. P6's
readiness report and ledger supersede earlier pending zoom/browser/build notes.

2026-10-31, PUI-D22: the live `/vouchers/new/purchase` page is redesigned as one page column with
a header, a single-column bill, a terms-and-tax card, a calculation card shown only when Accounting
has calculated, and a status-and-approval card with a progress track. The right-hand totals rail,
the "Connected to company APIs" badge, the raw ID lookup row and the one-option tax select are
removed or moved. The synthetic preview route keeps its layout. See
[purchase-page-redesign.md](purchase-page-redesign.md).

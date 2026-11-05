# Phase 3 execution — invoices and India tax

Status: **IN_PROGRESS**. B15–B19 authorized on 2026-10-10. Phase 2 remains
verified; C0–C4 activation checkpoints remain pending. This record tracks implementation,
not production tax compliance or release approval.

## Delivery and ownership

| Batch | Implementation and acceptance | Status |
|---|---|---|
| B15 | Accounting owns the canonical bounded invoice calculator; shared typed wire contracts, Vouchers revision details/preview, Catalog published scheme evidence. CAL01–04/07/15 and applicable CAL18–22/27. | IN_PROGRESS |
| B16 | Accounting owns immutable supply/tax components, legal dates and credit/advance/RCM effects. Retain legacy tax request semantics. CAL05–08/13 and applicable CAL20/21/23. | IN_PROGRESS |
| B17 | Extend the existing durable execution protocol for account/service invoices and source-linked financial notes, settlements and guarded return entitlements. Goods execution remains Phase 4. | IN_PROGRESS |
| B18 | Extend committed owner facts and Reports with invoice/tax grains, timing bridges and frozen outputs; recheck financial statements. | IN_PROGRESS |
| B19 | Statutory identity, immutable document/evidence and recovery/issuance controls, with matching clients and operational documentation. | PLANNED |

## Decision slices and boundaries

- Reuse Accounting's journal, open-item, allocation, bank, posting reservation and reporting
  transaction. No Sales/Purchase-specific document or ledger families; no network calls in
  a money transaction. Common component relations retain native references and scopes.
- Accounting owns invoice calculation. Shared clients contain wire schemas, not an alternate
  executable invoice engine. Preview and execution call the same implementation.
- B15 calculation bounds: 200 supply lines, 200 commercial components, 200 targets per
  component, 32 explicitly named dependencies per component and 4,000 total allocations.
  These are technical payload/fan-out limits, not company financial approval limits.
- Company/type/class policies restrict manual/free/deal and component capabilities. No new
  approval amount or supplier-difference tolerance is inferred: deviations require an
  explicitly configured supported policy. Custom attributes cannot change calculations.
- India GST is the selected first jurisdiction. No VAT state/commodity, provider, live
  taxpayer applicability or company tax rates are selected implicitly. Applicable supported
  profiles and statutory sources will be recorded with implementation and tests.
- Old Accounting tax requests continue resolving by posting date. New invoice contracts
  identify their date-resolution version; GL period selection remains posting-date based.
- The 2026-10-11 voucher checkpoint was committed and published through the folder
  mapping. This is source publication only; no deployment, release activation or
  real-company migration is included in the Phase 3 work.

## Verification baseline

Phase 2 artifacts are the pre-change baseline: Accounting combined coverage 95.14% overall /
99.60% domain; Vouchers 90.96% / 96.79%; Reports 90.71% / 93.26%; platform 97.97%.
Console: 328 tests, 97.66% lines/statements and 85.33% branches. Source fingerprints and
coverage snapshots are captured under `.test_artifacts/voucher-phase3-baseline.json` before
Phase 3 application edits. The Phase 2 execution note retains its original full-run failures
and successful focused corrections; this phase must not relabel that original run as green.

## Statutory research

Official sources consulted during implementation (recheck applicability at activation):

- [CGST section 16](https://taxinformation.cbic.gov.in/content-page/explore-act/1000285/1000001):
  input credit requires evidence and conditions beyond recording a purchase.
- [CGST section 31](https://taxinformation.cbic.gov.in/content-page/explore-act/1000300/1000001/invoice/ACTS):
  statutory documents and service invoicing facts have their own timing requirements.
- [CBIC circular 92/11/2019](https://cbic-gst.gov.in/pdf/circular-cgst-92.pdf):
  paid promotional bundles and independent gifts/samples require different treatment.
- [Authorized IRP reporting advisory](https://einvoice6.gst.gov.in/content/revised-time-limit-for-e-invoice-reporting-for-businesses-with-aato-of-%E2%82%B910-crores-above/):
  reporting-window applicability is distinct from e-invoice applicability itself.
- [GST Portal GSTR-1 guide](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm):
  taxable service advances and later invoice adjustments are separately reported; the
  advance event and invoice cannot each contribute the same output tax twice.
- [CBIC Central Tax notification index, 66/2017](https://cbic-gst.gov.in/hindi/central-tax-notifications.html):
  the goods-advance payment exemption is a separate rule, not a generic receipt behavior.

## Progress and evidence

Initial repository/plan review completed. The common calculator and same-item deal domain
have 51 passing focused tests, including the published purchase/sales examples, exact
precision bounds, cycles/fan-out, mixed rates, separate allocation purposes and explicit
inclusive-price rounding. This is domain evidence only: API/source publication, native
persistence and posting remain in progress. No Phase 3 batch is verified yet.

Catalog promotion definitions currently have typed P0 validation but no published promotion
tables/APIs. B15 automatic scheme availability therefore requires the applicable Catalog
publication/projection slice; manually supplied rule facts are not trusted API evidence.

Initial B15 Vouchers migration manifest (one CREATE per revision): 0041 common invoice
detail; 0042 common supply detail; 0043 supply quantity; 0044 charge detail; 0045 charge
target membership; 0046 charge dependency. All relation keys include tenant/company/revision.
Supplies reuse ITEM lines or create ACCOUNT lines, and components use CHARGE lines. Existing
account/tender/bill-instruction tables retain settlement capture; no per-kind table is added.
0047 adds the explicitly accepted Accounting calculation hash with one atomic ALTER. A
changed calculation requires a new accepted revision; user-supplied totals are not authority.

Early capture verification: 40 focused Vouchers tests passed; 14 selected tests passed on
native MySQL, with 46-revision upgrade/model-index-FK parity and downgrade/upgrade. This
predates 0047 and the preview HTTP adapter, which still require their own verification.
Accounting domain/contract/date plus existing money-contract slice: 71 tests passed.
Platform exact amount/rate slice: 50 tests passed. These are overlapping focused results,
not a phase-completion or coverage-floor claim.

Rate precision review found that the shared eight-decimal exchange-rate wire used the
four-decimal amount validator. Regression tests demonstrated both lost accepted precision
and an excessive integer range. `billing-platform` 0.31.0 adds an exact DECIMAL(19,8)
mechanism; `voucher-execution-client` 0.3.0 uses it and adds invoice contracts.
`identity-posting-client` 0.2.3 corrects its compatible platform range; all consumer lockfiles
are refreshed. Amount/quantity storage remains DECIMAL(19,4), while component percentages
have their own DECIMAL(19,8) column. No stored Phase 2 voucher or historical hash is rewritten.

The owner-preview adapter now resolves explicitly untaxed and ordinary domestic-service GST
calculations from authoritative account defaults and published tax replicas. Each supply can
override the header with its own complete tax context. Company precision is translated into
the calculator's rounding vocabulary, and each statutory component retains published rounding.
Free/deal profiles still fail closed until their authoritative resolution is connected.
The service-date domain covers ordinary service invoicing, supplier-invoiced RCM and the
six section-14 transition cases for one consideration slice. It is not yet an enabled tax
posting workflow. Recipient self-invoice RCM and special deadlines require separate dated
profiles; partial advances must use allocated source slices, never one payment date for an
entire invoice. [CGST section 14](https://taxinformation.cbic.gov.in/content-page/explore-act/1000283/1000001)
and [CBIC invoice rules](https://cbic-gst.gov.in/gst-invoice-rules.html) support the date design.

Vouchers 0048 stores explicit line tax contexts with a revision/supply composite foreign key.
Native MySQL verified all 48 revisions, model/index parity and downgrade/upgrade; six selected
capture/isolation tests passed. The overlapping SQLite capture/isolation slice passed 32 tests.
The service-tax/preview/calculator slice passed 39 tests, including intra/inter-state service
GST after discounts, line overrides, late service invoice dates, supplier-invoiced RCM,
pending/ineligible credit evidence and rejection of ambiguous whole-invoice payment dates.

Accounting 0121–0126 add shared immutable invoice records, supply facts, commercial components,
allocation facts, tax components and source-to-journal-line links. The DDL has been manually
reviewed; native model/index parity and five selected invoice tests passed. Native journal
amounts remain the GL authority. The original full-chain downgrade stopped at legacy 0093,
which correctly rejects newer tax-purpose fixture data. The harness now recreates only its
validated disposable database before structural downgrade/upgrade; no production guard is
relaxed. The rerun passed five tests and the complete 126-revision structural round trip.
Invoices retain gross open items and create separate settlement legs and allocations, so a
900 invoice with 300 cash retains the original 900 bill and 600 outstanding. The first posting
test passed on native MySQL after its balance assertions were corrected to use this owner's
native amount/allocation model. Ordinary-money regression slice: 45 passed.

`ACCOUNTING_VOUCHER_INVOICE_ENABLED` defaults false independently of ordinary-money activation.
The owner integration verifies untaxed account/service Sales/Purchase. Mapped GST posting is
being tested; its initial three fixtures exposed a transport normalization mismatch in the
default decimal tolerance. The fixed wire serializer now emits the same four-decimal value
before/after transport. The rerun passed 31 tests: three full GST postings (Sales, eligible
RCM Purchase and ineligible RCM Purchase), eight contract checks and twenty credit-domain
checks. RCM Purchase credits the liability, debits pending tax or the ineligible expense,
and leaves the supplier bill at its commercial amount. It creates no eligible ITC balance.
Native verification of 0127–0128 plus existing mapping regressions passed, including the
128-revision structural round trip. Tax event coverage, source-linked
notes and statutory issuance remain incomplete. The public Vouchers post producer has not yet
been widened to invoice kinds. No Phase 3 batch is verified and C2 remains pending.

The next native migrations, 0127–0128, add an `INPUT_PENDING` account purpose and five
component-specific `PENDING_*` posting mappings. These keep recorded recoverable purchase
tax separate from the existing eligible-input accounts. Their native validation passed.
The initial amount-level ITC domain passed 20 tests for partial verification/claim, blocked
credit, statutory-year deadlines, payment reversals/reclaims and prior RCM cash discharge.
The initial domain evidence predates the native action API below. [CBIC circular 237/31/2024](https://cbic-gst.gov.in/pdf/circular-237-31-2024-GST.pdf)
and [RCM scrutiny guidance](https://cbic-gst.gov.in/pdf/02-2022-GST-DATED-22032022.pdf)
are retained as official evidence. Exceptional historical relief requires a separate profile.

Resumed on 2026-10-11. The interrupted mapping/group regression run completed with nine
passing tests. The accepted calculation now binds supply group/head identities and versions,
dated tax mapping identities/versions, tax-account versions and tax-profile versions.
Execution consumes those resolved mappings. Read denies cover the contributing group fields.

0129–0131 add immutable common credit instructions/events and a `TAX_ACTION` journal kind;
each migration has one DDL statement per direction and has been read manually. Native
verification of this head passed: ten selected invoice/credit/read tests and the complete
131-revision structural downgrade/upgrade round trip. The action API uses the existing company
fence, idempotency receipts and journal/Identity reservation workflow. Verification alone
does not move balances. Claim, payment reversal/reclaim and blocked-credit instructions
produce balanced reclassification journals; committed histories are appended only with
the journal posting. RCM discharge requires a posted cash/bank-funded statutory deposit,
retained cash-offset evidence, remaining deposit capacity and the liability tax date.
Consumed deposits cannot be reversed independently. Ordinary reversal of credit-action
journals is blocked; source-linked statutory corrections remain part of the pending work.

Three focused API tests passed for partial claims, retry/stale-history protection, evidence
and field permissions, exact amount validation, blocked credit and an RCM deposit/offset/
verification flow. The native run includes competing credit claims and all eight new-table
tenant/company isolation checks. Two read/isolation tests also passed separately. The invoice
facts have native field-policy resources and sparse read schemas; bounded invoice/register
and child-fact endpoints are covered by those checks.
Frozen source proof is masked under contributing Accounting read denies, including exports.

Remaining Phase 3 work includes published Catalog deal resolution, partial advance and
withholding events, original-component financial notes/returns and settlement correction
dependencies, complete tax evidence/exception and annual-return ownership, Reports grains/
registers/bridges, statutory documents, clients/UI, coverage and final review. The new
manual evidence actions do not assert external GST portal verification. Public invoice
admission and C2 remain disabled/pending; no Phase 3 batch is verified.

Separate tax allocation now has explicit target membership and a value/compatible-quantity
basis, independent of commercial and stock-cost distributions. Its policy defaults disabled
and restrictive inheritance applies. Omitted controls preserve the commercial distribution;
gross adjustments reject independent tax redistribution. Vouchers 0049 adds a nullable native
basis and 0050 extends common target purposes; both one-statement migrations were manually
reviewed. Native verification passed six capture tests and the 50-revision structural round
trip/model parity. The wire library is 0.3.1 and both consumer locks and
environments are refreshed. Domain/contract/return-allocation slice: 74 passed. The 17 return
tests cover original-component caps and final residuals; native note claims remain pending.

Decision record (2026-10-11): separate tax value weights use retained net supply bases plus
the explicitly named component dependencies. No display-order or invoice-total dependency
is inferred. A separate quantity allocation uses the component's declared compatible unit
and quantity basis. This is calculator/capture capability, not authority to override a
statutory profile's eligible targets or tax treatment.

Reporting extension is now in progress. `reporting-contract` 0.3.0 exports eight native
invoice/credit grains through the existing committed feed. Its schema hash changes: Reports
requires a fresh generation from the new owner snapshot; old frozen report artifacts remain
immutable and must not be relabelled with the new schema. Both consumer locks/environments
are updated. No cross-service ORM reads or second tax-calculation engine are introduced.

Accounting 0132 adds nullable tax-component/purpose lineage to common invoice journal links,
using one atomic ALTER and a tenant/company/invoice foreign key. The DDL was reviewed manually.
The first flow run exposed insertion ordering against that new foreign key; flushing native
tax rows before their links fixed it. The rerun passed two end-to-end forward-charge/RCM
report flows plus 17 return-domain tests (19 total). The earlier broader run retained five
failures from that insertion-order bug; the native 0132 rerun passed 12 selected tests and
the complete 132-revision model/FK/index/downgrade/upgrade check.

New Reports definitions cover Sales/Purchase, components/allocations, tax, input credit,
settlements and invoice/tax GL bridges. Document totals and purpose allocations remain
separate grains. Tax-component GL entries link to their exact source; credit histories use
only committed owner events and retain event/posting dates. Date selection is explicit and
constrained per report. Credit positions and settlement histories are as-of outputs; the
settlement report includes earlier applications to show the complete position. Current
coverage is labelled `NATIVE_VOUCHER_INVOICES`, not all legacy external invoice sources.

Focused Reports verification initially passed 12 tests and the existing financial-report
slice passed 34. Review added a reproducing test for a balanced GL whose original party bill
disagrees with invoice payable; the missing check is fixed. The native Reports rerun passed
the full regression suite, model/index parity and 16-revision downgrade/upgrade. It checks
source-grain immutability and frozen CSV disclosure.
The Console consumes the allowed date choices from native field metadata; nine UI tests
passed. Accounting/Vouchers/Reports OpenAPI and generated TypeScript contracts are refreshed.

B18 remains incomplete until notes/returns, advance/withholding tax events and benefit
facts are available and included in the same reconciliation. B15-B19 remain unverified;
no issuance or company activation is enabled by these reporting changes.

The later B15 Catalog slice adds a scoped stored-fact reader for the bounded same-item
mechanic. It rebuilds typed deal terms from the dormant revision, benefit, SKU, price
level and stack rows, and rejects missing or inconsistent parts. This is publication
input validation only: no complete release, acknowledgement or Accounting projection
exists, so automatic schemes remain unavailable in voucher execution.

The B17 public command producer now admits approved, accepted-hash Sales/Purchase
account/service invoices behind `VOUCHERS_INVOICE_EXECUTION_ENABLED`, default false,
separate from the ordinary-money switch. It rejects common item/stock lines and unsupported
invoice kinds before enqueue; the Accounting owner still recomputes and compares the
accepted calculation before committing. The full native Vouchers regression (133 passed,
one skipped), 50-revision model/index parity and structural downgrade/upgrade passed.
The capability response and Console posting control use the separate invoice flag; voucher
detail includes the captured kind/profile so a masked invoice cannot be treated as ordinary
money for reversal. The Console draft
workflow previews an Accounting result, shows its totals and records the selected hash through
a dedicated server-side revision command. That command preserves stored fields the client
cannot read, checks the current version/configuration and requires invoice-input read plus
voucher edit access. The Accounting owner recomputes the hash before any monetary commit;
recording it alone is not financial acceptance. Seven focused Vouchers invoice tests and
Console 331 tests/TypeScript typecheck passed. Invoice reversal and tax-bearing or
stock-bearing financial notes remain disabled until source-linked component and statutory
correction guards are implemented.

Until B19 has a statutory profile, the generic B08 issue series cannot issue a captured
Sales/Purchase/Note invoice. It creates only non-statutory artifact numbers; financial
posting from an approved revision remains a separate owner-controlled action. The Console
therefore hides generic issue for captured invoices. This is a temporary protective gate,
not a completed statutory issuance flow.

The Reports reconciler now checks each tax component's expected native GL posting purposes,
including pending input, nonrecoverable and RCM legs. A valid signed snapshot with a wrong
tax purpose fails reconciliation. Both cross-service forward-charge/RCM cases passed on
native Accounting MySQL and the Reports native suite passed 76 tests,
one skipped, with its 16-revision structural round trip. This is report integrity for the
supported source profile, not completion of the pending tax/notes/advance scope.

The next B17 slice retains a nullable original-invoice ID in the common invoice detail,
Accounting's immutable invoice record and the signed Reporting wire. `voucher-execution-client`
0.3.2 and `reporting-contract` 0.3.1 preserve old absent-source wire content while carrying
source-linked notes; Accounting/Vouchers/Reports consumer locks and generated API types were
refreshed. Vouchers 0051 and Accounting 0133 each use one atomic ALTER, with the model and
read schema updated at the same time. The Accounting invoice record enforces a scoped
self-reference and a kind/source consistency check; native fixture cleanup deletes notes
before their original invoices.

The deliberately narrow executable note profile is an untaxed, accounts/service-only
Credit Note against a committed Sales invoice or Debit Note against a committed Purchase
invoice. It requires the same company, party, currency, source supply identity and account;
its posting date cannot precede the original. The owner locks the original, counts other
prepared and committed note claims, and rejects amounts above each original supply residual.
Each note supply retains the original account and account/service supply kind; changing
the kind while reusing the source line identity is rejected before financial posting.
The current execution is excluded from its own claim count. A note may offset only its
original native party bill and may settle an additional amount through a cash/bank tender;
both together cannot exceed the note payable. Supplier and customer debt/credit directions
are tested separately. Source or note tax, original components, note rounding, free/gift
lines and stock lines are refused in this profile. Tax-bearing notes, original component
benefit correction, other-source refund workflows and goods returns remain B16/B17/B24/B25 work;
this profile must not be treated as statutory issuance.

The native unit flow posts an original Sales invoice, two Credit Notes consuming its full
untaxed supply entitlement and rejects a further claim. The first note offsets part of the
original bill and refunds the rest in one transaction; an unrelated bill target is rejected.
A Purchase invoice and Debit Note verify supplier-party settlement direction. The tests
check idempotent replay, immutable source references and signed Accounting-to-Reports
snapshots: Sales and Purchase registers show original and reduction directions, settlement
history retains both allocations, and reconciliation checks source relation, tax and
component absence and claim caps. Seven selected Accounting native tests passed with the
133-revision structural downgrade/upgrade. The complete Vouchers native suite passed
135 tests, one skip, and the 51-revision model/index/FK and downgrade/upgrade check;
Reports' native 16-revision suite passed 77 tests with one skip and a structural
downgrade/upgrade after this extension. Console 331 tests, API-client
8 tests, generated-client check and TypeScript checks passed. At that checkpoint the
full-suite coverage gates and Phase 3 acceptance matrix were open; no Phase 3 batch was
marked verified.

The earlier whole-service coverage runs passed their tests but missed the repository's 90%
gate: Vouchers 89.51% (132 passed, two skipped) and Reports 85.35% (76 passed, one skipped).
Those measurements predate the note tests and are not claimed as current coverage. The
Accounting whole-service coverage run was stopped after prolonged progress at 10%; its
result is unverified, while the selected native Accounting tests above passed. Coverage
was required before B15-B19 verification. Later Vouchers and Reports runs met their gates;
Accounting whole-service coverage and the complete acceptance matrix remain open.

Settlement review exposed a prior invoice mapping error: supplier open-item debt/credit
direction is based on the party's payable exposure, not the GL debit/credit side. The same
rule makes both original Sales and Purchase bills DEBT and both Credit and Debit Notes
CREDIT. The shared invoice allocation builder now follows those roles, with Purchase cash
settlement and both note offset directions covered by tests. The original source bill is
resolved through its retained invoice-to-journal link, not by a caller-provided bill ID.
The supply-kind guard passed on native Accounting with five selected invoice-execution
tests, model/index parity and the 133-revision structural downgrade/upgrade round trip.

The follow-up native Accounting run passed five selected invoice-execution tests and its
133-revision migration/model-parity round trip after the source-bill reversal guard and
over-settlement assertion. Vouchers' whole-service run passed 134 tests (two skipped)
at 90.10% coverage, meeting its 90% gate. Reports added a reconciled component/allocation
and GL-grain fixture plus a balanced IGST fixture: the latter distinguishes the tax-point
date from the journal posting date and checks the exact tax-to-GL link. A source-linked
Credit Note fixture proves reduction direction, lineage and cumulative original-supply
caps. A supplier Purchase fixture proves pending input tax, evidence-only verification,
partial claim, balanced tax reclassification and tax-to-GL lineage. An earlier Reports
whole-service run passed 81 tests (one skipped) at 90.39% coverage, meeting its 90% gate;
native verification passed the same tests and 16-revision downgrade/upgrade. These checks
do not change the B15-B19 incomplete status or the C2 activation gate.

B18 source reconciliation now requires each invoice's party GL line to resolve to exactly
one native open item with matching amount, currency, bill reference, due date and party
exposure direction; the posting link must retain the same reference and due date. This
closes a gap where a signed invoice/GL snapshot could omit its subledger bill while still
entering the invoice register. Reports indexes open items once by native journal line for
bounded reconciliation. The final whole-service Reports run passed 82 tests (one skipped)
at 90.44% coverage; the native 16-revision verifier passed the same tests, model/index
parity and downgrade/upgrade. Seven Accounting owner-to-Reports tests passed against the
actual signed invoice facts. The fixture also rejects a missing open bill and stale due
dates in either the open item or posting link. B18 remains in progress until its dependent
tax/advance/benefit/return and full acceptance scope is available.

The B15 signed Accounting preview now rejects ordinary supplies whose ACTUAL and BILLED
quantities differ or use different units; Vouchers capture applies the same unit guard.
Both owner failures were reproduced before the fix. The six-test native Accounting preview
suite, two focused Vouchers capture cases and lint checks passed after the fix. Vouchers also
requires paid-bundle entries to carry billed units and a positive, disjoint reward quantity;
three invalid shapes were reproduced before that guard, and a valid 10+1 shape is accepted.
The full Vouchers capture file passed 15 tests, and all five Accounting owner execution
tests passed against the new preview guard. This closes the quantity-evidence guard only;
Catalog publication, free/deal evaluation and the other
B15-B19 acceptance cases remain open. No activation status changes.

For the next B15 Catalog dependency, the existing unpublished Catalog revisions 0158/0159
were reconciled with its declared migration head. The two-table negative-stock change was
split into one DDL per revision (0159/0160), and the registered head is now 0160. Catalog's
new CHECK names now match the SQLAlchemy models and stay below MySQL's identifier bound.
Catalog's combined migration/promotion suite passed 34 tests; the live Docker roundtrip was
skipped because Docker is unavailable in this workspace. This is a prerequisite repair,
not a promotion release.

Catalog now has a separate static preflight for the currently supportable automatic same-item
deal profile. It requires a frozen exact SKU target set equal to the reward SKU set, matching
quantity units, a full reward, and an ordered product stack group. The broad Catalog P0
definition schema remains capable of authoring other mechanics; it does not claim that the
bounded Accounting evaluator can execute them. All 31 promotion-contract tests and lint pass.
P1 authoring/publication workflow, protected APIs, complete releases and the Accounting
local projection are still absent, so automatic deal preview/posting stays unavailable.

Catalog promotion storage now has five scoped tables at migrations 0161-0165: stable
promotion identity, immutable same-item revision, typed buy/get benefit, exact SKU targets
and price-level targets. Composite same-company references protect promotion, SKU,
price-level, unit-revision and return-policy ownership. The one-DDL migrations match
the registered SQLAlchemy metadata;
the Catalog migration suite passed (four passed, live Docker test skipped), and targeted
Ruff and mypy checks passed. This is a dormant B15 foundation only. No authoring/publish
route, complete release acknowledgement, Accounting projection, redemption or goods effect
exists, and neither Catalog promotion readiness nor any invoice admission gate changed.

The bounded Accounting deal domain now also derives physical/reward quantities from paid
units without reinterpreting an already partitioned physical line. Native examples prove
9/10/19/20 paid units earn 0/1/1/2 rewards, capped repeats and exact four-place
quantities. Catalog's static stack preflight only grants manual stacking when its
maximum-applied count allows at least two benefits. Accounting's 22 deal tests and
Catalog's 31 promotion tests pass; these functions are still unreachable from posting
until publication, tax and stock authority are implemented.
The subsequent focused Accounting calculator/preview/deal regression group passed
73 tests. The new constraint-parity check raises the combined Catalog promotion/migration
group to 35 passing tests and one live-MySQL skip. With the storage tests, the combined
targeted Catalog group passes 38 tests and skips one live-MySQL case. A whole-Catalog
test run was stopped after reaching 6% because it is a much
larger suite; no whole-service Catalog result or coverage is claimed from that run.
The new storage fixture seeds all five tables for two tenants and confirms each table's
session-level tenant isolation. It also confirms a foreign-tenant SKU cannot be attached
to a promotion revision under the composite native FK. An ORM flush guard also rejects
edits/deletes of revision, benefit and target rows after insertion. All three storage
tests pass; direct database administrative writes are outside this ORM guard.
Catalog's complete source tree passes strict mypy (260 source files) and Ruff. A full
Accounting mypy run exposed a local invoice-preview variable reuse that confused the
quantity and quantity-list types; the names are now distinct. Accounting's complete
source tree passes strict mypy (136 source files) and Ruff, and the 73-test focused
calculator/preview/deal group passes again. Targeted domain coverage is 95% for Catalog's
deal preflight and 94% for Accounting's deal evaluator.

A further B15 storage review found that the ORM immutability guard covered edits and
deletes but allowed a new SKU/price-level target (or benefit) to be appended to an
already published revision. A regression test first failed with a database duplicate
constraint instead of an immutability refusal. The guard now permits child insertion
only for a revision created in the same transaction and clears that allowance on
commit/rollback. The cross-tenant FK test uses a direct SQL insert to verify the
database boundary independently of the ORM guard. All four focused promotion storage
tests pass; targeted Ruff and mypy pass. This is still application-level protection,
not a database prohibition on privileged direct writes. B15 and Phase 3 remain open.

The next B15 storage slice adds Catalog migrations 0166-0168 for immutable stack-policy
revisions, ordered groups and scoped permission pairs, followed by 0169-0170 for
same-company policy/group foreign keys on promotion revisions. The existing promotion revision
now names a native policy/group identity for the eventual protected publication workflow;
publication, release acknowledgement and Accounting projection are still absent. Model and
offline migration parity pass, including one DDL per revision. Promotion/stack storage,
domain and migration tests pass 42 cases; the Docker-gated migration case remains skipped.
The focused loopback MySQL verifier upgraded to 0170, checked promotion table/index/FK
parity and four native isolation/immutability cases, then downgraded to 0131 and re-upgraded
to head in a disposable schema (`cd apis/catalog; uv run python -m
tools.verify_promotion_mysql`). A whole-Catalog metadata comparison is still not green:
unrelated in-progress identifier/barcode, sales-channel and price-assignment changes have
model/migration differences. The focused verifier does not count as whole-Catalog parity.
No automatic promotion profile is enabled and B15 remains IN_PROGRESS.

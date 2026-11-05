# Phase 8 execution contract — B45 production readiness

Status: **PLANNED for verification (preparatory evidence gate implemented)**,
2026-10-11. B45 is the final verification and staged
readiness batch, not a new posting owner. It does not repair missing B15-B44
features by declaring them supported, and it does not itself activate C4.
The authoritative [batch tracker](voucher-delivery-tracker.md) retains B45's
prerequisites and evidence status. This contract details the execution order.

## Scope and entry gates

B45 covers the 22 required non-payroll voucher kinds, the selected India GST
profiles, account and inventory authorities, job work in both directions,
manufacturing, source-linked orders, reports and all selected company policies.
B42 Razorpay, B43 mapped CSV statement reconciliation and B44 cheque-book/cash
denomination controls were selected on 2026-10-11, so **all three are B45
prerequisites**. B31 reservation remains conditional on a positive reservation
selection; an order alone must not silently select it. Recurrence and advanced
BOM expansion/substitution remain outside the selected release.

Begin only preparatory inventories and fixtures while B36, B41, B42-B44 or
their upstream B15-B35 prerequisites remain incomplete. The B45 verification
run starts when each selected producer has native DB/API/client evidence and
an explicit supported-profile manifest. Freeze that manifest for the run:
company and tenant scope, service versions and migration heads, feature flags,
type/class/configuration versions, Catalog policy/BOM releases, Accounting
valuation methods (FIFO and moving average), tax rule versions, Reports
formula/mapping versions and selected optional integration versions. A test
that skips an absent producer cannot count as passing that producer's gate.

## Execution workstreams (one B45 batch)

| Workstream | Concrete work | Required evidence |
|---|---|---|
| 1. Contract and migration inventory | Compare every selected model, migration, OpenAPI route, permission, outbox event, generated client and console/mobile consumer with the manifest. Rehearse migration forward and supported downgrade/forward-repair on disposable native databases; preserve local/remote folder mapping. | No missing native table, column, index, FK, check, permission, client operation or consumer version; one DDL per revision and service-local migration heads. |
| 2. Historical intake and cutover | Dry-run backfill from the declared books-begin date; keep entered openings separate from derived carry, and native source facts separate from report projections. Use chunk identity/checkpoint/resume, row-level reject lists, source counts, control totals and lineage hashes. Compare pre/post snapshots before switching readers. | Repeatable import, interrupted/retried chunk recovery, duplicate-source refusal, no fabricated YTD or opening, exact source-to-owner-to-report counts and balances. |
| 3. Money and tax bridges | Reconcile source voucher revision/effect receipt to Accounting journal, open item, allocation, tax event, bank instrument and Reports fact. Include split tender, advances, bill adjustments, multi-scope sales/purchase charges, discounts, free/deal units, credit/debit returns, GST/ITC/RCM and statutory artifacts. | Debits equal credits; party/open-item and bank totals agree with GL; component/tax/settlement totals agree with issued documents; tax registers and frozen exports carry correct rule/document-year identity. |
| 4. Stock, orders and job work | Reconcile physical positions, unit/lot/serial/origin quantities, FIFO and moving-average value histories, cost of goods, holds/expiry, reservations if selected, demand/fulfillment claims, custody, WIP, multi-output/scrap genealogy and service invoices. Verify owned stock/WIP against GL and exclude third-party goods from assets. | No negative/duplicate tracked quantity under policy, no double movement or capitalization, source-capped partial returns/conversions, stock-to-GL/WIP conservation and cross-year challan/age continuity. |
| 5. Report rebuild and frozen evidence | Rebuild Reports from a committed Accounting/Catalog/Vouchers owner barrier with out-of-order and duplicate delivery; compare fresh generations with owner controls. Reopen a permitted earlier period, append a correction, verify dependent new runs change while previously approved/filed runs and artifacts remain frozen. | Rebuild equivalence, no multiplied joins, permission-safe totals/drill-down, pinned formula/configuration/classification lineage and explicit incomplete-source refusal. |
| 6. Optional banking integrations | For Razorpay, rehearse signed raw-body webhook, checkout signature, captured-status fetch, unknown outcome, duplicate callback/new client key, fee/refund/chargeback and one Accounting effect. For mapped CSV, rehearse duplicate/overlap imports, grouped/partial match/unmatch, opening uncleared items and proposed adjustments. For cheque/cash, rehearse leaf races, void/reprint, post-dated recognition and exact denomination tally. | AC27 complete in native DB/broker and provider test mode; no provider call inside a money transaction, no statement line or print artifact posts money by itself, one owner effect per business source. |
| 7. Fiscal, concurrency and recovery | Use a controlled two-financial-year company with prior-year order, invoice, advance, stock layer, job challan and bank item. Test close/reopen, backdate, late supplier cost/return, credit adjustment, number/issue year versus posting year, fiscal carry, worker crash, broker redelivery, replay and conflicting commands. Exercise account-summary cutover and stock repair/import after failure. | FY01-FY24, BAL01-BAL20 and STK01-STK20 applicable cases pass; guarded failures leave no partial money/stock or duplicated opening; recovery converges to the same owner and report totals. |
| 8. Security, clients and operations | Review company/object/field-level access, report/export inference, key rotation, provider secret handling, webhook replay, file limits/CSV formulas, audit redaction, idempotency and signed artifacts. Verify generated clients and current console/mobile flows. Run supported-volume load, migration timing, report freshness, queues and failure alarms; document runbooks and rollback/forward-repair. | No release-critical findings, supported latency/throughput and bounded queues, accessible client flows, alert ownership, operator recovery rehearsal and signed review record. |

## Combined acceptance fixture

Create two companies in one tenant, a third company in another tenant, and at
least two financial years for the main company. In the main company, issue an
account/service purchase with layered item/invoice tax and
charges; a goods purchase with both FIFO and moving-average item profiles;
a 10+1 sale and partial return; an advance later allocated to a bill; a
quotation/order converted into partial challan and invoice; a principal-to-
worker and worker-to-principal job with direct, onward and partial-return
legs; a manufacturing run with two outputs, scrap and processing charge; a
cheque that clears in the next year; a Razorpay captured receipt, partial
refund and chargeback; and a mapped CSV statement with grouped/partial matches.
Use deliberately duplicated/out-of-order owner events and a failed/restarted
report projection. Assert every source claim, quantity, value, tax, party,
bank, custody and report bridge at the same cutoff. The other companies test
company and tenant isolation, field denies, protected totals and wrong-scope
source IDs.

Keep separate worked fixtures for unsupported cases. They must be rejected
explicitly, never approximated: unsupported tax profile, unready Catalog
release, negative/uncosted stock, multi-level BOM/substitution, incomplete
GST job-work source chain, unverified provider outcome, ambiguous CSV row,
unselected reservation and closed-period mutation.

## Evidence and exit decision

Maintain a matrix keyed by supported profile and case, with an owner, version,
native test/artifact link, result, known limitation and reviewer. Cover
AC01-AC28, applicable RPT01-RPT20, INV01-INV24, FY01-FY24, BAL01-BAL20,
STK01-STK20, CAL01-CAL28, VCF01-VCF24 and T0-T4. A green aggregate test count
cannot replace a missing applicable case. Review the repository's security
and correctness invariants after the last feature phase and record findings,
including none. B45 becomes VERIFIED only when the selected manifest has no
unresolved release-critical mismatch and the combined native fixture,
backfill/rebuild, load, recovery, clients and applicable statutory/provider
evidence pass. Record unsupported profiles as disabled, not partially ready.

The fail-closed evidence check is `apis/vouchers/tools/verify_release.py`. Generate
a pending matrix with `uv run --project apis/vouchers python
apis/vouchers/tools/verify_release.py --template-output <path>` and verify it
with `--manifest <path>`. Its JSON schema requires the selected reservation
policy, frozen tenant/company/year and version/barrier scope, all 22 kinds,
all selected acceptance cases and eight workstreams. Every pass needs an
artifact reference and reviewer; a non-applicable non-AC case needs a reviewer
and reason. The command refuses duplicate/unknown keys and incomplete batch
statuses. This checks evidence completeness; reviewers must still inspect the
artifacts and native results before setting B45 VERIFIED.

C4 is a **separate activation checkpoint** after B45 and C3. Activate one
controlled company/profile set under an explicit versioned manifest, operator,
time, monitoring and rollback/forward-repair instructions. Observe owner
effect counts, unmatched sources, GL/stock/WIP/tax/report discrepancies,
provider unknown outcomes, report lag and failed outbox deliveries before
expanding. Stop/disable a profile on a release-critical divergence; do not
rewrite posted history or overwrite frozen exports. This plan records no
real-company data change, deployment, commit or publication.

## Current status at plan creation

B01-B14 have verified batch evidence. B15-B18 are in progress, B19 and stock/
order/scenario prerequisites remain open, Phase 6 has only preparatory
calculations, and selected B42-B44 have validation/preflight only. B36, B41
and B42-B44 are not VERIFIED, so B45 verification and C4 activation cannot
start. Preparatory fixtures, migration inventory and runbook drafts may be
written now without claiming release readiness.

## Preparatory execution checkpoint — 2026-10-11

The evidence gate and six focused tests are implemented. Ruff and mypy pass,
and the Vouchers regression suite passes 157 tests with two skips. A generated pending
matrix against the authoritative tracker exits 1 and reports 263 missing
gates, including 29 unverified selected prerequisite batches; B31 remains
unselected. No owner artifact or native combined fixture was generated by this
check. B45 verification and C4 activation remain blocked by the open producers.

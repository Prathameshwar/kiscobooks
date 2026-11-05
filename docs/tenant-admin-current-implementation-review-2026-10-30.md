# Current tenant-admin implementation review

Permanent Tenant Administrator opening access and the requested master control
alignment fixes are implemented. The fixed system-role catalogue was applied by
the configured platform operator and preserves existing role/assignment IDs;
fresh provisioning inherits the same grants. Actual opening fields are writable
in all three retained companies. A new auxiliary company completed the wizard,
activation, bootstrap and explicit zero-opening replay without a journal. A
balanced cash/equity worksheet was previewed and discarded. Existing nonzero
balances were not fabricated or overwritten.

Shared filter CSS aligns search, dropdowns, reference inputs and date controls
using central tokens. Evidence includes nine Items viewport cases, 45 other
desktop master destinations, 20 representative responsive cases, four browser
geometry regressions and 27 affected product component cases. The local UI version
advanced to 0.1.37 for this change; concurrent user work subsequently advanced it
to 0.1.38. Geometry evidence does not establish every filter option's semantics.

The independent Purchase account-bill workflow now uses native type/field policy,
supplier role, payable relation and expense head evidence. All nine final live
prerequisite/draft/calculation/acceptance/submission/refusal cases pass across the
three companies. Input 42.1234 remains exact; native payable is 42.1200 for Retail,
42.1234 for Services and 42.0000 for Distribution. Dedicated synthetic expense
defaults are explicitly NON_GST and dated. The first Retail draft's incorrect QA
expense/declared total was corrected through the native revision API. This does
not establish a Purchase edit UI. Initial projection-delay and fixture failures
remain in their ledgers, with final rechecks recorded separately.

Report review reproduced and fixed text submission of integer arrays, text
controls for booleans/counts, and an inventory group filter pointing at Accounting
groups. Native choices now hydrate same-company historical references, use Catalog
item groups/warehouses and Accounting batches, and retain bounded cursor paging.
All 35 focused report cases and TypeScript pass. The 38-definition sweep across
three companies has 219 passes and nine bank-specific parameter prerequisites.
These are labelled control/parameter checks, not populated calculation acceptance.
Actual UI array/boolean requests also reach the owner; current stock report jobs
are correctly refused because the retained financial snapshots lack complete
inventory coverage. Payload checks and source acceptance are separate cases.

The live overview uses immutable scoped source aggregates and real customer
references. Six three-company live cases pass; four API and four native MySQL
cases include nonzero reconciliation and tenant/company/field-deny boundaries.
Its coverage/freshness notices disclose the source cutoff and unavailable earlier
history. Those checks do not establish posted live invoice/collection acceptance.

Native existing-owner verification passed 19 invoice, 19 money and 31 stock cases,
with zero skips, on disposable model-created MySQL schemas. The initial money
close-race fixture had an unfinished opening; completing its zero opening fixed
the fixture without changing or weakening application checks. Initial XML remains.
These suites are not full migration, statutory/count or C1/C2/C3 activation evidence.

Manual simplification and security/correctness review covered native permission
and field policies, tenant/company scope, owner versions, exact decimal handling,
read-only boundaries, pending/uncertain saves, replay/audit, immutable source
aggregation and bounded native references. A further regression tightened report
lookup page/cursor verification. Affected checks and Python Ruff pass. No remaining
defect was identified in these completed slices. The named `/simplify` and
`/security-review` commands are unavailable; equivalent review was performed
directly. User edits were preserved; no direct application database mutation,
financial release activation or publishing was performed in this slice.

Remaining work is explicit in [the TODO](tenant-admin-fixes-todo.md) and
[current CSV](tenant-admin-fixes-after-6-results-2026-10-30.csv): physical count
cutoff/surplus valuation and native execution, country/tax-specific statutory UI
and legal issuance, separate-actor posting/reconciliation and release acceptance,
complete inventory sources, native bank fixtures, actual configured invitation
receipt and provider VM lifecycle. The user selected physical count with calculated
difference and country/tax-driven invoice selection; these instructions are
recorded in their plans. This review does not mark the full #7–18 backlog complete.

The collector retains distinct native suite identities and superseding live
recheck rows. Historical ledgers are unchanged; CSV totals count evidence entries
and can include overlapping assertions from different suite contexts. Reuse
commands and prerequisites are in [the testing README](testing/tenant-admin/README.md).

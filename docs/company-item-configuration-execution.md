# Company and item configuration execution record

**Started:** 2026-10-12. **Authority:** [implementation plan](company-item-configuration-plan.md).
The CI-P identifiers here do not alter the voucher batch or C0-C4 activation states.

## CI-P0 current-state audit

`EXECUTABLE` means the stated narrow behavior has a live owner path; it does not
certify an adjacent feature. `DEFINITION_ONLY` means configuration can be stored or
read without an implemented transaction consumer. `BLOCKED` means a related owner
exists but the required release/projection/acceptance is unfinished.

| Area | Owner and current source | Current state | Required next check or change |
|---|---|---|---|
| Company identity, country/state, currency, fiscal and books-begin | Identity `company`, `CompanyCreate/Update`, first-posting immutability; Accounting fiscal context | EXECUTABLE for existing Accounting journal paths | Add protected setup/readiness explanation; retain first-posting lock and fiscal authority. |
| Dated tax registrations, addresses, licences | Identity native child tables/APIs | EXECUTABLE for supported statutory capture; full item/location tax issue is BLOCKED | Resolve legal tax date and registration/location/item evidence together in CI-P3/P4. |
| Company capabilities and first-use locks | Identity `company_feature`, fixed platform catalogue, posting reservation | EXECUTABLE for existing feature transition/ratchet | Expose readiness without implying a Catalog definition has a stock consumer. |
| Party bill-wise and cash receipt cap | Accounting account/party policy and source-document posting | EXECUTABLE for the covered Accounting paths | Keep a company default as authoring guidance only; test vouchers separately. |
| Product configuration inheritance/adoption | Catalog scoped draft/published revisions and SKU adoption | EXECUTABLE for Catalog authoring/activation | CI-P2 validates every scope and consumer; stock execution remains separate. |
| Item identity, type, group, UOM and exact quantity/price grids | Catalog native item/family/unit/pricing histories | EXECUTABLE for Catalog authoring | CI-P2 exposes an effective source-pinned item view and checks bulk parity. |
| Item tax classification and HSN/SAC directory | Catalog tax histories and lookup API | Lookup EXECUTABLE; issued-stock tax integration BLOCKED | Treat directory values as candidate reference, not automatic statutory approval. |
| Catalog price levels, MRP and commercial guards | Catalog dated price/guard sources | Definition and Catalog resolution EXECUTABLE; invoice-final limits BLOCKED | CI-P3/P4 project verified sources into Accounting final calculation. |
| Warehouse master/default/registration link | Catalog warehouse and policy histories | EXECUTABLE for master validation; physical location effects BLOCKED | CI-P3/P4 tie actor, item, GSTIN and stock location to one movement. |
| Inventory template/profile choices | Catalog `InventoryProfileTemplateRevision` and `ItemInventoryProfile` | DEFINITION_ONLY for physical stock | CI-P2 marks `SPECIFIC` and `WARN/ALLOW` non-executable; CI-P4 implements supported owner paths. |
| Stock quantity, valuation, openings and replenishment | Vouchers plan; no Accounting stock-movement/valuation producer found in source audit | BLOCKED | CI-P3 adds truthful suggestions; CI-P4 owns movement/cost/GL and rebuild tests. |
| Voucher type/class configuration and invoice capture | Vouchers shared policy/revision and manual invoice controls | EXECUTABLE for supported account-only capture; stocked paths BLOCKED | CI-P4 binds item/company source pins and owner-derived acceptance. |
| Manufacturing/BOM/job work | Catalog definition and voucher plans | DEFINITION_ONLY or partial non-posting capture by feature | CI-P4 needs material/custody/WIP/cost/tax owner effects before execution. |

The older [company/item TODO](company-item-configuration-todo.md) recorded four checked
Phase 1 changes. Current focused tests pass for three Catalog cases: warehouse tax
registration linkage, inventory negative-stock *definition*, and HSN/SAC directory
search. The Accounting source-document test covering single and same-day aggregate cash
receipt limits also passes. This is evidence for those narrow paths, not for stocked
invoice execution, legal completeness of the directory, or negative-stock valuation.

The old TODO's Phase 2-5 descriptions overlap the authoritative voucher batches and
still say `Billing`. During implementation, replace those items with links to the
current Vouchers/Accounting owner work; do not build a second sequence allocator,
stock ledger or valuation store from that older checklist.

**CI-P0 test evidence:** Catalog focused tests `3 passed`; Accounting dated-source
and cash-boundary test `1 passed`. The first Accounting filter attempt selected no
tests; its nonzero exit was a test-selection error, corrected by the explicit test.

**CI-P0 decision:** accounts are baseline; stocked execution must reconcile quantity,
value and GL under Accounting; initial selected valuation methods are FIFO and moving
average; valued negative stock blocks; `SPECIFIC` and `WARN/ALLOW` remain visible as
definitions without execution readiness; India GST is the initial tax profile and
India state-VAT requires an explicitly implemented state/date scope. Existing data and
published revisions are preserved. No capability or release gate has been activated.

## Phase status

| Phase | Status | Evidence |
|---|---|---|
| CI-P0 | COMPLETE for current source audit | Setting register and focused proofs above. |
| CI-P1 | IN_PROGRESS | Identity-only readiness read and company locking correction implemented; remaining consumer/source checks pending. |
| CI-P2 | IN_PROGRESS | Catalog effective-item fact/readiness slice implemented; complete tax/price/location facts and wider repair review pending. |
| CI-P3 | PLANNED | Tax/price/location/replenishment integration pending. |
| CI-P4 | PLANNED | Stock and voucher owner execution pending. |
| CI-P5 | PLANNED | Full release review and activation evidence pending. |

## CI-P1 implementation checkpoint

`GET /v1/companies/{company_id}/setup-readiness` reports Identity-owned company
status, source timestamp, first-posting field locks and every fixed feature's
current state, dependency list, missing prerequisites, tax-system compatibility,
lock evidence and source timestamp. It deliberately
does not call Catalog/Accounting/Vouchers or claim stock/tax posting readiness.
The endpoint checks company scope and refuses derived output when a required
company source field is read-denied. It has 401, wrong-company 403, invalid-id 422,
normal and field-denial regression cases. The service OpenAPI and generated client
were updated.

Review found that feature enable/disable and posting reservation used different
locks. The feature transitions now take the company row lock before reading feature
state; reservation and terminal posting paths take that same row lock after the
existing tenant lock. A regression for feature transitions failed before the fix
(`False, False` lock observations) and passes after. The 29-test company/posting
group passed; strict Identity mypy passed 133 source files. Native concurrent
MySQL evidence and all CI-P1 source readiness work are still pending.

## CI-P2 implementation checkpoint

Catalog now has a protected, dated `GET /v1/companies/{company_id}/items/{id}/effective-facts`
read that composes the existing pinned product configuration and requirements,
item/family identity, product type, dated primary group assignment, exact effective unit
revision grid, minimum sale quantity and the selected inventory template revision. It distinguishes
Catalog definition eligibility from physical stock execution: goods report
`UNAVAILABLE` with explicit reasons until Accounting has a stock runtime; services
report `NOT_APPLICABLE`. `SPECIFIC` valuation and `WARN/ALLOW` negative stock are
visible as selected definitions with additional unavailable reasons. Existing
field-context checks protect each native source. Goods and service, wrong-company,
invalid-date and field-denial API cases pass. Catalog Ruff, formatting and strict
mypy passed. Catalog OpenAPI and generated client were updated, and the client
generation check and typecheck passed. Full tax/price/location aggregation and native
end-to-end acceptance remain pending. Existing tax and price resolution require
transaction-specific context; their separate protected endpoints remain the source
of those answers, rather than a static effective-item tax or price assertion.

## CI-P3 and CI-P4 dependency checkpoint

Catalog already implements dated tax and price resolution plus typed warehouse and
replenishment policies. These are definition and resolution paths, not an Accounting
stock balance or a voucher posting result. The voucher tracker still lists B15-B18
in progress and the stock producer/report batches B20-B27 pending. An authoritative
replenishment suggestion needs verified on-hand, reservation and order buckets;
without them, zero would be a false claim. CI-P3 remains open for consumer/source
integration, and CI-P4 cannot pass its stock/GL, FIFO/moving-average, return and
rebuild acceptance until those owner batches are implemented. No release gate was
changed.

## Review and validation checkpoint

Pass 1 checked company/feature/reservation lock ordering, item source selection and
execution claims. The feature transition previously read without the company lock;
its regression failed before the correction and now passes. The new effective-item
read explicitly requires the dated group assignment before returning its identifiers.
A conditional group field-denial test also passed without that extra check because
the existing configuration resolver already failed closed; the explicit check keeps
the new projection's own data access boundary clear. The stock state stays
`UNAVAILABLE` and no setting enables a stock posting path.

Pass 2 checked tenant/company scope, field-level read denies, generated contracts and
source-owner limits. Identity company/posting tests: 29 passed. Catalog product,
warehouse-policy, tax-workflow and activation-price tests: 23 passed before the final
group guard, followed by 5 changed-endpoint tests passing. Catalog and Identity strict
mypy passed (263 and 133 source files); changed-file Ruff checks passed. Generated
client freshness and TypeScript typecheck passed. No new migration or financial writer
was introduced. Native stock/GL reconciliation, MySQL concurrency, year-boundary
rehearsal and full cross-service suites are still required for CI-P4/CI-P5.
The [operator guide](company-item-configuration-operator-guide.md) explains the
current protected reads and explicitly names the unreleased stock boundary.

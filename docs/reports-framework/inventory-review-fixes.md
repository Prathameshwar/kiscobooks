# Inventory report contract fixes

Authorized 2026-10-23 following the review of all ten inventory reports. This change
addresses the four report contract gaps; operational stock producers remain under B20-B26.

## Delivered behavior

- ITEM_LEDGER exposes `value_balance` on opening and movement rows. The last balance in
  each position is its closing value. Values use retained owner value legs and the same
  inclusive requested period as quantities. Third-party or unavailable valuation is null.
- STOCK_MOVEMENT exposes `opening_value`, `inward_value`, `outward_value`, and
  `closing_value`. Positive/negative value legs, including zero-quantity adjustments,
  contribute once to value turnover. Opening + inward - outward reconciles to closing.
- STOCK_EXPIRY exposes remaining `carrying_value`, `reserved` quantity, and separate
  valuation/reservation availability statuses. Expiry never removes physical value.
- BATCH_SUMMARY accepts a typed optional `lot_id`. It filters current positions and
  retained history, labels the scope filtered, and survives signed item-ledger drilldowns.
- STOCK_VALUATION exposes `valuation_detail_status` on position rows. Setting
  `include_cost_details=true` adds authoritative residual FIFO layers, position shares of
  moving-average pools, and source-linked VALUE_ADJUSTMENT movements. It requires complete
  movement history and cost detail for every selected owned position; missing evidence
  blocks the detailed run. A position report without this option remains available with
  an explicit unavailable detail status for old source data.

The five affected definitions advance to version 2. Default and audit views declare the
new monetary/quantity columns; source identifiers are retained in the audit view. Paging,
result filtering, signed drilldowns and all four export formats use the ordinary framework.
The existing complete-company, financial, item/warehouse and field permissions apply.

## Owner evidence and compatibility

Reporting-contract 0.7.0 adds optional `Position.valuation_detail` in the existing JSON
handoff. No database columns or migrations are required. Accounting, Reports and Identity
consume updated locks. Deploy compatible owner/consumer packages and begin a fresh source
epoch before publishing the new schema. Existing financial and 0.6.0 inventory schema
hashes remain readable; frozen facts and report artifacts are not rewritten.

`valuation_detail.layers` contains at most 200 owner FIFO residual allocations per
position. Each carries a stable layer ID, optional origin ID, receipt date, remaining
quantity and remaining value. Identities must be distinct within the position; sums must
exactly match its quantity and carrying value. A layer split across positions describes
each position's residual allocation, never repeated whole-layer totals. Dates cannot
follow the snapshot date.

`valuation_detail.pool` carries a stable moving-average pool ID and this position's
allocated quantity/value, which must match the position. It is **not the entire pool
balance**. FIFO rejects a pool; moving-average requires a pool and rejects FIFO layers.
Third-party positions cannot claim owned cost detail. Reports validates and presents owner
cost evidence; it does not manufacture cost layers from receipt-age cohorts or sales prices.

Cost-detail rows use `remaining_quantity`/`remaining_value`, position rows use
`quantity`/`carrying_value`, and adjustments use `value_delta`. These separate measures
prevent detail from multiplying stock balances. Adjustment rows retain movement/voucher
IDs, number and date. They describe retained value adjustments already reflected in the
owner's closing layer/pool allocations; they must not be added again to closing values.
Ordinary valuation GL_CONTROL rows repeat account-level carrying value as a reconciliation
measure, as before; sum only POSITION rows for the position total.

Detailed valuation reads and budgets movement history; current balance reports retain
their indexed balance-only source plan. Existing source/result/byte bounds still apply.

## Verification

Regression tests were added before implementation and reproduced the missing balances,
expiry columns, rejected lot filter, missing detail option and absent output metadata.
Further checks cover exact layer/pool reconciliation, malformed and future-dated detail,
unknown capabilities, retained adjustments, native and legacy ingestion, authority,
drilldowns, source admission bounds and exports.

- Broad report/registry/navigation gate: **357 passed, 1 native-only skip**. Fresh domain
  branch/statement coverage: **92.51%** against the unchanged 90% floor. Inventory
  calculation coverage is approximately 98%; the new valuation detail module has complete
  branch/statement coverage. All ten legacy/versioned API cases and forty ordinary
  report/export-format cases are included, along with four detailed valuation exports.
- Final focused gate after adding audit position/lot identifiers: **27 passed**.
- Accounting inventory handoff/feed: **9 passed, 1 infrastructure skip** on SQLite.
  Identity report authority/company context: **6 passed**. API-client tests: **8 passed**.
- Native MySQL 9.6: **27 Reports tests passed** and **5 Accounting handoff tests passed**.
  Both verification helpers completed schema/model/index parity and migration
  downgrade/upgrade round trips (Reports 0038, Accounting 0155). Disposable test schemas
  were removed and the test server was stopped afterward.
- Reports strict mypy: **118 source files** pass. Accounting handoff and both changed
  shared contract modules pass strict checks. Ruff and formatting checks pass.
- Reports/Accounting OpenAPI freshness, generated client checks and API-client TypeScript
  checks pass. Accounting's generated manifest hash is synchronized with the new contract.

A supplementary 65-test domain selection passed all its assertions but, considered alone,
failed the whole-domain coverage gate at 44.10%. The broader fresh gate above passed
92.51%; coverage exclusions and thresholds were not changed. An initial detailed-export
test used a helper argument the existing helper does not accept; it now creates the audit
export through the endpoint, and all four format cases pass.

The initial native check against the existing port 3306 service was denied by its login.
The repository's disposable loopback MySQL launcher provides a separate server on 13396
for the subsequent native verification. Operational B20-B26 producers, production
activation and large-volume/load tests remain outside this change.
PowerShell classified redirected Alembic INFO output as `NativeCommandError`, giving the
wrapper a nonzero status; both native logs contain the passing pytest summaries and
successful final migration messages, with no traceback. Cleanup was checked separately.

Manual simplification and security review followed CLAUDE.md sections 5/6: exact Decimal
arithmetic, typed closed inputs, source identity/coverage and byte bounds, company/tenant
authority, field-deny enforcement, signed drilldowns/downloads, and distinct detail versus
balance measures. The named `/simplify` and `/security-review` commands are unavailable
in this session; the manual review and regression checks cover those requirements.

# Company and item setup: current backend contract

This guide describes the implemented administrative reads, not a stock-posting
release. See the [CI-P0–CI-P5 execution record](company-item-configuration-execution.md)
for phase status and evidence. UI and payroll are outside this work.

## Read company facts

With `company.read` and scope on the company, call
`GET /v1/companies/{company_id}/setup-readiness` on Identity. The response has
`scope: IDENTITY_ONLY`: company status and source timestamp, first-posting field
locks, and every fixed feature's enabled/disabled/inconsistent state, dependencies,
missing prerequisites, tax-system compatibility and lock evidence. A read denial
on a source field needed for this result returns
403. Enabled inventory or batch features mean the company chose those capabilities;
they do not certify an Accounting stock writer or an activated voucher profile.

The existing company, dated registration and feature APIs remain the writers.
Company row updates, feature transitions and posting reservations serialize on
the company row so a reservation cannot validate against a feature transition
in flight. The separate
Accounting fiscal/period and ledger rules remain authoritative for posting.

## Read item facts

Call Catalog's
`GET /v1/companies/{company_id}/items/{item_id}/effective-facts?as_of=YYYY-MM-DD`.
The protected response includes the item/family versions, dated primary group,
product type revision, exact effective unit revision grid, minimum sale quantity,
pinned product configuration, definition requirements and selected inventory
template. A 403 can indicate missing company/object scope or a denied native
source field. The `as_of` date is required; it does not imply that every tax,
price or warehouse result can be determined without a transaction context.

For transaction-specific choices, use Catalog's separate tax resolution,
price resolution, item warehouse-policy and item replenishment-policy APIs with
their required permissions and inputs. Tax resolution still requires the legal
transaction's date, direction and jurisdiction; price resolution additionally
needs quantity, unit, currency and purpose. A missing/ambiguous resolution must
be handled as unavailable, not replaced with a static item default.

For goods, `stock_execution.state` remains `UNAVAILABLE` until Accounting has
accepted and reconciled the applicable stock quantity/value owner path. `SPECIFIC`
valuation and nonblocking negative-stock settings are definitions only. Service
items report `NOT_APPLICABLE` for stock. Catalog replenishment bands are settings,
not current stock; no authoritative suggested order quantity is published yet.

## Rollout boundary

This implementation adds no table, backfill, stock balance, cost layer or posting
feature activation. Existing authored configurations and posted history need no
migration for the two reads. Before stocked voucher release, complete the
[voucher tracker's](voucher-delivery-tracker.md) Accounting/Vouchers stock batches,
owner projection acknowledgement, fiscal/return cases, rebuild parity and native
stock-to-GL reconciliation. Any discrepancy must be repaired through that owner's
audited procedure; do not edit Catalog item data to change historical stock.

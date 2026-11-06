# Purchase direct posting rollout

## Goal

For every default Purchase type (account, product, mixed), the entry action offers
Create/Update and Create/Update and Submit. With the default company policy, the latter
continues through authoritative calculation, acceptance, submit and posting until the
voucher is confirmed `POSTED`. A configured approval workflow stops at `SUBMITTED` and
waits for a different authorized approver. A failed or uncertain step remains visible
and recoverable under its original idempotency key; the UI never calls a draft posted.

## Current findings, 2026-11-05

- Company creation selects `inventory` by default, not `approval_workflow`; the three
  starter Purchase types explicitly set `approval_required=false` in that case.
- Vouchers already moves submit directly to `APPROVED` when approval is not required.
- The Console only exposes Save draft, then separate Calculate, Accept, Submit and Post
  actions. Its posting result is asynchronous and must be reconciled before `POSTED`.
- The VM has stock execution enabled, but invoice execution and the Vouchers to
  Accounting invoice credential are absent. The committed Console build also fails
  on numeric unit ratios sent to a string typed Catalog contract. The live release
  remains `46eff89f`.

## Phases and gates

1. Fix the committed build in an isolated change, then verify Console typecheck,
   affected tests and production build. Preserve concurrent local work.
2. Add the split action and a resumable Purchase command sequence. Test account,
   product and mixed types; no approval, required approval, duplicate bill,
   calculation refusal, posting rejection, timeout and refresh/retry. Verify the
   final status from the owner operation and a fresh voucher read.
3. Replace per-company invoice/posting service credential lists with authenticated
   company enrollment or an equally scoped native authority. Keep actor, tenant,
   company and policy checks at every owner boundary. Test a newly created company,
   wrong-company requests, revoked authority, idempotent redelivery and rollback.
4. Stage a tested source snapshot release, take consistent VM database and private-file backups,
   apply reviewed migrations if any, configure and activate matching service
   connections, deploy API/UI/workers together, and verify readiness and rollback.
5. In the named tenant, use the `+` flows to create suppliers, accounts and products
   as applicable; create two bills per available Purchase type with quantity, tax and
   discount cases; record voucher IDs, operation IDs and confirmed `POSTED` status.

## Deployment decision, 2026-11-05

The user authorized a VM release without a Git commit or push; Git publishing remains
for a later session. The release source is a frozen archive of this checkout, built in
its own VM directory. No schema migration differs from the current database heads.
The Invoice connection uses distinct signed credentials for Vouchers to Accounting
and Accounting to Identity. `allow_enrolled_companies=true` does not act as a tenant
wildcard: Vouchers discovers its native company guards, Accounting checks its native
setup row after verifying the request signature, and Identity checks an active
company row after verifying its separate Accounting signature. User authority and
voucher type approval policy remain independent checks. This is the enrollment path
for companies created after deployment; it avoids editing service secrets per company.

## Live verification, 2026-11-06

Release `/opt/kiscobooks/releases/purchase-20261105-2202` is active on VM
`201.18.205.54`. The Console production build succeeded after the saved-discount
rehydration fix and was restarted. The saved Bitvise profile described in `AGENTS.md`
was used; authentication secrets were not placed in repository files or commands.

The named tenant's `DEMO-TRADING-NKVH` company has six Purchase bills entered with
the live browser flow. Suppliers, expense accounts, and a product were created with
the `+` controls during these runs. The product has billed and received quantities,
warehouse, 18% IGST, and line discount; the mixed bills combine this product with a
taxable SAC 998314 service account and separate line discounts. Account bills carry
a line discount and are explicitly recorded without GST. The additional service
account's tax default was configured before it was used in a mixed bill.

| Type | Voucher | Journal | Tax | Payable | Stock posting |
| --- | --- | --- | ---: | ---: | --- |
| Account 1 | `01a1acbb-3be8-701b-af2d-57bed7259d5c` | `PURCHASE/FY2026-2027/000001` | 0.00 | 1,700.00 | No |
| Account 2 | `01a1aebd-f340-75a9-a5a2-15576273a7a8` | `PURCHASE/FY2026-2027/000006` | 0.00 | 1,700.00 | No |
| Product 1 | `01a1acd2-4cc6-736a-a6f1-de794ea9ba34` | `PURCHASE/FY2026-2027/000002` | 8,910.00 | 58,410.00 | Yes |
| Product 2 | `01a1aeab-4c39-72bf-b4c0-aad84a565259` | `PURCHASE/FY2026-2027/000003` | 8,910.00 | 58,410.00 | Yes |
| Mixed 1 | `01a1aead-c2a4-74a5-bb83-071540df97a1` | `PURCHASE/FY2026-2027/000004` | 4,609.80 | 30,219.80 | Yes |
| Mixed 2 | `01a1aebc-faeb-71dd-8471-15f919c71637` | `PURCHASE/FY2026-2027/000005` | 4,609.80 | 30,219.80 | Yes |

A fresh read from Vouchers and Accounting confirmed each voucher `POSTED`, at
least one `COMMITTED` operation, a `COMMITTED` money intent, and a balanced `POSTED`
journal with an invoice record. Product and mixed bills each have one stock posting.
Early diagnostic operations on Account 1 and Product 1 were rejected before the
underlying invoice and stock execution defects were fixed; the final operations are
committed and there are no incomplete operations for these six vouchers.

Verification on the VM: Console production build; 132 focused Console Purchase
tests; 16 Vouchers Purchase approval-flow tests. The approval tests cover default
direct approval on submit and a configured required-approval path that remains
`SUBMITTED` until a distinct authorized approver acts. No schema migration was
needed for the deployed changes. Git commit and push were deferred at the user's
request for the next session.

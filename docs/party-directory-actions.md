# Party and supplier directory actions

## Delivery phases

1. Reuse the current row action menu and native party-filtered credit policy
   directory. Resolve read/manage grants for the selected company independently
   of party-edit authority, and verify company configuration before enabling it.
2. Add pricing, ledger and pending-bill entries with honest unavailable states.
   Party-specific pricing has an effective-price read API, but its assignment
   authoring API and Console management page are not implemented; do not
   route it to unrelated company-wide price books or invent a party filter.
3. Test parties and suppliers, permission/configuration restrictions, retained
   navigation and unavailable actions. Review correctness and presentation.

Credit limits require the company's credit_limits capability. Pricing requires
inventory and multi_price_levels, plus customer-pricing read/manage authority.
Company configuration reads use their existing company.read authority. If the
configuration cannot be verified, actions remain disabled with an explanation.
Credit policies remain accessible through their existing master/detail routes
for historical review and preparation, as supported by the native service.

No ledger or bill-adjustment operation is invoked from these placeholders.
No API, model, migration, permission catalogue or seed change is required.

## Decision and verification (2026-10-27)

The directory uses the shared DataTable/Menu and existing token styles. Target
read/manage grants are independent of permission to edit the party itself. A
reader sees View credit limits; a manager sees Manage credit limits. The existing
list Refresh retries capability loading without blocking unrelated list reads.
Ledger and pending bills remain disabled, with visible reasons and no links.

All three phases are complete for the directory actions. Party-specific pricing
authoring remains unavailable and is explicitly identified as such. No new
assignment/price editor or backend authoring contract is claimed by this change.

Focused Console verification passed 133 tests across four suites; TypeScript and
whitespace checks passed. Cases include both lists, correct party/return filters,
disabled capabilities, missing configuration authority, configuration outages and
mismatched company responses, read-only policy access and expired/other-company/
role-only grants. A read-only live tenant3 browser check passed 12 captures across
three themes at desktop/mobile widths, verified menu placement and Escape focus,
and recorded no browser/API failures or writes. This test company's credit_limits
feature is disabled, so its live action correctly remained disabled; the enabled
navigation branch was verified by the component tests.

Final manual simplification and security reviews covered CLAUDE.md sections 5 and
6 (the slash-command tools are unavailable). No new authority, query expansion,
money handling or data mutation was introduced. No remaining scope or presentation
issue was found; pricing authoring and the two operational screens remain named
limitations rather than fabricated destinations.

## Deferred merge buttons (2026-10-27)

At the user's request, verified account details show disabled Merge accounts,
and party/supplier details show disabled Merge parties. The shared secondary
Button style is used beside the existing primary action, including for readers.
The accessible description states that duplicate merging will arrive in a future
update. These are placeholders with no click handler, link, modal or API; account
balances, party identities and financial history are unchanged. The paired product
detail placeholder uses the same presentation.

Verification: 143 focused detail/form regression tests passed, followed by a
46-test final detail check after arranging the secondary buttons. TypeScript and
whitespace checks passed. The shared disabled secondary-button styling fix passed
32 primitive/token tests. Eight live tenant3 desktop/mobile checks covered the
product, family, account and party detail buttons, with no browser errors or writes.
Manual correctness/security review found no new authority or mutable operation;
the only functional behavior is the existing native disabled Button state.

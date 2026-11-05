> UI retired on 2026-11-04. See [product UI removal](product-ui-removal.md) for the current scope. This document records the previous implementation.

# Product batch and serial navigation

Authorized 2026-10-29: make product-list and product-view tracking actions reflect
current company features and the product's actual inventory tracking configuration.

1. Reuse the existing lazy inventory-action menu in simple and advanced lists and
   product details. Add regressions for applicability, field protection and access.
2. Preserve the originating product/list and its filters through batch/serial
   management. Fail closed when an incoming product filter cannot be applied.
3. Verify UI, routing, existing preparation workflows and type/contracts; perform
   a manual security/correctness review and record evidence.

Active products use their activated inventory profile, not changed defaults for
future products. Company inventory and the matching batch/serial capability must
be enabled. Services and products without the relevant tracking do not offer that
action. Existing read/manage/hold authority remains enforced by the owner APIs.
Preparing tracking identities does not post quantity or value. No commit or
publication is included.

## Verification

All three phases completed.

- Added failing regressions for all four simple-list tracking combinations,
  product-view return destinations, protected product filters and company-scoped
  tracking-page access. Also checked case-normalized UUIDs and rejected records
  belonging to a different product in a filtered response.
- **130 Console tests passed in 6 files**, covering simple/advanced menus, product
  details, configuration refresh, disabled features, services, permissions, protected
  settings, tracking preparation, exact retries and retained navigation context.
- **33 Accounting tracking/source/domain tests passed** with isolated database and
  service-boundary fixtures. Existing batch/serial APIs and their mutations were
  reused without changes. No API schema/client regeneration or migration is needed.
- Console TypeScript check and scoped whitespace validation passed. A stale
  creation-tracking assertion expected the old word "SKU"; it now matches the
  existing product-oriented activation message, with production behavior unchanged.
- Isolated headless Edge review exercised the actual list and product-view menus,
  keyboard open/Escape/focus return, correct product-filtered destinations and
  configuration refresh. **12 theme/viewport checks** passed (light/dark/ledger,
  1440/390px, list/view), with no page errors or document horizontal overflow. Both
  mobile screenshots were inspected. Owner reads used fixtures; no live identities
  or stock were created, edited or posted. The browser harness shut down afterward.

## Security and correctness review

The `/simplify` and `/security-review` commands are unavailable in this session;
their subject areas were reviewed manually against CLAUDE.md sections 5 and 6.
No remaining findings were identified in the changed paths.

Inventory reads remain lazy until a menu opens, so listing products adds no
per-product configuration queries. Unknown/protected configuration does not grant
tracking actions. Reopening rechecks company features and effective tracking.
Read-only tracking users reach read-only directories; preparation and holds retain
their native permissions. Tracking pages now check grants for the selected company.
An inaccessible incoming product filter prevents loading an unfiltered company
directory. Return destinations remain local and allowlisted; tokens and unsupported
query fields are removed. Existing quantities, values, audits and posting admission
are unchanged. Concurrent local work was preserved. No commit/publication occurred.

# Advanced product creation: Phase 5 review

Reviewed 2026-11-05. This phase provides the verified creation entry and the
first two steps of the Advanced four-step experience. It follows
[the live TODO](advanced-product-creation-todo.md) and
[the UX contract](advanced-product-creation-ux.md).

## Delivered

- `/masters/items/new` chooses Simple or Advanced from the current company's
  verified `product_family_sku_enabled` value. The directory card uses that
  same value. A failed, denied, missing or wrong-company mode cannot launch a
  form. A mounted Advanced draft remains mounted and blocked after a mode
  change, so entered work is not replaced by a Simple form.
- Advanced displays an in-shell four-step path, responsive context rail and
  shared token-based `product-wizard.css` across light, dark and ledger themes.
  Phase 5 implements Profile and SKU editing; steps 3–4 remain named and
  incomplete until Phase 6.
- Profile editing uses the native options and family field set for name, code,
  published Type revision, group, brand/series/model, description and custom
  fields. It also collects configured categories and applicable manufacturer
  references for later native setup. A company default Type revision is shown
  when supplied; a user can select a different published Type.
- SKU editing starts with exactly one default slot. Additional SKUs require a
  variant-capable Type, enabled variant configuration and an explicit axis.
  It collects exact SKU codes, units, trade directions, quantity, permitted
  attributes, alternate units and pack conversions. Duplicate codes and
  variant signatures are blocked before moving on.
- Actor-scoped Catalog drafts can be listed, restored, created and replaced.
  The client sends reviewed mode/policy/source/field versions, preserves a
  frozen create key after an uncertain save and reconciles a possible lost
  replace response. Dirty work is guarded on company change and unload.

## Review evidence

- Console TypeScript typecheck passed after the changes.
- New entry, draft, policy and wizard tests passed: **12 tests**. Existing
  Product Mode, retired-route and classification pages passed: **31 tests**.
  Existing Simple creation and classification UI/policy runs passed **80
  tests** after one older page expectation was updated to the new route.
- A real Edge/Playwright layout check passed at 1440, 768, 390 and 320 px
  across all three themes. The test checks no horizontal page scroll and no
  clipped interactive control in the Profile view.
- Security review: the server still gates `item.create`; the mode provider
  requires `product_configuration.read`; the route policy admits only exact
  Advanced option/draft paths. No price, tax, stock or Voucher write is wired
  from this phase. Native endpoints remain authoritative for all field,
  reference, company and current-policy validation.

## Phase 6 dependencies

The UI must map the saved Profile classification and per-SKU unit declarations
into native setup commands, then add tax, profiles, purchase references,
selling prices, opening preflight and a truthful receipt-based progress view.
The Advanced route cannot submit a product until that work is reviewed.
Browser checks for SKU, Business and Opening states extend the visual matrix
in Phase 7.

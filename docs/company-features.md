# Company Feature Flags

**Status:** Identity configuration and console management implemented; each consumer's operational readiness is separate
**Date:** 2026-09-03
**Master:** `identity` · **Machinery:** `libs/platform` · **Consumers:** every service
**Related:** [company.md](company.md) §5.2 · [custom-fields.md](custom-fields.md) §1 · [roles-permissions.md](roles-permissions.md) §1 · [fiscal-year.md](fiscal-year.md)

Borrowed in concept from Tally's `F11: Features` matrix, which is the single best idea in that product's company model — and implemented with the enforcement Tally lacks.

---

## 1. What this is, and what it is not

A **feature flag says what this company does.** A service business doesn't want inventory fields, batch numbers, or godowns anywhere in its UI or its API surface. A pharma distributor needs all three plus expiry tracking.

Three controls, and conflating them is the mistake:

| Control | Question | Home |
|---|---|---|
| **Feature flag** ← this doc | Does this company *do* this at all? | `company_feature` |
| **Permission** | May this actor do it? | `role_permission` ([roles-permissions](roles-permissions.md)) |
| **Custom field** | Does this company want to *store* something extra? | `custom_field_definition` ([custom-fields](custom-fields.md)) |

The distinction against custom fields is the important one:

- A **custom field** lets a tenant add *data* the platform has no opinion about. It may never drive money ([custom-fields.md](custom-fields.md) §11).
- A **feature flag** turns on *native capability we built, tested, and can price from* — inventory valuation, foreign-currency revaluation, TDS deduction. It absolutely drives money, which is exactly why it is code and not configuration data.

**Both gates must pass.** `feature_enabled AND has_permission`. Never either alone.

The planned [Product Configuration](catalog-product-configuration.md) adds a narrower native
product-level gate: supported capability AND company feature (where required) AND applicable
product configuration AND valid transaction context AND actor permission. It owns defaults,
option requiredness and permitted SKU overrides, not a second company-feature catalogue.
Baseline options such as barcode metadata need no invented feature key. Disabling a product
option never erases history or bypasses existing tracking/feature-use locks.

---

## 2. Catalogue — code, not data

The feature list is a **fixed catalogue in `libs/platform`**, same as permission keys and custom-field data types. A tenant cannot invent a feature, because a feature is a claim that code exists to honour it.

**Clients read it from `GET /v1/company-features`, never from a list of their own.** The graph below is the authority; the labels, the sentence each feature is described by, and the order they are offered in are Identity's (`identity/domain/company_features.py`), because no other service renders them and a label is not a rule. That module checks at *import* that every catalogued feature is offered and that none is offered twice, so a feature added here without a label fails the boot instead of quietly disappearing from every setup form. The endpoint describes the platform and reads no tenant data; a company's own flags remain `GET /v1/companies/{id}/features`.

```python
FEATURES = {
    # accounting scope
    "inventory":        Feature(requires=[], locks_on="stock_movement"),
    "multi_currency":   Feature(requires=[], locks_on="foreign_currency_posting"),
    "cost_centres":     Feature(requires=[], locks_on="cost_allocation"),
    "budgets":          Feature(requires=[]),

    # inventory depth
    "bom_definitions":  Feature(requires=["inventory"]),
    "multi_godown":     Feature(requires=["inventory"], locks_on="godown_movement"),
    "batch_tracking":   Feature(requires=["inventory"], locks_on="batch_recorded"),
    "expiry_tracking":  Feature(requires=["batch_tracking"], locks_on="expiry_recorded"),
    "serial_tracking":  Feature(requires=["inventory"], locks_on="serial_recorded"),

    # statutory — gated by the company's tax system
    "e_invoicing":      Feature(requires=[], tax_systems=["gst_in"]),
    "e_waybill":        Feature(requires=["inventory"], tax_systems=["gst_in"]),
    "tds":              Feature(requires=[], locks_on="tds_deducted"),
    "tcs":              Feature(requires=[], locks_on="tcs_collected"),
    "reverse_charge":   Feature(requires=[], locks_on="rcm_posting"),

    # commercial
    "sales_promotions": Feature(requires=[], locks_on="sales_promotion_posted"),
    "credit_limits":    Feature(requires=[]),
    "recurring_billing": Feature(requires=[]),
    "approval_workflow": Feature(requires=[]),
}
```

Three properties per feature:

`bom_definitions` enables single-level BOM authoring and non-posting quantity
preview. It defaults off, requires inventory and does not enable manufacturing
execution, stock movements or cost posting. Disabling it prevents new authoring
and selection while permission-protected history remains readable.

- **`requires`** — dependencies. Enabling `expiry_tracking` enables `batch_tracking` and `inventory` transitively, or is rejected; disabling `inventory` is rejected while any dependent is on. Cycles rejected at import time.
- **`tax_systems`** — the feature is only offerable when the company's tax system matches ([company.md](company.md) §2.1). `e_waybill` on a UK VAT company is meaningless and must not be selectable.
- **`locks_on`** — the event that makes the flag irreversible. §4.

---

## 3. Table

```
company_feature
  id, tenant_id, company_id
  feature_key               -- from the code catalogue (§2)
  is_enabled
  enabled_at, enabled_by
  disabled_at, disabled_by
  locked_at                 -- set once dependent data exists; §4
  lock_reason               -- the event that locked it, for the error message

  UNIQUE (company_id, feature_key)
```

**Rows, not a JSON column on `company`.** A JSON blob cannot carry `enabled_by`, cannot be queried for "which companies have inventory on," and gives the audit trail one opaque diff instead of a discrete event per feature. Feature changes are `admin`-category audit events in their own right.

Absent row = disabled. The jurisdiction profile's `default_features` ([company.md](company.md) §3) are what a setup form offers **already selected** — `GET /v1/reference/countries` carries them per country as `default_features`, in dependency order, and empty for a country with no profile.

**A default is a suggestion, not a seeding.** Creation writes no `company_feature` row of its own: each feature is still enabled by its own call, with its own actor, its own audit event and the dependency closure the endpoint enforces. A pre-selected capability is visible on the capability step, says what it does, carries its `Permanent` badge if it has one, and is cleared with one click before the company exists. The alternative — a row appearing because of a country — is a capability nobody chose with an `enabled_by` nobody can explain.

The list lives in the profile and not in a client because three clients would hold three opinions about what a company in India does. Validated at import: every key is in the catalogue, is offerable under one of that jurisdiction's tax systems, and is preceded by whatever it `requires`.

---

## 4. The ratchet — a feature that shaped posted data cannot be turned off

This is the rule Tally does not have, and its absence is why Tally deployments quietly corrupt their own history.

> Enable multi-currency. Post a USD invoice against an INR base currency. Disable multi-currency. What is that invoice now worth, and which exchange rate reproduces the figure you already filed?

So: **once `locks_on` fires, the feature is permanently enabled.** `locked_at` is set by the first dependent write, inside that write's transaction, and never cleared.

| Feature | Locked by |
|---|---|
| `inventory` | Any stock movement |
| `multi_currency` | Any posting in a non-base currency |
| `batch_tracking` | Any batch recorded against a stock item |
| `expiry_tracking` | Any expiry date recorded |
| `cost_centres` | Any cost allocation on a posted voucher |
| `tds` / `tcs` / `reverse_charge` | Any deduction, collection, or RCM posting |

This is [company.md](company.md) §5.2's principle generalized: **anything that has shaped posted data is immutable.** Enforced in `domain/`, for every actor including platform admin — it is not a permission and no role can override it ([field-permissions.md](field-permissions.md) §1).

Features with no `locks_on` — `budgets`, `credit_limits`, `approval_workflow` — are freely reversible because they constrain future behaviour without reinterpreting past figures.

### Disabling never hides history

A feature that is off but was once on still renders its historical data. A company that stops using cost centres still shows cost centres on old vouchers, in old reports, and in exports. Same rule as deactivating a department (rule 4.12): **off means unavailable for new records, not hidden.**

Practically, most `locks_on` features can never be disabled at all, so this applies mainly to the reversible ones and to the pre-first-posting window.

---

## 5. Enforcement

In the shared library, checked in the route layer alongside the permission check:

```python
@requires_permission("invoice.create")
@requires_feature("inventory")            # 409 if not enabled for this company
```

**A disabled feature returns 409, not 403.** 403 means *you* may not; 409 means *nobody here can, yet*. Keeping them distinct matters because permission denials are `access`-category audit events worth investigating ([field-permissions.md](field-permissions.md) §10), and feature-gated calls are ordinary client behaviour that would otherwise flood that signal.

The error envelope names the feature so the client can offer to enable it:

```json
{"error": {"code": "feature_not_enabled", "feature": "batch_tracking",
           "message": "Batch tracking is not enabled for this company."}}
```

**Replication:** features are read on write paths in every service, so they replicate read-only from `identity` like tax registrations, and a missing replica row is a hard failure rather than an implicit enable ([company.md](company.md) §5.3).

---

## 6. What features drive, beyond routes

1. **Custom field visibility.** `custom_field_definition.requires_feature` — a definition whose feature is off resolves out of the effective set entirely ([custom-fields.md](custom-fields.md) §5, step 1). Cleaner than referencing features inside visibility rule trees, because it resolves at cache time rather than per record.
2. **Native field requirements.** `batch_tracking` makes batch number required on stock lines. That is a domain rule keyed off the flag, not a field policy.
3. **Client navigation.** Both clients render menus from the resolved feature set. `GET /companies/{id}/features` returns it; the clients never hardcode a feature list.
4. **Report availability.** A stock valuation report is not offered to a company without `inventory`.
5. **Pricing, eventually.** Feature enablement is the natural meter for plan tiers — which is a reason to keep the catalogue small and meaningful rather than one flag per checkbox.

---

## Catalog price levels

Implemented in shared library 0.19.0: **multi_price_levels**, with
`locks_on=customer_price_level_posted` through the existing Identity ratchet. The verified
Identity source exposes it to Catalog. PRICE1 remains baseline; enabled companies may
bootstrap PRICE2/PRICE3 and create additional named levels (up to ordinal 64), without
inventing amounts. Run Catalog's idempotent `POST /pricing/bootstrap` after enablement.
Catalog does not perform a synchronous cross-service write during Identity's transaction.

[V1.3 pricing](catalog-v13-api.md) supports dated company defaults/fallback and authorized
administrative selection. Customer identity/pricing-type mappings and the actual Billing
posting producer remain future owner-contract work. The event name's registration does
not claim that posting producer exists. Historical level/price reads remain available;
disabling the feature prevents resolution/publication through additional levels.

## Planned voucher policy integration

The [Sales/Purchase configuration plan](voucher-commercial-configuration.md) adds native
Vouchers company/type/class restrictions below Identity capabilities. They select permitted
discount scopes, charges, free-entry purposes and implemented deal mechanics; they do not
duplicate feature flags or override product/legal/actor restrictions. Manual authorized bonus
entry and automatic scheme redemption have separate readiness requirements. Existing feature
first-use/disable rules still apply; policy tightening preserves historical returns/reprints.

The [all-voucher configuration contract](voucher-configuration-design.md) applies this boundary to accounting/banking,
stock, orders/scenarios and job-work settings too. Vouchers policies may restrict native
capability; they do not replace Identity activation/access or Catalog/Accounting master rules.
Published settings still require the appropriate runtime and consumer readiness.

## Commercial definition additions — promotions and coupons

The `sales_promotions` fixed feature gates Catalog definition authoring and publication. It
locks on the future `sales_promotion_posted` event. Its label explicitly describes definitions;
turning it on never enables sale application, quotas or redemption. Those consumers still require
complete released definitions and their own first-use/disable handshake. Coupons additionally
require their own definition gate when implemented. Physical gifts require inventory and the
actual tracking capabilities; ordinary authorised manual discounts remain baseline functionality.

P3/P4 deliver registry entries, management, local projections, roles/seeds and the existing
first-use/disable handshake together. A coupon sale records both applicable distinct use events.
Disabling before first use coordinates pending holds; after use the ratchet preserves history.
Suspending an offer or code uses Billing's dated redemption_block, independent of irreversible
capability flags. No arbitrary company-created feature keys or generic approval engine are implied.

## Planned warehouse behavior — Main and multiple stores

The existing multi_godown feature already requires inventory and locks on godown_movement.
The [warehouse design](catalog-warehouses.md) defines its consumer behavior: each company always
has Main metadata; inventory without multi_godown uses only Main; additional stores/godowns
require multi_godown. Main-only movement locks inventory, while actual additional-location
opening/transfer/receipt/issue (including dispatch into transit) records multi_godown use.

Creating an empty master does not itself lock the feature. Before first use, disabling still
requires coordinated checks for stock/value, holds, pending documents and default references.
After use the ratchet applies. Per-location sale/purchase/transfer/return controls narrow native
operations and do not create new company feature keys or erase historical stock.

## Planned Catalog addition - optional BOM definitions

Proposed fixed capability **bom_definitions** requires **inventory** and supports only Catalog
BOM/routing/specification authoring and estimates. It is not an existing runtime feature and
does not enable production orders, backflush, WIP, machines/capacity or actual manufacturing cost.
Identity source registration/projection support is an external prerequisite for Catalog M0;
no Identity source implementation is hidden in the Catalog checklist.

Native [manufacturing configuration](catalog-manufacturing-design.md#7-configuration-and-lifecycle-controls)
controls per-product participation and supported structure/estimate options. Disabled by default;
GOODS stock outputs only. Separate definition availability from execution-owner acknowledgement.
Feature disable/use follows the existing Identity ratchet and preserves historical references;
Catalog default/retirement changes cannot revoke or rewrite running production documents.

## 7. Open questions

- [ ] Should a plan tier *cap* which features a tenant may enable? Implies `plan_feature` and resolves the deferred `plan` table ([org-model.md](org-model.md) §6.3)
- [ ] Can a feature be enabled tenant-wide as a default for new companies, or is it strictly per company?
- [ ] `approval_workflow` is listed but undesigned — it needs threshold and routing machinery ([roles-permissions.md](roles-permissions.md) §7)
- [ ] Does disabling a reversible feature need a cooling-off period, or is immediate correct?
- [ ] Should `locked_at` be set optimistically at enable time for features where the first dependent write is hard to intercept cleanly?

## 8. Decision log

- 2026-10-27: Implemented `JurisdictionProfile.default_features` (§3), carried per country by
  `GET /v1/reference/countries` as `default_features` and used by the company creation wizard
  to arrive with the ordinary capabilities already selected. India suggests `inventory`,
  `credit_limits` and `e_waybill`; the UK the first two. `e_invoicing` is deliberately not
  suggested — it starts at a turnover threshold and needs IRP credentials nobody has at
  creation time, so it is offered unselected. **Nothing is seeded:** each suggestion is still
  enabled by its own call with its own audit event, and clearing one before creation leaves no
  trace. Validated at import (catalogue membership, tax-system offerability, dependency order),
  so a default no code honours fails the boot. Changing a country re-suggests until the
  operator touches the step; after that their selection stands, minus anything the new
  jurisdiction cannot offer — a GST-only capability carried into a UK company was a 422 from
  the enable call after the company already existed. Nothing is pre-selected where the cards
  are disabled, because a selection that cannot be cleared is not a suggestion. Shared
  library 0.42.0; api-client 0.2.31.

- 2026-10-24: Implemented [company configuration UI/API](company-configuration-ui-api.md)
  using the existing catalogue and setup snapshot. Explicit feature reviews carry a
  reason and optional expected company version; Identity checks active status/version
  under the parent lock. Actual feature changes advance the company version and emit
  one existing outbox audit event; repeated enables do not invent audit changes.
  Dependencies, tax gates and first-use/pending-use protection remain authoritative.
  Company metadata editing remains the existing editor. Capability configuration does
  not certify consumer readiness or activate posting/provider execution.

- 2026-09-11: Proposed bom_definitions as an optional Catalog definition/estimate capability
  requiring inventory; Identity source registration remains external work and production
  execution requires its own supported consumer. No runtime enablement is claimed.

- 2026-09-11: Defined existing multi_godown semantics for permanent Main, extra locations,
  first actual multi-location use and independent warehouse operational controls.
- 2026-09-11: Added Product Configuration as a scoped native gate/default system below
  existing company capabilities; feature authorization, dependencies and use locks remain authoritative.
- 2026-09-11: Recorded proposed sales_promotions/coupons dependencies and distinct first-use
  events, including holds/disable coordination and a separate operational suspension control.
- 2026-09-11: Recorded proposed multi_price_levels from the user's Catalog requirements.
  Implementation must extend the code catalogue and producers/consumers together; the
  planning entry does not claim that the current API accepts this feature key.

- 2026-09-11: Added implemented `point_of_sale` capability configuration, reversible and
  without dependencies or tax gates. It is independent of business category/role/store format;
  checkout/payment execution remains a separate capability implementation. Shared library v0.6.1.

- 2026-09-12: Implemented multi_price_levels in shared 0.19.0, Identity configuration and Catalog verified sources; explicit idempotent bootstrap seeds reserved definitions. Customer mapping/actual Billing first-use production remains outside V1.3.

### Sales commercial-configuration review - 2026-10-10

Linked planned Vouchers Sales/Purchase/type/class policies below existing capability and
product restrictions. Native free-sale/discount guards remain authoritative inputs; no
Catalog/Identity runtime setting or feature activation was changed.

### All-voucher configuration review - 2026-10-10

Extended the planned Vouchers policy boundary from commercial controls to the common
all-kind registry. Existing Identity capability/first-use and owner enforcement rules remain;
no feature flag, provider, payroll function or runtime capability was enabled.

Decision 2026-10-27: register sales_promotions for bounded Catalog definition authoring. Operational sale application remains unavailable without consumer admission.

Decision 2026-11-07: physical batch/serial registration uses a separate delegated
Identity reservation over the existing durable reservation lifecycle. Pending
registration freezes the identity capabilities and their prerequisites against
disablement. Accounting commits its physical record and confirmation outbox
together; its posting-delivery worker confirms the first use. A rejected local
write emits an abort. A lost reserve response remains pending and must be retried
with the same command key/content; it cannot authorize local creation. An abort
can seal an operation before a delayed reserve arrives. Registration confirmation
locks batch/serial and any actual declared expiry, but does not set
`first_posted_at` or lock inventory merely for an empty identity. Stock posting
and reversal also include expiry tracking for the actual selected batches even
when the product profile makes expiry optional.

The signed private routes are `/internal/v1/tenants/{tenant}/companies/{company}/tracking/reservations`
and `/{operation}/{confirmed|aborted}`. They reuse the enrolled stock Identity
connection and credentials with distinct operation signatures. Reserve requires
fresh original-actor company authority and the corresponding Accounting batch or
serial manage grant; financial posting grants are unnecessary. Terminal delivery
is restricted to its retained registration owner and exact command hash.
Confirmed outcomes are immutable. Accounting's existing `posting_delivery`
worker delivers registration confirmations/aborts with bounded retries and
backlog reporting. Registration fails closed when this transport is absent.
Contract versions: identity-posting-client 0.3.3 and API client 0.2.75.

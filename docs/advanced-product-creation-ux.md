# Advanced product creation: Phase 0 UX and field contract

Saved 2026-11-04. This document specifies the directory entry and four-step
experience for [the implementation plan](advanced-product-creation-plan.md).
It is a reviewable design contract; no application behavior is changed by it.

## 1. Entry and route

The current company authoring control is Catalog
`product_family_sku_enabled` from `GET /product-configuration/authoring`.
`variants_mode` and type-level `allow_variants` only affect the Advanced
wizard's variant section. The product listing, its creation card, its empty
state action and `/masters/items/new` must agree on the **same verified current
company mode**. There is one creation route and one mode-selected experience.

| Verified state | Directory card and action | `/masters/items/new` | User-facing explanation |
|---|---|---|---|
| Mode false, `item.create` granted | **New product**; “Create one product with its units, prices and optional opening stock.” Action: **Create product**. | Simple Product creation. | “You are creating a product for {company}.” |
| Mode true, `item.create` granted | **New Product Profile + SKUs**; “Define shared product details, then add one or more SKUs and their setup.” Action: **Create profile and SKUs**. | Advanced four-step wizard. | “Create a Product Profile and its SKUs for {company}.” |
| Mode loading or refreshing without a usable verified result | Reserved card skeleton; no link or click target. | Blocking loading state. | “Checking product setup for {company}…” |
| Mode read failed, malformed, stale or wrong-company | Non-actionable card with **Retry**. Never guess Simple. | Blocking error with **Retry**. | “Product setup could not be verified. Retry before creating a product.” |
| `product_configuration.read` denied | Non-actionable card. | 403 explanation. | “Product setup access is needed to choose the creation flow.” |
| `item.create` denied | Read-only card or no primary action; preserve permitted listing. | 403 explanation. | “You can view products, but cannot create one for this company.” |
| Company missing | Existing company selection/setup state. | Existing company state. | “Select a company before creating a product.” |

The card and empty state action use `/masters/items/new` and preserve the
existing safe `returnTo` behavior. A direct URL is no bypass: it verifies mode,
company and creation permission before mounting either form. An existing
verified value may be displayed during a refresh only if the provider can
prove it belongs to the current company and is still usable; a failed refresh
blocks new submission and asks for a fresh check. A company switch never reuses
the previous company's mode, options or draft.

**Current implementation gap:** `ProductCatalogPage.tsx` renders
`SimpleProductCreate` for product creation regardless of mode. The directory
already switches between Simple and Advanced listings, but Advanced currently
has no product creation action, and a failed mode read falls back to the Simple
listing with its **New product** link. Neither listing has the proposed card.
The creation route and both listing states need the same verified-mode guard.
This is implementation work in the later UI phases, not a Phase 0 change.

### Directory wireframe and exact primary copy

```text
Products                                      [company switcher]
Search, filters, import (when permitted)

┌──────────────────────────────────────────────────────────────┐
│ New Product Profile + SKUs                    [Create profile │
│ Define shared details once, then set up each SKU.  and SKUs] │
│ 4 guided steps · Drafts can be saved                         │
└──────────────────────────────────────────────────────────────┘

Product list, or an empty state with the same mode-selected action
```

In Simple mode the card title/body/action come from the first matrix row;
there is no Advanced teaser or mode selector. In Advanced mode, creating a
single SKU remains normal even when variants are disabled. The import action
is independent and remains visible only with its existing permission. Do not
describe optional batch, serial or opening capabilities as available until
the native options for this company/type say so.

## 2. Four-step page structure

```text
Products / New Product Profile + SKUs          Company: Example Ltd
Create a Product Profile and its SKUs

1 Profile  ──  2 SKUs & units  ──  3 Business setup  ──  4 Opening & review

┌─ Main content, max comfortable reading width ─┐  ┌─ Context rail ─┐
│ Step heading + one-sentence purpose             │  │ Company, kind  │
│ Error summary, if needed                         │  │ Draft state    │
│ Clearly named sections and field help           │  │ SKU completion │
│ In-step SKU list or focused editor               │  │ Blockers       │
└─────────────────────────────────────────────────┘  └────────────────┘

[Back]                         [Save draft] [Continue / Review / Submit]
```

Use the Console shell scroll region with shared `@janso/ui` primitives and
product-scoped styles in `mfes/packages/ui/src/styles/product-wizard.css`.
The existing full-viewport `WizardLayout` must not be nested unchanged inside
`ConsoleShell`. Desktop shows a compact step rail or horizontal stepper and a
context summary; tablet reduces the rail; phone uses one column with step
label “Step N of 4” and stacked SKU cards. The sticky action area must never
cover content, focus, field errors or the on-screen keyboard. Use existing
tokens for spacing, type, surfaces and states across light, dark and ledger
themes. A step title is a real heading, not decorative text.

### Step 1 — Product Profile

Heading: **Product Profile**. Help: “Details shared by every SKU.” Begin with
kind, name, code, published Product Type and group. Classification sections
appear in a predictable order: categories; brand/series/model;
manufacturer/site; shared typed and descriptive attributes; variant axes.
Selecting Service immediately makes physical setup inapplicable, but entered
Goods data remains in the draft until the user confirms a deliberate type
change. A changed Product Type or axis prompts a review of dependent SKU data.

### Step 2 — SKUs and units

Heading: **SKUs and units**. Help: “Add only the SKUs you intend to use.”
Always start with one editable SKU. A non-variant profile has exactly one SKU;
hide Add SKU for that structure. When variants are allowed, adding an SKU is
explicit and no Cartesian product is generated. Desktop: compact SKU list at
left, one focused editor at right. Phone: labelled cards with name, code,
variant signature and “Needs details”/“Ready for setup” status. Move between
SKUs without losing unfinished values. Changing a shared axis marks affected
SKU signatures for review; never delete rows silently.

### Step 3 — Business setup

Heading: **Business setup**. Help: “Set tax, policies and prices for each SKU.”
Show a per-SKU summary first, then tax, published profiles, purchase reference,
named sale prices, and applicable optional price dimensions. A required
price level is visibly marked. A single applicable sale level uses one field;
several levels use named rows. Each amount shows currency, unit and tax basis.
“Saved draft” is never described as “active price”. A readiness panel names
the SKU and native prerequisite for each blocker with an Edit action.

### Step 4 — Opening and review

Heading: **Opening and review**. Help: “Review the product before creating it.”
For eligible stock Goods, opening stock is an explicit optional choice, with
per-SKU date, location, quantity, cost and physical identifiers as applicable.
Service and non-stock Goods omit the opening editor and proceed to review.
The review lists shared profile, every SKU, units, tax, published profiles,
prices, defaults applied and any opening. Each section has an Edit link to the
responsible step. Omitted optional data says “Not provided”; hidden required
data is never silently omitted. The primary action says **Create and activate**
or **Create, activate and post openings** according to the reviewed request.
“Save draft” is separate. Successful completion shows verified product/SKU IDs;
partial or uncertain completion shows existing receipts and safe next actions.

## 3. Field ownership, applicability, authority and validation

This matrix is a presentation contract. Native field-set metadata and the
target endpoint decide each field's exact read/write permission, configured
mode (disabled, optional, required), and allowed values. The UI never grants
access or makes a required field optional. `item.create` and
`product_configuration.read` are entry gates; referenced masters and later
native effects can require additional permissions. A required field denied for
read or write is a visible blocker naming the missing access, never an empty
hidden value. Server validation remains authoritative at Save, Preview and
Submit, including company/object scope and current source revisions.

| Step and input | Native owner | Show/require when | Validation and permission boundary |
|---|---|---|---|
| 1 Kind, profile name/code | Catalog | Always; kind/name required, code generated or entered | Company uniqueness and type/length rules; Catalog create/field policy. |
| 1 Published Product Type, primary group | Catalog | Always required | Active company-owned reference, kind compatibility, published revision; each reference read and field write policy. |
| 1 Description, descriptive custom fields | Catalog | Field metadata allows; required only if metadata says so | Typed length/value and field-level read/write; never authorizes money/stock behavior. |
| 1 Categories, scheme membership | Catalog | Configured schemes; required cardinality from scheme | Authorized active choices, scheme cardinality and company scope. |
| 1 Brand, series, model | Catalog | Independent configured modes; series only with Brand | Requiredness/defaults from effective configuration; company-scoped references and field policy. |
| 1 Manufacturer, site | Catalog | Goods and enabled; site follows manufacturer | Site belongs to selected manufacturer; reference read and field write policy. |
| 1 Shared attributes and variant axes/values | Catalog | Published Type requirements; axes only when company/type permit | Typed values, required axes, unique option keys and later SKU compatibility. |
| 2 SKU rows, code/name, variant signature | Catalog | One row always; more only for permitted variants | At least one SKU; company-unique code; one option per axis; no duplicate signature; Catalog create and field policy. |
| 2 Purchasable/sellable, base unit | Catalog | Always; at least one trade direction and base unit | Type-compatible unit dimension and native status/field policy. |
| 2 Sale/purchase units, packs, conversions | Catalog | Directions and configuration enable; required by policy when applicable | Exact conversion, active compatible revision and unit/pack reference permissions. |
| 2 Minimum quantity, barcode/GTIN, identifiers | Catalog | Numeric/identifier options and chosen pack allow | Positive grid-aligned quantity; identifier syntax and uniqueness, preserve leading zeros. |
| 2 SKU typed/descriptive attributes | Catalog | Type and field metadata allow/require | Typed native constraints; field-level read/write; descriptive fields do not control posting. |
| 3 HSN/SAC, tax treatment/rule | Catalog | Goods/Service and tax configuration require | Correct tax direction/classification and published native rule; tax reference access. |
| 3 Inventory profile, batch/serial/IMEI/expiry policy | Catalog definition; Accounting physical effects | Stock Goods and enabled/required capability | Published compatible profile; physical option and later Accounting permissions checked separately. |
| 3 Warranty, return, handling profile | Catalog | Configured and applicable Type/kind | Published compatible revision and profile read/field write policy. |
| 3 Purchase reference | Catalog | Purchasable and config requires/allows | Exact decimal amount, currency, unit, basis quantity and source revision. |
| 3 Named sale prices, MRP, optional dimensions | Catalog | Sellable with configured named levels; MRP Goods only | Required level coverage; exact decimal amount, currency/unit/tax basis; optional dimensions only if native option and permission permit. |
| 3 Replenishment, relationships, manufacturing requirements | Catalog or their native owner | Only if current policy needs them for readiness | Native readiness and owner permissions; otherwise named follow-up, not a fake wizard field. |
| 4 Opening choice, date, location, quantity, cost | Accounting/Vouchers | Optional eligible stock Goods only | Books-begin/period and location policy; exact quantity and cost; owner posting permission and preflight. |
| 4 Batch, manufacture/expiry, physical MRP | Accounting/Vouchers | Profile requires or allows batch tracking and opening selected | Batch uniqueness/date order/quantity/value; owner physical permissions. |
| 4 Serial/IMEI slots | Accounting/Vouchers | Profile requires or allows serial tracking and opening selected | Exact unit count, unique typed identifiers and owner permissions. |
| 4 Final review and command | Catalog coordinator plus native owners | All applicable sections reviewed | Server whole-draft preview; exact immutable body/idempotency key; per-owner receipts before claiming completion. |

All disabled/inapplicable input is removed from the submitted body. Changing
kind, type, configuration or a required reference presents a named impact
summary and asks the user to resolve affected fields. Optional values may be
cleared deliberately; required fields stay visible with their prerequisite.
No UI-only calculation becomes the authority for tax, price, quantity, stock
or readiness. The server returns field paths that map to step and SKU labels.

## 4. States, recovery and interaction copy

| Event | Visible behavior and wording |
|---|---|
| Enter step with options loading | Keep heading and structure; show field placeholders, disable dependent choices and Continue. “Loading available product options…” |
| No allowed choices for required reference | Inline blocker with owner and permitted next action. “No published Product Type is available for Goods.” |
| Save draft pending/success/failure | “Saving draft…” then “Draft saved at {formatted time}”; on failure keep values and show “Draft could not be saved. Retry.” |
| Navigate with unsaved edits | Offer Save, discard changes, or remain; do not lose input through Back, step Edit or browser refresh. |
| Field or whole-draft invalid | Error summary names step/SKU, links to field, sets focus; inline error says what to fix. Preserve all other input. |
| Mode, company or source revision changes during draft | Freeze submit, retain draft, refresh native options and show changed sections. “Product setup changed. Review these fields before continuing.” Never silently switch a mounted wizard to Simple. |
| Submit pending | Lock exact reviewed body/key; “Creating your product. You can safely return to this progress view.” |
| Definitive rejection before effects | Show native blockers with links; edit draft and submit a new reviewed intent only after rejection is confirmed. |
| Response unknown | “We are checking the result. Please do not create another product yet.” Poll/read existing intent; only safe advance of that intent. |
| Some owner work complete | Name completed SKUs/openings and pending action; “1 of 2 openings posted. Continue the remaining opening.” Never imply rollback. |
| All requested work verified | “Product Profile and {N} SKUs created.” Link to permitted product view and Create another. |

Formatting uses resolved company date, amount and quantity settings. Data entry
uses labels, help and examples next to the field; validation identifies the
specific SKU. Status never relies on colour alone. Save and Continue are
distinct actions, with one primary action per step.

## 5. Accessibility and acceptance examples

The stepper exposes current step and completed steps; headings and fieldsets
make the hierarchy navigable. Every input has a persistent label and required
state. Conditional content announces its arrival without stealing focus.
Errors use a summary plus field association; after Continue fails, focus the
summary, and its links focus the field. Confirmation for destructive draft
changes has an explicit choice. Keyboard order follows reading order in all
widths and themes. At 200% zoom and 320/390/768/1440 px, content reflows with
no horizontal page scroll or obscured controls. Screen readers get SKU names
and status as text, not just badges or icons.

Acceptance examples for the Phase 7 matrix:

1. Simple mode: one Simple card, Simple form at direct URL; no Advanced choice.
2. Advanced mode with variants disabled: Advanced card and four steps, exactly
   one SKU, no variant axes or Add SKU; optional stock opening when eligible.
3. Advanced Goods with variants: explicitly add two signatures; duplicate
   signature is named and blocked; no generated combinations.
4. Advanced Service: SAC and applicable prices, no inventory or opening editor.
5. Batch/serial Goods: only fields allowed by published profile and company
   capabilities; quantities/identifiers reconcile in native preflight.
6. Missing permission or failed mode read: no actionable creation card and
   no form mounted from the direct URL.
7. Configuration changes mid-draft: draft survives, final submission waits for
   refreshed options and explicit review.

## 6. Phase 0 review notes and remaining implementation decisions

The contract makes mode, card, route and final submission behavior explicit.
Its matrix covers field owner, applicability, permission boundary and native
validation; actual option values and permission results must be supplied by
Catalog/native owners, never copied into the client. The implementation phases
must settle aggregate SKU bounds, opening location and batch price owner
contracts before those endpoints ship. Draft expiry, deletion and resume actor
scope must be decided before Phase 1 persists drafts. Record those decisions
in the plan and TODO when resolved.

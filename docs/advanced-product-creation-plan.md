# Advanced Product Profile and SKU creation

Saved 2026-11-04. This is an implementation plan, not an implementation record.
The user requested a new, clear and polished four-step experience for non-Simple
products, with a file-level plan covering fields, features and styles. On
2026-11-04 the user authorized phase-wise delivery with review after **every**
phase and explicit confirmation before starting the **next** phase. Track that
gate in [the implementation TODO](advanced-product-creation-todo.md). The
reviewed entry, field and interaction contract is in
[the UX contract](advanced-product-creation-ux.md). Phase 1 implementation and
review evidence are in [the execution record](advanced-product-creation-phase1.md).

## 1. Scope and decisions

- A **Product Profile** is the Catalog `product_family`: shared identity,
  classification and variant definition. A **SKU** is an `item`: the actual
  purchasable or sellable record with units, prices, identifiers and stock rules.
- Keep `/masters/items/new` as the creation entry. When the verified current
  `product_family_sku_enabled` company control is true, show the new Advanced
  wizard; when false, retain the existing Simple Product experience. If the
  control cannot be read, block creation with a retryable explanation.
- The product directory shows one configuration-selected creation card and one
  primary action. Simple mode advertises and launches Simple Product creation;
  Advanced mode advertises and launches Product Profile + SKUs. The direct
  `/masters/items/new` route verifies the same current mode before rendering.
  Do not present a free choice between the two modes or infer a mode from
  `variants_mode`, a cached directory, or a failed configuration read.
- Build new product-specific UI and presentation state. Reuse the existing
  `@janso/ui` controls, tokens, themes and Console shell. The retired advanced
  create/edit/detail components are historical, not the new implementation.
- Keep four visible steps. Sections inside them follow current Company Product
  Configuration, Identity capabilities, published Product Type rules, native
  metadata, authorized reference options and field permissions.
- Let the user save a wizard draft from every step. Final submission is from the
  review, after whole-draft validation. A submitted intent and its command keys
  are immutable while its result is uncertain or partially complete.
- A non-variant profile has one SKU. A variant profile contains only explicitly
  selected SKU combinations; never generate the whole Cartesian product.
- Catalog owns family/SKU definitions, profiles, tax and price definitions.
  Accounting owns stock/value and physical batch/serial facts; Vouchers owns the
  opening document lifecycle. No remote call occurs inside a money transaction.
- Save/activation/opening may span owner transactions. Completion means every
  requested SKU and optional opening has a verified native receipt. Partial
  progress is shown truthfully and resumed without duplicate effects.
- Related masters needed for activation are selected or created through their
  authorized native flows. Optional supplier terms, relationships and BOM work
  can be offered as next actions after creation. If a selected type or policy
  requires one, show the native readiness blocker before activation.

Current references: [product design](catalog-product-design.md),
[company-only configuration](catalog-product-configuration.md),
[authoring mode](simple-product-api.md),
[retired UI](product-ui-removal.md),
[existing native authoring](catalog-v12-api.md),
[activation](catalog-v14-api.md), and
[Simple opening](simple-product-batch-opening-plan.md).

## 2. Four-step field and feature contract

### Step 1: Product Profile

| Field or section | Scope and rule |
|---|---|
| Kind | GOODS or SERVICE; required; controls type, tax, unit and physical-field applicability. |
| Profile name and code | Required identity; offer a unique generated code when left blank, retaining leading zeros in entered codes. |
| Product Type | Required published revision compatible with kind; show its allowed unit dimensions, required attributes, inventory modes and variant eligibility. |
| Primary group | Required company-owned active group; category memberships are separate classification. |
| Description and descriptive custom fields | Optional when readable/writable; custom fields never control money, tax or stock. |
| Brand, series and model | Configuration modes control availability and requiredness; series needs Brand, while Model is independent. |
| Categories | Show configured schemes and cardinality; a required scheme must have valid membership. |
| Manufacturer and site | Goods only; site requires its manufacturer; do not treat manufacturer as supplier. |
| Variant axes and allowed values | Only when company mode, configuration and Product Type permit; use native typed attributes and published options. |

### Step 2: SKUs and units

| Field or section | Scope and rule |
|---|---|
| SKU rows | At least one; explicit add, duplicate, rename and remove actions before submission. |
| SKU code and name | Unique within company; offer a generated code; preserve entered values and leading zeros. |
| Variant signature | Exactly one selected option per declared axis; duplicate combinations rejected. |
| Purchasable / sellable | At least one true; reflect type and native policy. |
| Base unit and quantity rules | Required; exact decimal precision/increment from the selected unit and effective numeric defaults. |
| Sale/purchase units and packs | Optional or required by configuration; exact compatible conversions and revision dates. |
| Minimum sale quantity | Optional positive quantity on the native unit grid. |
| Barcode/GTIN and other permitted identifiers | SKU or pack-specific; preserve strings and leading zeros; enforce format and company uniqueness. |
| SKU attribute values and custom fields | Native typed requirements plus separately authorized descriptive custom fields. |

Desktop uses a scannable SKU list with one expanded editor. Phone layouts use
stacked SKU cards with an always-visible name, code, variant signature and
completion state. A change to shared axes or Product Type revalidates all SKU
rows without silently clearing them.

### Step 3: Business setup

| Field or section | Scope and rule |
|---|---|
| Tax | Goods HSN or Service SAC, applicable native classification/treatment/rule and SALE/PURCHASE directions; never infer tax from name or price. |
| Inventory profile | Stock Goods only; select a published revision. Batch, serial/IMEI, expiry, issue strategy and valuation follow that revision and company capabilities. |
| Warranty, return and handling | Published revisions when configured and applicable; show the selected terms in plain language. |
| Purchase reference | Exact amount, company currency, pricing unit and basis where required. |
| Selling prices | Active named price levels; required coverage is distinct from permission to add levels. Display one ordinary field when only one level applies. |
| MRP | Goods only, when enabled; preserve its distinct tax basis and source. Physical batch MRP belongs to the batch opening. |
| Extra pricing | Unit/pack prices, tiers, channels, additional currencies and native formulas only when their explicit configuration and company capabilities permit them. |
| Replenishment, relationships and manufacturing | Show only native, applicable setup required for readiness. Otherwise give a clearly named follow-up action after creation. |

Each SKU has a readiness summary and direct Edit action. Prices are exact decimal
strings with declared currency, unit, basis quantity, numeric revision and source.
Draft price definitions are never labelled live. Activation checks every required
level, tax binding, unit rule, profile and policy through the native owner.

### Step 4: Opening and review

| Field or section | Scope and rule |
|---|---|
| Opening choice | Optional for eligible stock Goods; unavailable for Services and non-stock Goods. |
| Date, location, quantity and cost | Company books-begin date and allowed native location policy; per-SKU exact quantity and purchase cost. Show calculated carrying value separately. |
| Batches | When selected/required: code, manufacture/expiry dates, quantity, batch prices and immutable initial physical MRP where applicable. |
| Serials/IMEIs | When selected/required: typed identifier and slot values per physical unit, optionally nested under batches; quantity equals physical-unit count. |
| Final review | Profile, each SKU, applied defaults, prices, profiles, tax and opening; show omitted optional sections as not provided and every blocker with an Edit link. |

Accounting/Vouchers readiness is checked before offering a postable opening.
One opening may complete while another SKU's opening waits; the progress view
must preserve those verified results and offer only safe continuation. The final
primary action says exactly what it will do, such as **Create and activate** or
**Create, activate and post openings**. **Save draft** remains separate.

## 3. Applicability, permission and error rules

| State | Wizard behavior |
|---|---|
| DISABLED or inapplicable | Omit new input; server rejects an incompatible submitted value. |
| OPTIONAL | Start from configured default, allow deliberate enable/disable, require dependent fields when enabled. |
| REQUIRED | Display enabled and locked; show missing prerequisite and its owner. |
| Field read/write denied | Respect server metadata; a required denied field blocks submission rather than being treated as empty. |
| Missing reference or stale source | Preserve entered draft; explain what changed and require refreshed review. |
| Definitive validation failure | Return to responsible step/SKU, show a summary and focus the exact field. |
| Uncertain response | Freeze the submitted body/key; read or advance its existing intent before allowing another mutation. |
| Partial owner completion | Show completed IDs and outstanding actions; never claim rollback of posted stock or prices. |

No client switch is an authorization rule. All company, object and field checks
remain native, including replay. Descriptive custom fields never determine
posting, pricing, tax or permissions.

## 4. Proposed file-level work

Paths marked **create** are proposed, not present now. Exact migration numbers
must be selected from the next free revision at implementation time because
other work may add revisions concurrently.

### Catalog options, drafts and command state

| Action | Path | Responsibility |
|---|---|---|
| Create | `apis/catalog/src/catalog/api/advanced_product_creation.py` | Scoped options, draft CRUD, preview, submit, status and safe advance endpoints. |
| Create | `apis/catalog/src/catalog/schemas/advanced_product_creation.py` | Strict Profile/SKU/setup/opening input, options, preview, status and field errors. |
| Create | `apis/catalog/src/catalog/tasks/advanced_product_options.py` | Effective configuration, capability, type/profile, price-book and permission-aware options with source versions. |
| Create | `apis/catalog/src/catalog/tasks/advanced_product_drafts.py` | Actor/company-scoped save and resume, optimistic versioning and explicit review after source changes. |
| Create | `apis/catalog/src/catalog/tasks/advanced_product_validation.py` | Whole-draft compatibility and field-path mapping; server owns validity. |
| Create | `apis/catalog/src/catalog/models/advanced_product_draft.py` | Pre-submission draft snapshot; JSON is transport state, not a domain authority. |
| Create | `dbs/catalog/versions/<next>_advanced_product_draft.py` | One `CREATE TABLE`, guarded downgrade. |
| Create | `apis/catalog/src/catalog/models/advanced_product_creation.py` | Immutable submitted hash, progress, SKU IDs, exact owner receipts and lease. |
| Create | `dbs/catalog/versions/<next>_advanced_product_creation.py` | One `CREATE TABLE`, guarded downgrade. |
| Edit | `apis/catalog/src/catalog/main.py`, `models/__init__.py`, `metadata.py` | Register API/model and align readiness with migrations. |
| Edit if new events | `apis/catalog/src/catalog/events/audit_contract.py`, `apis/catalog/contracts/audit-events.json` | Add versioned state-change audit/outbox contract and consumers. |

### Catalog native definition, setup and activation

| Action | Path | Responsibility |
|---|---|---|
| Create | `apis/catalog/src/catalog/tasks/advanced_product_creation.py` | Bounded, idempotent Catalog transaction for family, axes and explicit SKU definitions. |
| Create | `apis/catalog/src/catalog/tasks/advanced_creation_steps.py` | Per-SKU setup, price publication and activation with retained command receipts. |
| Create | `apis/catalog/src/catalog/tasks/advanced_creation_readiness.py` | Step/SKU-labelled preview and activation blockers. |
| Edit | `apis/catalog/src/catalog/tasks/products.py`, `product_initial.py`, `product_attributes.py` | Reuse native checked creation, attributes and initial setup inside the aggregate; preserve existing routes. |
| Edit only for verified gaps | `apis/catalog/src/catalog/tasks/profile_bindings.py`, `product_requirements.py`, `activation.py`, `activation_prices.py`, `pricing_publication.py` | Apply and verify selected native profiles, required prices and active source facts. |
| Edit | `apis/catalog/src/catalog/schemas/products.py`, `product_initial.py` | Add bounded advanced aggregate input while keeping existing default-SKU requests compatible. |

Catalog definition creation is one transaction: a rejected SKU leaves no new
family or SKU from that command. Subsequent publication, activation and stock
effects are separately recorded stages; the coordinator does not pretend they
share that transaction.

### Opening owner integration

| Action | Path | Responsibility |
|---|---|---|
| Create | `apis/catalog/src/catalog/tasks/advanced_creation_transport.py` | Bounded owner calls, exact keys, receipt validation and safe retry classification. |
| Create | `apis/catalog/src/catalog/tasks/advanced_creation_opening.py` | Per-SKU preflight, lot/serial preparation, posting and reconciliation. |
| Review/extend if needed | `apis/accounting/src/accounting/api/stock_opening.py` and native stock-opening tasks | Use existing product opening, calculation, manifest and finalization authority. |
| Review/extend if needed | Vouchers stock-opening/lifecycle APIs | Use existing issue/post flow and approval policy; change contracts only for a verified gap. |

No Accounting or Vouchers table or migration is planned merely to add the
wizard. Any proven owner contract change must ship with its own service model,
schema, migration, test factory and generated client update.

### Console route, components and data policy

| Action | Path | Responsibility |
|---|---|---|
| Create | `mfes/apps/console/app/components/ProductCreationExperience.tsx` | Verified mode switch for Simple or Advanced creation, including loading/failure state. |
| Create | `mfes/apps/console/app/components/AdvancedProductWizard.tsx` | Four steps, navigation, draft save, preview, immutable submit and progress. |
| Create | `mfes/apps/console/app/components/AdvancedProfileStep.tsx` | Step 1 identity, classification and variant axes. |
| Create | `mfes/apps/console/app/components/AdvancedSkuStep.tsx` | Step 2 explicit SKU builder and unit/identifier controls. |
| Create | `mfes/apps/console/app/components/AdvancedSkuCard.tsx` | Compact repeated SKU editor with completion and duplicate feedback. |
| Create | `mfes/apps/console/app/components/AdvancedSetupStep.tsx` | Step 3 per-SKU tax, profiles and prices. |
| Create | `mfes/apps/console/app/components/AdvancedOpeningReviewStep.tsx` | Step 4 opening and full editable review. |
| Create | `mfes/apps/console/app/components/AdvancedCreationProgress.tsx` | Verified complete/needs-action/uncertain result and next actions. |
| Create | `mfes/apps/console/app/lib/advanced-product-draft.ts` | Typed draft state and deliberate dependent-field changes. |
| Create | `mfes/apps/console/app/lib/advanced-product-applicability.ts` | Presentation mapping from native metadata; never permission authority. |
| Create | `mfes/apps/console/app/lib/advanced-product-api.ts` | Generated-client shaped calls and retained idempotency keys. |
| Create | `mfes/apps/console/app/lib/advanced-product-errors.ts` | Server field path to step/SKU/error summary/focus. |
| Create | `mfes/apps/console/app/lib/advanced-product-policy.ts` | Narrow allowlist for proposed native routes. |
| Edit | `mfes/apps/console/app/components/ProductCatalogPage.tsx`, `ProductModeProvider.tsx`, `ProductCatalogDirectory.tsx` | Route creation by verified company mode; show the correct entry and destination. |
| Edit | `mfes/apps/console/app/components/SimpleProductDirectory.tsx`, `ProductExperience.tsx` | Keep Simple and Advanced directory creation cards consistent with the verified mode. |
| Edit | `mfes/apps/console/app/lib/product-request-policy.ts`, `master-navigation.ts` | Register allowlist and navigation; keep unrelated service paths closed. |
| Review/extend | `mfes/apps/console/app/api/product-fields/route.ts` | Check bounded body size and timeout for submitted requests. |
| Create if status needs a bookmarkable URL | `mfes/apps/console/app/masters/items/creation/[creationId]/page.tsx` | Resume only the actor/company-owned creation status through the normal session shell. |

Keep `/masters/items/new` under the existing dynamic master route; no second
creation URL is required. A status URL may be added so a refresh or another
session can resume a submitted operation safely.

### Styles and shared UI

| Action | Path | Responsibility |
|---|---|---|
| Create | `mfes/packages/ui/src/styles/product-wizard.css` | Product-scoped rail, form, SKU cards, summary, progress, responsive and focus styles. |
| Edit | `mfes/packages/ui/package.json` and `mfes/apps/console/app/layout.tsx` | Export/import the stylesheet once; bump UI version and consuming lockfile. |
| Edit only if needed | `mfes/packages/ui/src/styles/tokens.css`, `setup.css` | Add reusable semantic tokens or fix a shared primitive, not product-only values. |
| Reuse | `Stepper`, `Card`, `FieldGroup`, `SearchSelect`, `ReviewList`, `Notice`, `ConfirmDialog` | Shared controls, accessible names, focus and theme behavior. |

The existing `WizardLayout` owns a full viewport and its own scroll container.
Do not nest it unchanged inside `ConsoleShell`. Compose the new product layout
from shared primitives in the shell's scroll region, or add a reusable
within-shell variant if a second application needs the same behavior.

Visual rules: clear title and company context, four-step progress, readable
content width, generous token-based spacing, subtle card grouping, one primary
action, SKU-specific status text and icons, tabular money figures, visible focus,
and a sticky action area that never covers focused fields. Desktop uses a step
rail and broad SKU editor; tablet uses compact progress; phone uses one-column
cards. All three shipped themes must look intentional. No hardcoded palette or
ad-hoc component stylesheet in Console.

### Generated contracts and tests

| Action | Path | Responsibility |
|---|---|---|
| Regenerate | `apis/catalog/openapi.json`, `clients/api-client/src/catalog.d.ts` | Keep API, generated TypeScript and Console consumers synchronized. |
| Update | `clients/api-client/package.json`, client and MFE lockfiles | Version the changed client and preserve frozen installs. |
| Create | `apis/catalog/tests/test_advanced_product_options.py`, `test_advanced_product_drafts.py`, `test_advanced_product_creation.py`, `test_advanced_product_creation_mysql.py`, `test_advanced_product_security.py` | Config matrix, two-tenant isolation for each new table, rollback, replay, native MySQL and permissions. |
| Create | `apis/catalog/tests/test_advanced_product_opening.py` | Owner responses, exact value, closed period, partial posting and recovery. |
| Create | `mfes/apps/console/tests/advanced-product-wizard.test.tsx`, `advanced-product-applicability.test.ts`, `advanced-product-recovery.test.tsx`, `advanced-product-layout.browser.test.tsx` | Four steps, field conditions, errors, navigation, themes and responsive layout. |
| Edit | `mfes/apps/console/tests/product-mode-provider.test.tsx`, product directory/route tests | Preserve Simple mode and guard unknown mode. |

If a shared UI component changes, add its own unit tests in
`mfes/packages/ui/tests/`. Backend tests cover authenticated success, 401, 403,
wrong-company access, 422, replay and tenant filtering. Money and quantity tests
assert exact `Decimal` types and closed-period rejection.

## 5. Delivery phases and exit gates

| Phase | Deliverable | Exit gate |
|---|---|---|
| 0. Contract and UX | Field matrix, command states, four-step wireframes and reviewed wording. | Every field has owner, applicability, permission and validation; no hidden required input. |
| 1. Options and drafts | Native wizard context and server-backed draft/resume. | Source change, actor/company isolation and field-denial tests pass. |
| 2. Catalog aggregate | Profile and explicit SKU definitions in one Catalog transaction. | Duplicate/rollback/replay tests pass; no partial definition on rejection. |
| 3. Setup and activation | Tax, profile, unit and price publication with per-SKU readiness. | Required coverage and native activation tests pass. |
| 4. Opening orchestration | Optional per-SKU stock opening and retained cross-owner progress. | Exact valuation, one effect on replay and partial-failure recovery pass. |
| 5. UI shell and steps 1-2 | New in-shell layout, profile and SKU builder. | Desktop/mobile/theme/keyboard and draft navigation checks pass. |
| 6. UI steps 3-4 | Setup, opening, review, submit and progress. | Whole-draft error focus, uncertain retry and truthful completion checks pass. |
| 7. Integration and release | Contracts, native schema rehearsal, full scenario matrix and current-mode routing. | Affected tests, TypeScript, Ruff, strict mypy, API client, security/correctness review and Simple regression checks pass. |

Each phase leaves the repository working with affected tests green. A model
change includes its matching migration, Pydantic schema, test factory and
regenerated client in the same phase. Every MySQL migration is reviewed line by
line and has one DDL statement per revision with a working or justified
downgrade. Apply live migrations only after private backup and native rehearsal;
verify all service heads again before reporting alignment.

After each phase, review its changed files against `CLAUDE.md` sections 5 and
6, record findings and verification in the TODO, and stop. Do not start the
next phase until the user explicitly confirms it. A phase plan or a passing
test does not itself authorize the next phase.

## 6. Release scenario matrix

Verify at least: Service, non-stock Goods, one-SKU Goods, explicit variants,
required Brand/category/manufacturer/attributes, multiple required and optional
sale levels, unit/pack pricing, batch, serial-only, batch plus serial/IMEI,
expiry, missing published reference, denied field, changed Company configuration,
duplicate SKU, lost response before/after Catalog commit, and failure after one
SKU's opening has posted. Test at 320, 390, 768 and 1440 pixel widths, 200%
zoom and light/dark/ledger themes with keyboard and screen-reader checks.

The design follows [W3C multi-page form guidance](https://www.w3.org/WAI/tutorials/forms/multi-page/)
for logical steps and progress, [W3C notification guidance](https://www.w3.org/WAI/tutorials/forms/notifications/)
for error/success feedback, and the [GOV.UK check-answers pattern](https://design-system.service.gov.uk/patterns/check-answers/)
for an editable final review. The native owners remain the final authority for
scope, tax, money and stock correctness.

## 7. Decision log and implementation review points

- 2026-11-04: The user selected a new, four-step, configuration-driven Advanced
  Product Profile/SKU creation experience and requested this detailed file-level
  plan be saved. The plan was documentation only when first saved.
- 2026-11-04: The user authorized phase-wise execution, with a review after
  each phase and user confirmation before the next. Product creation entry
  cards and `/masters/items/new` must both follow verified current company
  authoring mode. Phase 0 defines this contract; subsequent phases implement it.
- Use the current company-owned Product Configuration and the separate current
  `product_family_sku_enabled` control. Product Type and native authorities still
  narrow valid choices. Keep Simple Product creation working in its current mode.
- Before implementation fixes request limits and schemas, confirm the native
  bounds for an aggregate SKU command and the owner contracts for a selectable
  opening warehouse, batch prices and any required manufacturing/BOM setup.
- 2026-11-04, Phase 1: An unsubmitted wizard draft belongs only to the
  initiating actor and company. It has no automatic expiry; the owner can
  explicitly delete it with a matching row version. Deletion erases the draft
  row while its audit marker remains. Limit each actor to 20 saved drafts per
  company, 64 KiB and 64 explicit SKUs per draft. Phase 2 must use the same or
  a stricter native aggregate command bound. A draft is transport state, never
  a product, price, tax or stock authority. Submitted operation receipts must
  remain durable for recovery and audit.
- 2026-11-04, Phase 2: One submitted native definition command accepts at most
  64 explicit SKUs and 64 KiB of normalized JSON. The first SKU occupies the
  default slot. More SKUs for the same family must be added later through the
  existing bounded native variant command; the wizard must state this limit
  before submission. A submission retains its canonical request, hash, actor,
  family/SKU IDs and stage receipt. Product Profile, attributes and every SKU
  either commit together or leave no new definition or receipt. Setup,
  activation and opening are subsequent native stages, not part of this
  definition transaction. See [the Phase 2 review](advanced-product-creation-phase2.md).
- 2026-11-05, Phase 6 continuation: Every Advanced SKU needs a dated BASE unit
  binding before native price setup or activation. An opening uses the signed
  company's books-begin date, so that binding starts by that date when opening
  is requested. The native initial setup allows eight bindings in total:
  BASE plus up to seven alternates. Batch named prices belong to the existing
  Catalog/Accounting opening owner path recorded in Phase 4. Current native
  Product Type readiness has no mandatory manufacturing/BOM rule; show it as a
  follow-up until a native requirement and owner contract exist. See the
  [Phase 6 continuation review](advanced-product-creation-phase6-review.md).

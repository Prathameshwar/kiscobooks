# Products and classification UI delivery

Scope: Products/SKUs, product families, product types, category schemes, categories,
brands, brand series and manufacturer sites. Reuse the existing console layout,
shared controls, tokens and CSS. Company permissions and native field metadata are
authoritative. Preserve versioned commands, idempotency and reviewed publication.

## Phases

1. Map native contracts, field controls, scoped searchable references and the BFF
   allowlist. Keep models, migrations, OpenAPI and SDK contracts aligned.
2. Deliver the six classification directories, create/edit/detail screens, lifecycle,
   hierarchy changes, reviewed scheme transitions and product type revisions.
3. Deliver family/SKU directories and authoring, classification links, related records,
   configuration/attributes navigation and explicit readiness/activation workflows.
4. First review: native workflows, permissions, scope isolation, version conflicts,
   validation and uncertain-write recovery. Fix findings and rerun focused checks.
5. Second review: professional presentation, navigation, responsive layouts, keyboard
   accessibility, integration and regression checks. Fix findings and recheck.

## Verification ledger

Phases 1–3 are implemented. All eight resources use company-scoped native commands,
shared page navigation, directories, searchable references, metadata-driven forms,
validation, success/error messages and permission-aware record actions. Product types
include draft requirements and immutable publication. Schemes include reviewed impact
transitions; families include complete dated category selections and atomic family/SKU
creation. SKU details link setup, attributes, effective configuration and readiness.

First review findings fixed:

- Interrupted preview requests now retain and replay their exact request and key.
- Ineligible activation reviews offer a usable review-again step.
- Cancelling an interrupted publication closes its dialog while retaining publication
  recovery; draft saves cannot accidentally replay publication.
- Product creation and editing use their separate native permissions.
- Category changes fail closed when complete membership or required field authority
  cannot be verified.

Second review findings fixed:

- Requirement checkbox groups reuse the existing fieldset reset and wrapping/gap
  styles, removing the browser border and cramped labels.
- Country/state labels, directory headers and required-field guidance are clearer.
- Unit revision metadata failures have a visible error and retry both field sets.
- SKU activation uses its own permission independently of descriptive editing.
- Service SKU configuration links preserve the family kind; direct product-attribute
  visits also require scoped native item read permission.
- Subsequent cursor pages show the returned count instead of a false first-page range.
- Family filters use the native `product_type_revision_id` contract and the status
  lifecycle; draft family choices no longer send an unsupported `is_active` filter.
- Unsupported resource casing and invalid mixed family kinds fail closed.
- Next.js's generated page contract exposed an optional-argument mismatch on the
  attributes route. The entry point now accepts required page props, retaining
  validated SKU/return query forwarding; its 24 page/editor regressions pass.

Keyboard selection, Escape focus, direct SKU attribute navigation, interrupted writes,
native DTO aliases, exact ratios/quantities and denied-field retention have regression
coverage. A browser review of actual shared CSS/components with isolated API fixtures
passed 150 desktop/mobile checks across light, dark and ledger themes; screenshots
are in the ignored `.tools/product-classification-review` directory.

Manual simplification/security review: shared references, custom fields and command
recovery are reused. No additional unresolved findings from the scoped route allowlist,
company grants, field authority, frozen requests, version/receipt verification or safe
return navigation. Publication/activation retain native audit and idempotency behavior.
No additional tables, migrations, dependencies or CSS were introduced.

Final regression verification: **2,409 Console tests across 160 files passed**.
After the last three contract corrections, **122 focused tests across eight files
passed**, including direct page grants, keyboard navigation and actual native-shaped
filter requests. Native Catalog regression: **74 passed**. Console/SDK TypeScript,
Catalog Ruff and strict mypy, OpenAPI freshness, generated Catalog client freshness
and all **eight SDK transport tests** passed. SDK version is `0.2.22`.

Read-only local schema audit: migration, database and readiness heads all equal
`0191`; all **164** model tables match, with no missing/extra tables and no Alembic
changes. Catalog was reloaded through its managed launcher and is ready on 8003.
All eight live master contracts and unauthenticated API/BFF rejection were verified
without creating or changing business records. The separate Design service remains
outside this delivery and its local readiness was already unavailable.

The final browser recheck also passed all **150 checks**, with no browser errors
or page overflow. The production build passed after the generated Next.js page-type
correction, and the managed Console was restored to `UP` on 4320. All five phases
and both review/fix passes are complete. The core master inventory now has two
pending categories: exchange rates and charge policies.

Browser workflows use isolated intercepted fixtures and the actual shared UI/CSS;
native authenticated workflows use isolated databases. Live business data remained
unchanged throughout verification. Completed Catalog/master work is published through
the configured `git publish` mapping; concurrent unfinished Design changes remain local.


## Product master experience refinement (2026-10-27)

The product directory, creation, editing and detail screens received a further live
experience review. Compact reference filters, grouped form/footer layout, readable
facts, active area/section navigation, readiness repair links, accessible field
instructions and correctable create conflicts reuse the shared design system.
See [product master experience review](product-master-experience-review.md) for
findings, fixes, native/API verification and the exact draft-product test scope.


## Four-step product creation (2026-10-27)

New product creation now uses the four-step flow in
[product-creation-wizard.md](product-creation-wizard.md). The existing family/SKU
command accepts optional bounded initial setup, reusing native handlers within the
same transaction and retaining current company, field and purpose-aware permissions.
The receipt optionally returns up to three created price draft IDs for bounded detail
readback. Opening quantity/value remain outside Catalog. Prices remain drafts until
published, and product activation still requires the existing readiness review.

Decision: identical effective configuration may be accepted after an Identity source
refresh only when the new create-specific fingerprint matches under the policy lock.
Changed policy generations or values still block creation. Completed replays recheck
authority and return the receipt without repeating creation preconditions.

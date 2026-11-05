# Product and company configuration consumption

Decision 2026-10-30 supersedes the earlier hierarchy: current/proposed defaults
consume Company configuration only; type/group/family/SKU configuration scopes
are retired. Native product context and hard constraints still apply. Existing
adoption pins resolve immutable historical sources internally until a supported,
reviewed draft adoption accepts the current Company revision. Profile clearing
and explicit company profile choices override optional native defaults for new
configuration; original historical pin ordering is preserved. See the
[company-only plan](company-only-product-configuration-plan.md).

The follow-up [consumer review](company-product-configuration-consumer-review.md)
adds Catalog 0214 and a server-controlled adoption resolution version. New
version 2 pins retain reviewed Company choices in all SKU consumers; old version
1 pins retain their original semantics. Preview evidence includes the marker and
the UI rejects missing/old/unsupported markers. Publication validates native
constraints of the configured default goods/service type. This additive change
does not alter saved units, prices, active snapshots or financial source facts.

Plan and gap audit, 2026-10-25. User authorization covers investigation followed by implementation for product masters and their supporting configuration; existing CSS, controls and layout are retained.

## Findings

The native service already resolves company/type/dated group/family/SKU inheritance and adopted SKU configuration. It also offers authoring defaults, exact unit-grid suggestions and versioned acceptance. Product UI mostly consumes generic field metadata and fixed initial values instead. Native readiness/activation is therefore stricter than the controls used to prepare a product.

| Area | Gap | Intended behavior |
|---|---|---|
| New families/SKUs | Published configured type defaults are not offered | Resolve by company date/kind; explicitly apply valid writable suggestions; preserve user overrides and accept native defaults with their receipt when appropriate |
| Brand/series | Fields do not reflect effective requiredness/prohibition | Use resolved policy with native field permissions; retain existing values and explain restrictions |
| Categories/manufacturers/barcodes/variants | Setup offers prohibited actions or misses optional defaults | Required is on; optional starts from its resolved default and permits explicit opt-in; disabled blocks new assignments, while history remains readable |
| Unit bindings | Fixed precision/increment and simultaneous fixed/measured inputs | Resolve native numeric defaults for the actual SKU/unit/date; explicitly apply the exact suggestion; condition conversion controls and invalidate stale acceptance |
| Product types/profile templates | Capability choices ignore company inventory/tracking flags | Native company-aware presentation hints restrict new choices; existing configuration/binding/activation checks enforce capability compatibility when a library definition is used; retain historical values |
| Failures and updates | Configuration loading/failure/change can leave misleading actions/defaults | Verify company/date/ownership, block dependent submissions while unresolved, expose reload/navigation, and preserve dirty values until an explicit review |

## Phases

1. Add tested native presentation hints for affected product-type/profile controls. Reuse verified Identity projections and existing feature keys; synchronize OpenAPI and the generated Catalog client. Existing native configuration/profile binding checks enforce capabilities when a library definition is used; reusable library preparation remains available. No schema/model/migration, command-policy or permission-catalogue change is planned.
2. Add a single application policy/default-consumption layer and wire product creation/edit, supporting setup, category/attribute/variant workflows and revision controls to it. Reuse existing native effective/authoring-default APIs, metadata, exact values, shared form controls and draft navigation guards.
3. Run affected backend/frontend regressions, verify default/prohibition/optional and field-denial branches, perform simplification/security review and fix findings. Inspect desktop/mobile themes and build/restart Console and the changed native service as needed.

Published/adopted product sources remain authoritative. New company defaults never silently rewrite existing products or financial facts. Feature enablement does not grant permissions; field denies remain server enforced. Global master libraries retain their own management routes independently of a particular product's optional choices.

## Evidence

All three implementation phases are complete locally. The existing Company settings entry and product configuration links are retained.

- Catalog verification: 32 distinct tests passed across configuration consumption, authoring defaults/version acceptance, classification/profile metadata, profile authoring, and unavailable-source behavior (31 in the main run; the three final control tests include two repeated tests).
- Console verification: 465 tests passed in 25 files. The final history regression tests first failed for disappearing tracking/conversion values, then passed with explicit retained-value presentation and field-grant protection.
- Browser verification: 92 checks passed at 1440px and 390px in light, dark and ledger themes; no browser errors. Six writes used isolated fixture data; no live business records were written.
- Ruff, strict mypy for changed Catalog modules, generated Catalog client verification, OpenAPI verification, SDK type checking and final Console type checking passed. The final production build exited successfully after the history correction; the managed Console restarted and is ready on port 4320.
- Catalog was reloaded through the existing managed launcher and verified ready on port 8003.

Review one corrected optional-default consumption, configuration context changes, exact default receipts, and the distinction between library preparation and product assignment. Review two corrected disappearing historical selections and the outdated expectation of a duplicate configuration menu entry. Manual simplification and security review found no remaining field-grant escalation, cross-company default acceptance, automatic history rewriting, or new command/idempotency policy. The unavailable `/simplify` and `/security-review` commands were covered manually.

Compound quantity policy applies to submitted quantity components rather than the existence of multiple unit bindings. Existing native quantity-preview validation already enforces it; this master UI work does not add transaction-entry screens. Pricing currencies and profile selection continue to use their existing verified native option APIs. Company feature hints govern allowed tracking and pricing capabilities; effective product configuration governs attaching supporting choices to a specific product.

No ORM model, database schema, seed, migration or startup-script change was needed. The response hint is synchronized in Catalog OpenAPI and `@janso/api-client` 0.2.26. Existing field permissions and native mutation checks remain authoritative.

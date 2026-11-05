# Product configuration UI and option controls

Authorized by the user's 2026-11-04 request to review Product Configuration UI,
CSS, layout and navigation and control unit conversion, Brand and Model here.
Simple creation is delivered separately in [the ready-on-Save plan](simple-product-ready-plan.md).
Product edit/detail, advanced authoring and batch/serial pages remain deferred.

## Phases

1. Add a native Model option for the existing product-family `model_code`.
   Preserve published history with `INHERIT` for existing rows; disable Model in
   new-company defaults. Enforce Brand and Model in native product writes,
   imports and activation. Verify existing alternate, compound and measured
   unit controls, without introducing a duplicate conversion switch.
2. Group product information and unit conversion controls using native field
   metadata. Improve section navigation, spacing and responsive presentation
   in the editor and read views, preserving field permissions and draft guards.
3. Verify API contracts, migration, configuration workflows and browser layouts
   across light, dark and ledger themes. Record native schema verification and
   manual simplicity/security review before completion.

## Semantics

- Brand controls `brand_id` and its dependent `series_id`.
- Model controls the existing optional `model_code`; it is independent of Brand.
- Alternate units allow conversions to another unit or pack; compound units
  permit quantities made of multiple unit components; measured units permit
  measured conversions. Base-unit entry remains available.
- Options keep the native Disabled / Optional / Required / Use system default
  choices. An Optional option also has an explicit default-on choice.
- Pricing dimensions remain separate from quantity conversion.

## Delivery evidence

Completed 2026-11-04. Native Model policy, Brand/series enforcement and the existing
three unit conversion controls are reflected in metadata, configuration forms,
effective review and product validation/imports. Required choices and dependent
defaults retain their field permissions.

The editor and review use shared CSS/tokens, grouped fields and working section
links. Browser checks passed at 320, 390, 768 and 1440 pixels in light, dark and
ledger themes (24 configuration scenarios); mobile screenshots were inspected.
Artifacts: `.tools/product-config-ui-review/`. Configuration UI tests and console
TypeScript pass. Model-option native migration/reversible-empty rollback and
authored-history refusal pass on isolated MySQL.

Catalog 0217/0218 are applied locally, with backup and retained-value checks.
All 183 Catalog tables match native constraints, models and migration/readiness
heads. Security and simplicity review found and fixed an existing assignment check
that refreshed away unflushed edits; writes now flush after native field checks
and before configuration validation, within the same rollback-safe transaction.

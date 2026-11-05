# Reusable product profile UI and API

Delivery plan (25 October 2026), authorized by the requested end-to-end implementation:

1. Reuse native inventory/tracking, warranty, return and handling masters/revisions. Add
   typed authoring and publication metadata plus a closed company-scoped Console proxy policy.
2. Reuse shared CSS, layout, controls, notices, menus, tables and navigation for directories,
   master authoring/lifecycle, revision history, draft editing and confirmed publication.
   Return conditions use their complete bounded native aggregate; handling stays exact.
3. Test native contracts/permissions and UI success/failure/field access/navigation; review
   desktop/mobile themes; run affected checks, build and schema audit; fix review findings.

Existing models/migrations already contain all four profile families. Published revisions
are immutable definitions selected by existing product configuration references; they do not
execute stock, claims, refunds or shipment monitoring. No new persistence or DDL is planned.

Implementation:

| Profile | Console route | Native permission prefix |
|---|---|---|
| Inventory / tracking | `/masters/inventory-templates` | `inventory_profile_template` |
| Warranty | `/masters/warranty-policies` | `warranty_policy` |
| Return | `/masters/return-policies` | `return_policy` |
| Handling | `/masters/handling-profiles` | `handling_profile` |

Each resource has a searchable, filtered, cursor-paged directory; permission-aware actions;
identity create/edit; confirmed activation/deactivation; revision history; draft creation and
editing; and confirmed publication. Master codes become fixed once revisions exist. Nested
revision pages use `/{profile_id}/revisions/new` and `/{profile_id}/revisions/{revision_id}`.

The four pages share one implementation and existing `@janso/ui` CSS, shell, layout, controls,
menus, tables, notices, navigation and unsaved-change guards. Native field metadata controls
visibility and editability. Company and tenant grants authorize the selected company; a
platform role alone does not. Readers can review; managers can author; publishers can publish
saved drafts without manage permission. Published definitions remain immutable.

Inventory authoring preserves native batch/serial, expiry, identifier and valuation rules.
Warranty durations keep calendar days/months/years with matching limits. Return conditions
use five bounded native choices and aggregate replacement only after the complete set has
been verified. Protected conditions are preserved when another term changes. Handling bounds
remain exact decimal strings; comparison uses fixed-point integers and the absolute-zero
limit. Multiline coverage/instructions use the existing full-width field and error styles.

Commands send only changed writable fields with the saved version. Unconfirmed results freeze
the exact body and idempotency key for replay. Verified receipts must match the company,
profile, revision and version; publication additionally requires a published timestamp.
Conflicts retain drafts until a confirmed reload; validation failures remain editable.

Review fixes:

- Expose publication field authority separately for all four profile families and return
  conditions. Parent links are writable in create metadata because native creation assigns
  and checks them; they remain fixed in updates/publication.
- Avoid treating protected temperature bounds as empty during local validation; the API
  validates the merged stored definition.
- Wait for identity form initialization before enabling edits, remove inaccessible filters
  with an explanation, and display calendar-unit-specific warranty limits.
- Use existing multiline field/error CSS and a meaningful back action on immutable views.

Completed verification (25 October 2026): all 2,329 Console tests in 156 files;
114 focused Console checks; 46 native API/metadata
checks, with the four publication-to-product-configuration workflows rechecked after adding
that assertion; 238 browser workflow/layout checks plus 60 final multiline layout checks at
1440/390 pixels in light/dark/ledger themes. Console TypeScript, Catalog lint/strict typing,
OpenAPI freshness, Catalog SDK freshness/types and all eight SDK transport tests pass.
The read-only schema audit reports 164 model tables, migration/database/readiness head `0191`,
no missing/extra tables, and a clean Alembic comparison. No migration or business-data repair
is needed for this change. The production build passes, Console was restarted and is ready on
port 4320, and the live Catalog profile contracts/readiness and unauthenticated API/BFF
protection were verified. Manual simplification and security review equivalents found no
remaining scope, field-policy, replay or publication issues after the fixes above; the slash
commands are unavailable in this session. All three delivery phases are complete.

Browser checks use actual Console components, providers, shell and CSS with intercepted
native-shaped fixtures. Native workflow tests use isolated SQLite databases. The local
business database was inspected read-only; no live profile records were created for testing.

Sources: [inventory contract](catalog-inventory-template-routes.md),
[warranty contract](catalog-warranty-routes.md), [handling contract](catalog-handling-routes.md),
[commercial masters](catalog-commercial-masters-api.md), and
[product configuration](product-configuration-ui-api.md).

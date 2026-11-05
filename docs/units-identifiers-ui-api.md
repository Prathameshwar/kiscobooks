# Units and identifiers UI delivery

Selected scope: unit conversions, pack types, identifier types, identifier namespaces,
and identifier profiles. Reuse the existing console shell, shared controls, CSS,
company permissions, native Catalog commands, field metadata, and error envelopes.

## Phases

1. Inspect native contracts; complete missing type/namespace management endpoints,
   protected field metadata and control hints. Keep the existing models and schema;
   retain Identity's existing generic Catalog snapshot/authorization contracts and
   synchronize OpenAPI and generated SDK. Verify
   company/tenant boundaries, field denies, idempotency, versions and dependencies.
2. Add permission-aware navigation and directories with search, sorting, filters,
   paging and kebab actions. Add create/detail/edit/lifecycle screens, searchable
   unit references, exact rational conversion inputs, and bounded profile requirements.
   Preserve caller filters and return navigation. Validate native immutable fields,
   success/error states, stale versions, uncertain retries and unsaved drafts.
3. Run API and UI regressions, types, production build and browser review. Review
   security, simplify repeated logic, fix findings and update the master inventory.

## Native limits to retain

- Conversions are create/read only. Ratios use positive integer strings through
  the wire, up to signed BIGINT, with reduced ratios and canonical-root consistency
  enforced by Catalog. They do not support arbitrary edit/delete/lifecycle actions.
- Pack types use existing create/update/activate/deactivate commands. They are
  packaging labels, not company-wide quantity conversion factors.
- Identifier type and namespace codes are stable references. Types declare barcode
  classification at creation. Changes to descriptive names are versioned; referenced
  identifiers cannot be retired. No new physical identifier capture is introduced.
  These definitions search and sort by their indexed codes; descriptive names are
  displayed but do not introduce unindexed prefix search or name sorting.
- Identifier profiles use the existing native aggregate. One or two distinct SERIAL
  and IMEI requirements are authored at creation; requirements and normalization
  version are immutable. Counts are bounded by eight, multi-value requirements need
  explicit slots, and IMEI uses company uniqueness. Requirement changes create a
  new profile. Physical identifier capture remains with the operational owner.
- Platform/tenant administrators use explicit grants for the selected company.
  Company administrators and ordinary users see only their company-scoped grants.
  Read access permits browsing; manage access permits the supported native commands.
  Server-side field denies remain authoritative for reads, writes and list queries.

## Verification and review

Phase 1 complete: native type/namespace routes, metadata/control hints and fixed
registry entries reuse the existing authorization, listing, idempotency, version,
dependency and audit pipeline. Existing Unit/Pack/Profile contracts are retained.
OpenAPI and Catalog SDK were regenerated together; SDK version is `0.2.20`.
21 initial native API checks passed; 42 final API regressions passed, including
retirement dependencies, company/tenant boundaries, protected reads/writes/replays,
closed indexed queries, exact units and profile storage. Ruff and strict mypy pass
for all nine changed/new Catalog source modules.

Phase 2 complete: all five resources use the existing dynamic master routes,
shared shell/CSS/controls, native field metadata and company grants. Directories
have supported search/filter/sort, signed cursor navigation and shared kebab menus.
Create/detail and supported edit/lifecycle pages retain errors, submitted values,
request keys, versions and safe caller navigation. Units link back to conversion
callers; related navigation does not require unrelated master permissions.
Profile requirements are authored together, bounded/distinct/validated, and shown
as read-only paginated rules after saving. Conversion ratios remain integer strings
through BigInt preview and native wire values. Quantity previews use native exact
calculation and verify the requested units and input quantity in the receipt.

Phase 3 review fixes:

- Requirement add/remove buttons explicitly use `type="button"` so they cannot
  submit the enclosing form. Fieldsets reuse the existing styled setup form classes.
- Editor controls wait for initial draft hydration before becoming editable.
- Missing/conditional field controls keep general errors visible; unknown fields
  never enter native command bodies. Immutable identifier headers stay excluded.
- Unsupported/read-denied URL filters and sorts are removed with an access message,
  preserving caller navigation. Edit actions honor writable fields and row versions.
- Unconfirmed lifecycle menu actions explain their disabled state and retain the
  original expected version/key for retry; conflicts require reload/review.
- A preexisting fractional-serial API test now removes its seeded barcode so it
  exercises the intended fractional rule rather than the earlier immutable binding
  guard. Production unit rules were not relaxed.
- Route dispatch reads a server-safe resource registry. Server pages do not call
  helpers exported from client hook modules, preserving Next.js rendering boundaries.
- Quantity results use the existing resolved company formatter; the calculation,
  submitted decimal strings and receipt verification retain native exact values.
- Lifecycle replay accepts the protected current record. If another administrator
  changed availability after the committed action, the screen explains that state
  rather than falsely reporting the old state or indefinitely retrying a saved action.

Final verification (2026-10-25):

- All 2,017 console regressions passed with two workers. The initial parallel run
  hit unrelated timeout failures; all affected tests passed with reduced concurrency.
- All 109 focused units/identifier checks passed after the final quantity-format
  and lifecycle-replay changes. The eleven identifier API checks were rerun and
  passed, including current-state replay after reactivation; the broader 42 API
  regressions had already passed.
- All 152 browser checks passed on actual console components, shell and production
  CSS at 1440px and 390px in light/dark/ledger themes. This covers all five directories,
  detail/forms, immutable controls, requirement add/validation, error focus, dirty
  navigation, frozen retries, lifecycle/current-state replay, quantity preview and
  read-only access. Browser writes use isolated fixtures captured from native metadata.
- Production build, console/SDK types, eight SDK transport checks, Catalog OpenAPI
  freshness, generated Catalog SDK freshness, Ruff and strict mypy passed. SDK ratio
  request/list/detail types correctly remain strings.
- Local Catalog was reloaded through the workspace's managed launcher. All eleven
  infrastructure/API components are UP; the managed console at 4320 is UP. The final
  build stops/restarts only that console, avoiding a shared development/build cache.
  Live readiness, all five API contracts and unauthenticated API/BFF rejection were
  verified without changing business records.

Read-only schema audit: Catalog database head, migration head and readiness head
all equal `0191`; all 164 model tables match the local database, and Alembic check
reports no changes. No model/DDL/migration/seed changes are necessary for this task.
Concurrent design/access-policy work is preserved and excluded from these changes.

Manual security and simplification review substitutes for `/security-review` and
`/simplify`, which are unavailable in this session. Reviewed route/field/object
authorization, tenant/company scope, immutable semantics, dependency locking,
closed inputs/queries, lean projections, protected receipts, retry keys, exact
arithmetic, bounded requirements and safe navigation. Remaining release-level
concurrency/broker/load gates in the native Catalog contracts are unchanged.
No unresolved findings remain within this selected UI/API delivery scope. The core
master UI inventory now has 20 pending categories, down from 25.

## Unit review follow-up (2026-10-27)

The read-only conversion checker retains the configured quantity display and also
shows the exact four-place storage value when that display differs, so a small
nonzero conversion cannot be mistaken for zero. Both use the shared company-aware
formatter. Its guidance distinguishes identity checks from conversions between
different units, which require a common declared canonical root.

Product creation now validates the selected unit's actual readable precision and
increment rather than inventing missing values. Whole serial base steps and fixed
alternate steps preserve the unit grid and exact base representability, using
bounded BigInt arithmetic. The resulting steps are shown before creation. Native
rules and atomic commands still make the final decision. No ratio or quantity is
rounded, no stock facts are created, and voucher integration remains deferred.
Verification and retained API-only boundaries are in unit-conversion-review.md.

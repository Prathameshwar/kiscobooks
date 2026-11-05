# Warehouse and reference UI delivery

Requested 24 October 2026. The user authorized implementation and a final review.

1. Confirm existing contracts and scope. Reuse Catalog's company-owned warehouse
   aggregate and metadata-driven master pages. Preserve Main/internal transit,
   optimistic versions, field policies and the stock retirement fence. Reuse
   existing platform CRUD for Countries, States, Currencies and Languages.
2. Implement warehouse directories, create/detail/edit, lifecycle actions,
   reviewed operation-policy publication and company activity defaults. Use the
   existing controls, layouts and CSS, including searchable regional selectors.
   Add an authorized paged IANA timezone directory and warehouse timezone choices.
   Timezone rules remain installation-maintained, consistent with the existing
   timezone model; no administrator-defined offsets or invented zone identifiers.
3. Test, review and fix validation, access, stale-response, retry, keyboard,
   navigation and responsive behavior. Regenerate affected API/client contracts.
   Record evidence and limitations below. Do not publish or change live stock.

Warehouse grants authorize only the open company. Platform reference management
requires platform.config.manage; tenant/company administrators do not acquire
global reference writes. Location operation flags never confer stock permissions.
Pending consumer acknowledgement must remain visible as pending.

## Verification

All three implementation phases and the final manual simplification,
security/correctness and visual review are complete. The named `/simplify` and
`/security-review` commands were unavailable; equivalent manual reviews were
performed. Existing unrelated working-tree edits were preserved.

### Delivered behavior

- Inventory > Warehouses uses the existing company master directory and shared
  create/detail/edit layouts. Regional, department and tax-registration choices
  use the shared searchable dropdown. Saved links resolve their labels, lookup
  failures offer recovery, and country changes clear the writable state choice.
- Warehouse settings reviews company activity defaults before saving. Main
  initialization, operation-policy preview/publication and uncertain-response
  recovery preserve the server's version and idempotency contracts. Protected
  Main/transit identities and lifecycle restrictions remain enforced. Consumer
  acknowledgement is displayed separately from publication acceptance.
- Platform > References includes Countries, States, Currencies, Languages and
  Timezones. The existing four editable directories retain validation, lifecycle,
  navigation and audit behavior. Timezones are a searchable, paged, read-only
  IANA directory. Global writes require `platform.config.manage`; warehouse
  permissions and lookup permissions remain scoped to the open company.
- Identity exposes bounded active timezone choices and the authorized paged
  timezone directory. Existing company tax-registration lookups now accept
  scoped ID and escaped number-prefix filters. OpenAPI and the generated client
  were refreshed; API client version is 0.2.13. These contracts use existing
  tables and require no model or migration changes.

Review fixes include preventing dirty reference values from being overwritten
by synchronization checks, freezing unconfirmed reference writes to avoid
duplicate submissions, excluding immutable/unreadable warehouse fields from
editable-state checks, and making uncertain policy/default saves recoverable
with the original command key. Refused previews cannot be published.

### Evidence and limits

- Console: 1,260 tests passed in 108 files. TypeScript and the isolated production
  build passed. Client generation, type checking and all eight client tests passed.
- Identity: 56 affected reference/statutory tests passed. Ruff and strict mypy
  passed for the changed Python modules. Catalog: 74 existing warehouse,
  operation-policy, location-mode and resolution tests passed.
- Browser: 84 checks passed without page errors, using real components and
  fixture BFF responses at 390/1,440 pixels across light, dark and ledger themes.
  Reviewed lower mobile form sections, directories, selectors, kebab actions,
  confirmations and lost-response recovery. Independent API tests cover server
  contracts; this browser run does not claim live Authentik workflow verification.
- Coverage increased from 97.67% to 97.75% statements/lines, 84.45% to 84.63%
  branches, and 79.77% to 80.11% functions. The existing global branch/function
  thresholds (85%/90%) still fail, so the coverage command exits unsuccessfully
  despite every console test passing. Thresholds and exclusions were preserved.
- All seven local databases passed Alembic/model and additional native schema
  comparison. Reference seed rows match the shipped datasets. All 49 launcher
  tests and parsing of all 49 PowerShell scripts passed. Current backend status
  reports all eleven components UP. See [local-schema-sync.md](local-schema-sync.md).

Local evidence is retained under ignored `.tools/warehouse-*` logs and the
`.tools/warehouse-browser-review/` and
`.tools/warehouse-schema-review-20261024/` directories. The production build used
an isolated output directory; running API/UI processes and live stock were
preserved. Existing Identity processes need their normal restart to load new API
routes; current readiness probes certify the already-running service versions.

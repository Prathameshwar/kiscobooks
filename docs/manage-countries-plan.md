# Manage countries and states

Superseded scope: the user's later request adds Languages, Currencies and full
create/view/edit/delete flows. See `reference-catalog-management-plan.md` for the
combined plan, agreed on 2026-10-21. Prepared regressions remain useful.

Requested 2026-10-21: enable Settings → Manage countries with complete UI, API and
database support, reusing shared styles and components. Expanded to include States
management from the Settings card and each country's kebab. Combined phase
agreement was received on 2026-10-21.

Existing country/state records are global ISO references, replicated and seeded
from the committed dataset. Their codes select jurisdiction rules and are foreign
keys used by existing business records. Do not treat them as ordinary tenant CRUD.

Recommended scope: platform-admin country/state directories and dedicated details pages,
with durable enable/disable configuration. Keep canonical ISO identity fields
read-only and preserve all referenced records. Persist platform availability in
Identity-owned settings tables so seed refreshes cannot undo administrator
configuration. Existing company/tenant references and historic documents remain
valid; prevent disabling a country or state where doing so would break an active dependent
configuration. No arbitrary ISO record creation, code renaming or hard deletion.
State parent-country links and tax jurisdiction codes remain canonical: changing
them would reinterpret existing company/address references and GST validations.
State availability combines source activity, administrator configuration and
parent-country availability. Re-enabling a country must preserve each state's own
configuration rather than blindly enabling all children.

1. Add country/state availability models, single-DDL migrations, schemas and domain validation,
   protected platform list/detail/lifecycle APIs, transactional audit and concurrency
   controls. Use the existing platform operator plus live platform.config.manage
   authority. Use bounded signed paging, typed status filters, indexed prefix/code
   search and allowlisted sorting. Apply availability consistently to registration,
   tenant setup and company reference selection/validation, retaining authoritative
   source activity. Include new company/address state selections; historical tax
   lookups remain unchanged. Regenerate contracts and run API/domain/migration regressions.
2. Enable Countries and States in Settings for permitted platform administrators.
   Add directories with search, country/status filters, paging, sorting, refresh icon and row
   actions, and a dedicated view/configuration page with confirmation, validation,
   loading/empty/error/retry and session recovery. Reuse central ActionCard,
   FilterBar, DataTable, Pager, forms, notices and page/card layouts. Keep the other
   Settings cards disabled. Each country kebab has Manage states linking to
   `/settings/states?country_code=IN` for India (the actual selected code for other
   countries). The States card opens `/settings/states`, with an All countries
   option. Preserve list filters when viewing details or returning. Include
   parent-unavailable explanations and validation, stale-version conflict recovery
   and confirmation of availability changes. Add route/component/accessibility tests.
3. Verify a disposable native MySQL database, seed reruns, concurrency and rollback,
   browser/API behavior and country/state availability in signup/tenant setup. Review
   permissions, global-data boundaries, audit, historic reference preservation and
   shared styling; update run instructions and evidence. Restore normal processes
   and remove test records. No publishing or unrelated-file changes.

The scope and phases need agreement because this crosses application boundaries,
introduces database schema and exceeds about 100 lines (CLAUDE.md §2).

Preparation evidence: 28 Console Settings/platform-boundary/tenant-form tests and
10 Identity public/regional choice tests pass. Prepared regression checks confirm
the missing administrator Settings link and missing protected country directory
(404). They are saved outside active suites in ignored
`.tools/local-login/manage-countries-prepared/` until implementation starts.

Implementation details to preserve: natural ISO code is the stable pagination
tie-breaker for this reference list (existing UUID-only keyset helper needs a safe
extension rather than pretending Country has an id). New settings rows use UUIDv7
and unique country code/FK; only platform operator API writes reach global settings.
Audit identifies the availability row's UUID and records safe field changes in the
actor's platform tenant outbox. Seed reruns update source rows without touching
availability settings. Serialize disable and new dependent writes on the source
country and state rows, with consistent country-before-state lock ordering; retain historical company reference
behavior already enforced by `_assert_references_exist`.

States review: `state.code` is the ISO subdivision key; `(country_code, code)` is
the composite foreign key used by tenants, companies and company addresses.
`tax_jurisdiction_code` drives GST state-prefix validation. `seed_reference`
overwrites canonical source fields on reruns, so operational configuration must
remain separate. Current Settings cards and company reference APIs are read-only;
no protected state management route or administrator Settings link exists yet.

Prepared regressions for the expanded scope must cover both Settings entry points,
the country-kebab filtered navigation, strict BFF allowlists, protected state reads,
cross-country filtering, signed cursor/query binding, denied/stale mutations,
parent availability, persisted configuration after reseeding, dependent selections
and historical record preservation.

Expanded preparation evidence: existing 28 Console and 10 Identity regional tests
still pass. The new state regressions fail at the expected missing features:
administrator Settings links are absent, the fixed BFF rejects state reads, and
both anonymous and country-filtered platform state requests return 404. Two UI
permission/destructive-operation checks pass. Prepared sources are saved in the
ignored folder above, outside the active suites; no application change is made
before combined phase agreement.

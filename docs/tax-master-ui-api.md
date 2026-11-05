# Tax master UI and API delivery

Scope: company-owned India GST tax categories, HSN/SAC classifications, rules and
dated rates. Reuse the console shell, shared CSS, forms, searchable selects, tables,
messages and navigation. Existing tax commands remain authoritative for tenant and
company access, evidence, exact decimals, publication and history integrity.

## Phases

1. Verify existing contracts; add protected native form hints and a read-only current
   company/source/policy context. Test API contracts and regenerate the Catalog client.
2. Deliver `/tax` and four linked master directories, creation/edit/detail screens,
   rate series/components, preview/publication, future revision replacement and
   withdrawal. Preserve query context, provide field errors and safe save recovery.
3. Run UI/API tests, type checks, production build and browser checks. Review
   simplification, authorization, field access, dated tax integrity and navigation;
   fix findings and record actual evidence here.

Categories and rules use their existing active/inactive lifecycle. Published
classifications and rates use dated replacement/withdrawal commands rather than
editing history. Rule code, kind, treatment, category and evidence remain immutable
after creation. Rate series identify a rule and supply context; rate components are
children of their publication. Official evidence is entered explicitly; directory
suggestions never set statutory rates or manufacture evidence.

## Implementation

- The Tax masters menu and `/tax` overview link all four company-scoped directories.
  Categories/rules support creation, native detail and permitted name/status/custom-field
  edits. HSN/SAC classifications and rates support reviewed publication, future replacement
  and withdrawal with retained publication evidence.
- Rule details link classification applicability and supply-context rate series. Rates offer
  individual previews and `/tax/rates/release/new` for one coordinated publication across
  the three GST supply contexts. Replacements require explicit consent and pin previous
  versions. Government document reference, HTTPS URL and SHA-256 remain explicit inputs.
- Forms reuse `@janso/ui`, existing production CSS and the console layout. Reference choices
  use the shared searchable select with selected-record hydration, paging, cancellation and
  company scope. Native enum choices use the shared select. Errors, empty states, focus,
  kebab actions, return filters and unsaved-change/company-switch guards are implemented.
- Server pages and existing command APIs require company-scoped `tax_rule.read`,
  `tax_rule.manage` and, for publication, `tax_rule.publish`. Native field permissions remain
  authoritative. The shared proxy exposes a closed tax namespace; request bodies pin source,
  policy and relevant row versions. Unconfirmed writes freeze inputs and replay the exact
  command/idempotency key until its receipt can be verified.
- Added protected native field hints, a read-only tax administration context and protected
  rate-directory rule/context labels. Fixed an existing item inventory profile read-schema
  mismatch exposed by the native tax activation regression. Catalog OpenAPI, API-client
  0.2.18, its npm lock and its installed console consumer are synchronized.
- No SQLAlchemy models or migrations changed. The live Catalog database matches 164 model
  tables at Alembic/readiness head `0191`; read-only `alembic check` found no new operations.

### Background reviews

For releases affecting more than the native synchronous preview capacity (256 products),
users can request a durable background review, refresh progress and page through findings.
Publication requires a verified COMPLETE report with zero blocking findings. Stale, failed
and incomplete reports cannot be published through this screen.

`start/win/tax-review.ps1` starts/stops/status-checks the existing Catalog review worker.
Backend startup/shutdown include this lifecycle, using managed process ownership and no
listening port. Configure private `CATALOG_IDENTITY_SOURCE` and explicit tenant/company
`CATALOG_SOURCE_SUBSCRIPTIONS` in the Catalog environment to enable processing; do not
invent subscriptions or put credentials in UI/commits. These values are absent locally,
so startup currently reports a clean skip. Large background reviews remain queued until
an administrator provides that configuration; ordinary preview/publication is available.

## Review and verification (2026-10-25)

Manual simplification/security/correctness review covered the repository's money, audit,
tenant/company and field-access rules. `/simplify` and `/security-review` are unavailable in
this session; their review was performed manually. Findings fixed included required-field
feedback, a saved-value hydration race, protected-status preservation during allowed name
edits, history verification before withdrawal, readable rate-directory labels, no-op edits,
return navigation during uncertain withdrawal, missing coordinated publication, background
review gating, failed predecessor reads remaining blocked after editing evidence, and rejecting a
background report returned for a different review ID.

- Native tax/configuration API regression suite: **104 passed**.
- Full console regression suite: **1,825 passed** across 139 files with two workers
  and a 20-second timeout for this Windows environment. After the final report-ID
  guard, all **95 focused tax tests** passed and the production build passed again.
- Ruff and strict mypy checks passed for the changed Catalog sources; mypy checked seven files.
- Catalog OpenAPI regeneration check, generated Catalog client check and client type check passed.
- Production console build passed; original TypeScript/Next environment files were preserved
  byte for byte. The new tax route compiled successfully.
- Windows: **51 scripts parsed**, **49 existing launcher regressions** and **3 tax review
  lifecycle tests** passed.
- Browser: **146 checks passed**, using actual components and production CSS at 1440px/390px
  in light/dark/ledger themes, including validation, navigation, searchable references,
  permission states, preview/publication, coordinated publication and same-command retries.
  Browser writes used an isolated fixture BFF. No live tax definitions were changed.

Live verification: all eleven backend components are UP after the managed Catalog reload.
The tax administration route is present in live OpenAPI. Both local web servers are UP;
unauthenticated `/tax` and `/tax/rates` requests reach sign-in as expected.

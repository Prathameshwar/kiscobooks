# Company setup: country, currencies and pharmacy licences

Identity owns company setup. Reference rows are loaded by `python -m identity.install`;
country, state and currency choices have no CRUD API. Licence kinds come from the
versioned jurisdiction catalogue, so a deployment exposes them without a tenant seed.

## Minimal Product Configuration — 2026-11-04

Selected company capabilities now commit with company creation using the creator's
actual company role and the existing feature command. This prevents Catalog's
enrollment worker from publishing starter masters before requested capabilities
such as inventory are present. The resumable feature step remains idempotent.

Catalog then publishes one minimal company Product Configuration and a default
company pricing policy after preparing Default type/group, PRICE1 and base-currency
sales/purchase plans. Extra entry and pricing options start disabled. Simple
authoring is the existing no-row default. Inventory is selected by default; an
untracked Goods type and FIFO inventory template are prepared for a new inventory
company. Services retain their separate non-stock defaults. Retries preserve
existing work and published history.

The 2026-11-04 Simple Product decision changes new setup's default opening choice
to `ZERO_CONFIRMED`, with an editable explanation that individual product openings
will be entered during creation. Setup confirms the native zero financial and
stock baselines. Explicit deferred/entered opening choices remain available.
The earlier undecided-default description below is historical.

[Simple Product Save](simple-product-ready-plan.md) creates an active product,
publishes its selected prices and posts its optional opening through native owners.
Goods show HSN and opening stock; Services show SAC and reject stock. GST fields
appear only for GST companies. Purchase price times quantity supplies opening value.

The company setup worker verifies the published company configuration, effective
goods/service settings and current pricing policy before completing the Catalog
step. A missing publication waits; an existing unpublished configuration or a
missing/ambiguous current pricing policy requires review. The UI names this step
“Products and pricing setup” and links configuration review when needed.
Details and validation: [Product Configuration starter plan](product-configuration-starter-plan.md).

## Automatic setup delivery (2026-11-03)

The 2026-11-06 progress follow-up reuses the financial reports' animated preparation
feedback from saving the creation request through checking setup and opening the
company. Verified setup responses supply the current operation and ready-step count.
Waits, access failures and steps needing review retain their existing explanation
without an activity bar. New creation phases scroll into view on short screens;
the existing **Open while setup continues** action remains available after saving.
See the [progress review](company-create-progress-review-2026-11-06.md).

The user approved [automatic readiness](company-automatic-readiness-plan.md) through
all phases and two final reviews. Company creation accepts an optional bounded
`setup` intent (selected features, explicit opening choice/reason). Legacy callers
default to undecided opening balances. `Idempotency-Key` binds the authenticated
creator's request to its company and durable setup run; changed details cannot reuse
the key. Company creation, creator grants, source enrollments, setup steps and audit
commit atomically. `GET /v1/companies/{id}/setup` exposes scoped progress;
`POST /v1/companies/{id}/setup/retry` resumes incomplete work without changing the
original financial declaration. The Identity setup worker prepares owner defaults,
books and the first fiscal year; Reports discovers enrolled companies and reconciles
verified sources continuously. The browser may close after creation succeeds.
`DECIDE_LATER` and `IMPORT_EXISTING` complete technical setup without claiming zero
opening balances. An explicit `ZERO_CONFIRMED` choice uses the existing guarded
Accounting command. See the [delivery and review record](company-automatic-readiness-delivery.md).

Chart and books initialization each allow a bounded 30-second Accounting transaction;
the setup worker and browser proxy allow 45 seconds for these two owner commands.
Other financial commands keep their existing deadlines. The shared executor's exact
busy/in-progress conflicts retry with the same command key; authorization and business
conflicts still require review. No timeout permits a partial books or ledger commit.

On `/settings/readiness`, users with company-scoped `company.update` access can
select **Complete remaining setup** for an interrupted or waiting run. It resumes
the existing setup command, preserving completed steps and the opening choice.
The page polls progress and reloads its books and financial-year context when an
observed background run completes, including runs resumed elsewhere. Pending steps
say **Waiting** until their work starts. Refreshes preserve an unfinished opening
declaration. Current Accounting readiness overrides a historical deferred-opening
step after balances are finalized.
Needs-review runs continue read-only polling too: recovery in another tab or after
an uncertain retry response must replace the stale failure and remove the retry
button. Polling never resubmits a setup command automatically, and still stops for
completed runs or denied/missing setup access.

## Read-only selectors

| Endpoint | Content |
| --- | --- |
| `GET /v1/reference/countries` | Active ISO countries, default currency, subdivision label, jurisdiction support and tax systems |
| `GET /v1/reference/countries/{country_code}/states` | Active subdivisions belonging to that country |
| `GET /v1/reference/currencies` | Active currency codes, names, symbols and minor-unit precision |
| `GET /v1/reference/countries/{country_code}/licence-types` | Supported kinds, labels and platform validity requirements |

The actor needs an in-force `company.create`, `company.read`, `company.update` or
`company.licence.manage` grant. Any company scope is sufficient for these global
choices; they expose no tenant or company records. Lists are ordered by natural
code, with a hard maximum of 1,000 rows (states are restricted to one country).
An oversized catalogue returns a conflict instead of silently losing choices.

ISO reference availability is broader than implemented tax jurisdictions. Use
`jurisdiction_supported` and `tax_systems` when presenting company creation choices.
Currently India and the United Kingdom have profiles. Unsupported countries cannot
be used to create a company merely because they have an ISO reference row.

## Country and currency selections

`POST /v1/companies` requires `country_code`, matching `state_code`, `base_currency`
and a `default_tax_system` supported by the country's profile. Country and currency
are explicit selections; the country's default currency is a UI suggestion, not an
override of the selected ledger currency. No default is guessed by the API.

For a new company, the Console preselects the current tenant's
`default_country_code` and `default_state_code`, supplied by `GET /v1/session`.
Both controls remain editable. A supported active country is selected first, then
its state is selected only if it appears in that country's active choices. Missing
or unavailable defaults leave the relevant control for manual selection. Changing
the country clears the state; a delayed earlier response cannot replace the user's
new selections. The submitted company values remain explicit and independent of
later tenant default changes.

`reporting_currency` is optional; omitted or null means use the base currency.
It is a presentation setting, not an alternate transaction currency. It does not
enable exchange-rate lookup, currency conversion, foreign-currency billing or
consolidation. The `multi_currency` feature flag alone does not implement those flows.

Create and PATCH validate references and country/tax consistency before writing.
Inactive codes cannot be newly selected; an unchanged historic selection can be
retained. Required country/state/base currency fields cannot be cleared. The base
currency, country and state remain immutable after first posting. Reporting currency
can be changed or cleared because it does not reinterpret stored ledger amounts.

Before first posting, changing country is also refused once company licences, tax
registrations or statutory IDs exist. Company updates and statutory writes take the
same company-row lock, so a concurrent insert cannot bypass this check. Changes to
an existing jurisdiction with statutory records require a separate migration workflow.

## Pharmacy and chemist licence records

Create the company first, then add each licence with
`POST /v1/companies/{company_id}/licences`. Read them with the corresponding GET.
Licences use the existing `company_licence` table with one row per kind/number/validity
period. A company may have zero, one, two or more; no universal two-number requirement
is inferred from choosing the pharmaceutical business category.

| Kind | Label |
| --- | --- |
| `drug_licence_20` | Drug Licence 20 (retail) |
| `drug_licence_21` | Drug Licence 21 (retail) |
| `drug_licence_20b` | Drug Licence 20B (wholesale) |
| `drug_licence_21b` | Drug Licence 21B (wholesale) |

These form distinctions follow the [Delhi Drugs Control licence-type checklist](https://drugs.delhi.gov.in/sites/default/files/drugs/universal/checklist_1.pdf).
Existing 20B/21B keys and records retain their identity; the old retail label on 20B
was incorrect. Other special licence forms are outside this catalogue's current scope.

Each record carries number, validity dates and optional authority, issue date,
premises, document reference and reminder lead time. If premises are supplied they
must be an active address of the same company and tenant. This is checked before
writing, with the same non-disclosing error for missing or inaccessible addresses.
Duplicates return 409; invalid selections or dates return 422. Licence creation is
protected by `company.licence.manage` at the company scope and emits an audit event
in the same transaction. Renewals are new dated records; existing records remain.

**Validity is a platform verification window.** The existing platform policy requires
`valid_to` for drug licence records. Do not interpret this as a claim that all such
licences automatically expire: [Drugs Rules, rule 63](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/drug_rules/Drugs%20Rules%201945_2024%2009.pdf)
provides for continued validity subject to retention fees and suspension/cancellation.
Use the verified-through date supported by the supplied documentation; no arbitrary
expiry or five-year interval is generated. Automated retention verification,
suspension/revocation history and reminder dispatch are not implemented by these fields.

The existing generic `scheduled_drug` helper is not a complete pharmacy authorization
engine. Product schedule, retail/wholesale activity, premises and licence combinations
must be evaluated together when Billing is implemented. A stored licence or a
pharmaceutical category alone does not certify that a particular sale is permitted.

## Current client boundary

The OpenAPI contract and TypeScript client expose the selectors and licence operations.

**The console has a company setup screen** at `/companies/new` (web only). It
reads supported country/reference choices and treats currency, fiscal and display
defaults as suggestions the operator confirms. Creation saves the company, grants
and durable setup intent together. The wizard then displays the eight authoritative
setup steps and opens the company only after the server reports technical completion.
Users may choose **Open while setup continues** or **Leave for now**; the saved work
continues independently. A later completion cannot redirect a user who chose to leave.
Recovering an uncertain creation response replays the same body and idempotency key.

The company details page and Company readiness page both show the authoritative
`Automatic company setup` checklist. It polls the saved plan and explicitly separates
company saved, preparing, retrying, needs attention and complete. Opening balances
still require the user's declared choice; technical completion with `AWAITING_OPENING`
does not claim that balances are finalised. Retry remains gated by company-update
permission and the server's scoped endpoint.

The setup worker prepares capabilities, starter Catalog masters, voucher types,
account chart, books, first financial year, opening choice and Reports. The browser
can close without stopping these steps. Tax registrations, customers, suppliers and
bank details still require real company facts. See
[company master bootstrap](company-master-bootstrap.md).

**Two code catalogues are served rather than copied into the form.** `CountryChoice` carries
`setup_defaults` — the fiscal anchor and the presentation conventions that country usually
implies (`identity/domain/company_defaults.py`) — and `GET /v1/company-features` carries the
capability catalogue with its labels, dependencies, tax gating and which entries lock once
used. Both are suggestions and descriptions only: creation still states every field
explicitly, and enabling a feature still closes dependencies upward server-side. A client
keeps only a neutral starting point for the moment before the first response lands.

The Business step suggests the full legal name as the Trading name until the operator
edits or clears Trading name. Short name suggests uppercase initials for multiword
names, including legal endings: "Visva Enterprises Private Limited" becomes "VEPL".
Single-word names remain readable. Suggestions are limited to 40 characters and stop
following the legal name once edited or cleared. Users may enter their preferred name
within the existing 120-character limit. Short names need not be unique; no suffix or
uniqueness validation is added. The separate Company code retains its existing rules.

Location and tax offers an optional registration section after tax-system selection:
GSTIN or VAT registration number, registration type and registration effective date.
`CountryChoice.tax_registration_options` supplies the supported types, labels and
jurisdiction scope from native catalogues. All three fields are required unless deferred.
The "Add registration later" switch sits beside the registration heading for GST, VAT
and other supported tax systems, and defaults to off so the fields are available immediately.
Turning it on clears and hides them, omitting registration from creation. Changing country/tax system
starts an empty registration for the selected system. Changing state clears a state-scoped
registration while preserving the switch choice. The review includes the details.
The registration section explains the automatic tax-ledger/mapping preparation and
that Purchase GST needs a saved registration valid on the bill date. General company
setup completion does not by itself imply that a company has registered for GST.
Registration also does not select a tax percentage: Purchase uses the product's tax
assignment or an expense account's purchase tax default, with dated rates maintained
under Tax rates. The current Purchase form has no direct line-level Tax % input.

`POST /v1/companies` accepts optional `initial_tax_registration` containing `number`,
`regime` and `valid_from`. Tenant-scoped `company.create` authorizes this initial setup
only on the company being created. The server derives its tax system, jurisdiction,
legal name and primary status, then reuses the existing registration validation and
audited writer. Company, registration and setup intent commit together; invalid details
roll back the transaction. The creation receipt includes these details, so retries
cannot duplicate the registration or change it under the same key. Requests omitting
the new field preserve the pre-existing receipt hash. No schema migration is needed.

Verification (2026-11-04): 39 wizard tests and 102 Identity tests passed, including
GST/VAT creation, permission/scope checks, rollback, audit privacy, idempotent replay,
existing company settings and reference caches. Scoped TypeScript, Ruff, strict mypy
and generated-contract checks passed. Browser layout checks covered 1440/390/320px
in light, dark and ledger themes; controls remained within the viewport. Full console
typechecking is blocked by the unrelated `tests/design-assets.test.ts:63` BlobPart
type error. Manual simplicity/security review found no further issue; `/simplify`
and `/security-review` commands are unavailable here, so equivalent checks were
performed directly. No new migration, dependency, commit or publication was needed.

Follow-through verification: 11 initial-registration tests (including the first signed
automatic books command), 29 Accounting default-selection/provisioning tests, 124
Purchase-tax UI tests and the 39 wizard tests passed. These used the existing isolated
test fixtures; no registration was fabricated for a live company. Existing local
companies without registrations still need their actual registration details entered.

Statutory identifiers, additional tax registrations and licences remain post-creation
operations; a failed licence save still leaves the company available for a retry. Logo and
signature images are not collected yet — there is no upload flow, and these columns take a
URL. Full FX billing and a pharmacy posting workflow are separate capabilities, not implied
by this setup API.

## Decision log

- 2026-11-06: Reuse the existing Profit and loss progress treatment as the shared
  `PreparationProgress`. Company creation shows immediate saving feedback and
  verified setup step progress, scrolls new phases into view, and keeps explicit
  background opening. Polling, completion callbacks, retry permissions, creation
  idempotency and opening-balance declarations retain their existing contracts.
  Verification: 257 unit tests, 384 browser layout checks, Console/UI TypeScript
  checks and task-file whitespace checks passed. Two pre-existing report-test
  error-message expectations were corrected; financial behavior did not change.

- 2026-11-04: Commit selected capabilities with company creation, then provision
  and verify a minimal published Product Configuration and company pricing policy.
  Existing drafts and pricing choices require review rather than replacement.

- 2026-11-04: MASCPL still showed Books: Needs review in an open readiness panel
  although its saved run was COMPLETE, its books and FY2026-2027 existed, and reports
  were READY. Removed the terminal polling branch for NEEDS_ACTION so recovery made
  elsewhere, or after a lost retry response, updates the visible evidence and triggers
  the guarded readiness refresh. Regression tests reproduced the stale panel before
  the fix and cover completion without another write and without changing the saved
  opening choice. MASCPL retains DECIDE_LATER; no zero balances were declared.
  All 83 affected wizard/readiness tests and scoped TypeScript passed. Live reads
  confirmed COMPLETE with seven READY steps, opening AWAITING_OPENING, initialized
  INR books and the April 2026-March 2027 year. A controlled stale first response in
  the browser restored the retry button; clicking it returned 200 from the real
  endpoint and replaced the stale panel with current evidence. A second stale-response
  probe recovered automatically with zero extra retry writes. Manual simplicity and
  security review found no additional issue; server authorization and financial
  commands are unchanged. Review slash commands are unavailable in this environment.

- 2026-11-04: Kept automatic preparation visible in the creation wizard by default
  instead of immediately opening a saved company. Reused the existing scoped setup
  checklist, retries and completion signal, with an opt-in initial-completion callback
  so readiness-page refresh behavior remains unchanged. Explicit background opening
  and leaving are available; neither duplicates creation nor changes opening balances.
  Review copy now describes preparation without claiming posting is authorized and
  avoids a fixed account count that omitted applicable stock/tax accounts.
  Live verification created `Creation Verification GST Nov04`
  (`01a1a493-7c27-774d-9775-1afe3f917791`) with test GST registration, inventory and
  an explicit zero-opening declaration for this new verification company. All eight
  steps reached READY in 193 seconds and the wizard opened it automatically. Browser
  evidence recorded exactly one creation write and no manual setup retry or owner
  initialization. Report sources reached CURRENT with business and inventory READY.
  The business overview displayed verified figures and the readiness page was checked.
  Desktop and 390px progress layouts were inspected; the narrow view had no horizontal
  overflow. Deferred opening choices remain covered independently and are not converted
  to zero balances. Manual simplicity/security review found no additional issue; this
  UI change retains existing server scope, grants, idempotency and financial rules.
  Verification: all 57 wizard/automatic-readiness tests and scoped TypeScript passed.
  The `/simplify` and `/security-review` slash commands are unavailable here.

- 2026-11-04: MASCPL's initial stock/GST ledgers exceeded the ordinary 10-second
  financial-command deadline, rolling back books and blocking its calendar/reports.
  Matched books initialization to the existing 30-second chart budget and aligned
  worker/proxy timeouts. Recognized only the executor's two transient 409 responses
  as retryable; other conflicts remain actionable. Resumed the saved setup without
  changing its `DECIDE_LATER` opening choice. Live books initialization completed in
  about 23 seconds, FY2026–2027 was generated, and the overview returned verified data.
  Verification: 28 Accounting provisioning/fiscal tests, 15 Identity setup tests and
  99 console proxy/policy tests passed; affected Python modules passed Ruff and strict
  mypy. Live setup reached `COMPLETE`, report sources reached `CURRENT`, and the
  overview displayed current figures with the opening-balance decision still pending.
  Manual simplicity/security review found no additional issue; the `/simplify` and
  `/security-review` commands are unavailable in this workspace.

- 2026-11-04: User chose initials for Short name (Visva Enterprises Private Limited
  → VEPL) and explicitly requested no uniqueness requirement. Manual edits and clearing
  remain authoritative; existing company names are unchanged.

- 2026-11-04: Approved editable Trading name autofill and three-field GST/VAT
  registration in Location and tax. Optional initial registration now saves atomically
  with company creation, before automatic accounting setup can start. Its choices come
  from the existing tax catalogue, and its validation/audit writer is shared with company
  settings. Existing registrations and settings permissions remain unchanged.

- 2026-11-03 (follow-up review): Windows setup now supplies the reviewed UTGST
  subdivision configuration when absent, preserving explicit installation values.
  Company tax defaults and calculation share that setting. Regressions also cover
  tax registration arriving during an in-flight setup request, rollback audit
  isolation, and inventory/UTGST/RCM/TDS/TCS together. See the defaults delivery
  record for evidence and the source reference.

- 2026-11-03 (accounting defaults review): the chart/books owner commands now
  provision the approved High-priority ledgers. Since tax registrations are entered
  after company creation, adding one requeues only the enrolled books step and
  fences stale in-flight completion. Its idempotency key includes the authoritative
  feature/registration selection; unchanged retries reuse the key. Live authority
  is still resolved for the original setup actor. Completed calendar/opening steps
  remain complete. See [delivery record](company-accounting-defaults-delivery.md).

- 2026-11-03: Authorized automatic company readiness replaces browser orchestration
  with a durable Identity plan and signed report-purpose enrollment. Initial sources
  and later updates run automatically. Installation credentials opt in once; company
  IDs are discovered live. Existing-company report adoption preserves business facts
  and disabled enrollment. Opening balances remain an explicit business decision.

- 2026-11-03 (final review): Setup retry backoff counts consecutive attempts at the
  unfinished step and resets on success. Earlier successful steps must not delay a
  later step's first dependency retry. Stable owner command keys, fenced leases,
  native authority checks and the maximum backoff remain unchanged.

- 2026-11-03 (user decision): Company creation opens **every** month of the first financial
  year from the books-begin period to the year end, not only the books-begin month, so a
  voucher dated in any of them posts without a separate step. Each month is opened through
  the existing `period.manage` transition (one idempotent command per period, in date order,
  audited by Accounting); a month already past `FUTURE` is left as it is, and a closed or
  locked books-begin period still stops the run. Closing, reopening and locking are
  unchanged, as is year generation itself (it still leaves periods `FUTURE`). No API or
  schema change.

- 2026-10-26: New company location starts with the tenant's country/state as editable
  suggestions. The existing authenticated session exposes only those two additional
  tenant defaults; no extra tenant-read permission or browser-selected tenant ID is
  needed. Console and Identity's generated client are synchronized at SDK 0.2.29.
  Existing company records, create validation, models and migration heads are unchanged.

- 2026-09-11: Reviewed company setup. Added read-only seeded selectors; validated
  country, state, currency and tax on both create and update; retained inactive
  historical codes; guarded country changes against existing statutory records;
  closed the licence-premises ownership gap; added retail Forms 20/21 and corrected
  the Form 20B label. Kept the normalized licence table and existing required platform
  verification window. No schema change or mutation API for reference data was needed.

- 2026-10-21: Console company creation shipped against this contract unchanged (no new
  endpoint, no schema change). Noted the one duplication it introduces: the capability list
  on the "what you track" step is a client copy of `libs/platform/.../features.py`, kept for
  labels the API does not carry. A stale entry there can only omit a capability from that
  screen — enable still closes dependencies upward and refuses a feature the company's tax
  system cannot offer — and a feature-catalogue endpoint would remove the copy.

- 2026-10-22: Removed that duplication. `GET /v1/company-features` now serves the catalogue
  (graph from `libs/platform/.../features.py`, labels and order from
  `identity/domain/company_features.py`, which validates at import that every catalogued
  feature is offered — a new feature without a label fails the boot rather than silently
  vanishing from the form). `CountryChoice.setup_defaults` serves the per-country fiscal and
  display suggestions, so the wizard's `IN`/`GB` table is gone and only a neutral fallback
  remains client-side. The defaults live in Identity's domain, not in
  `billing_platform.jurisdiction`: nothing outside company creation reads them, and
  replicating them into other services would imply they govern something there. No schema
  change; both endpoints are read-only and carry no tenant data.

- 2026-11-04: Replaced the registration deferral button with a switch; on skips registration, off shows the required fields. Reused the shared switch with globally loaded styles.

- 2026-11-04: Aligned the registration heading and deferral switch in one shared header row for every supported tax system; shortened the non-GST setup hint too.

- 2026-11-04: Defaulted "Add registration later" to off for every supported registration profile. Country/tax-system selection opens empty fields; state changes clear state-scoped details without changing an explicit deferral choice. Creation requires complete registration details or an explicit choice to add them later.

- 2026-11-04: Live creation verification found that a degraded unrelated API caused
  startup to skip reference delivery and Catalog source workers. Restored the configured
  workers and moved the aggregate startup failure exit after their launch attempts.
  Startup still reports failure for unhealthy APIs. Added the existing setup checklist
  to company details so the fast creation redirect no longer hides background work.
  The clearly named test company `Setup Test Nov04` (`SETUP-QRVF`) reached COMPLETE:
  all eight steps READY, report sources CURRENT, and the overview showed verified zero
  balances. No GST registration was invented; the test deferred registration and
  explicitly confirmed zero opening balances for this new test company.
  Validation: 44 affected Console tests, 6 Windows lifecycle tests and scoped TypeScript
  passed. Regression tests first reproduced the skipped workers and missing progress.
  Manual review confirmed scoped reads/retries and no changes to accounting write rules.

- 2026-11-04: End-to-end review corrected four progress states: show the initial
  status read, explain 401/403 and clear stale progress, distinguish completed
  preparation from unconfirmed opening balances, and claim company creation is
  saved only after the response confirms it. Older companies without setup
  enrollment still omit the checklist after a 404.
  Regression tests reproduced the misleading states before the fixes.
  Verification passed 130 distinct Console cases and 123 Identity cases (253 total),
  plus the scoped TypeScript check. Coverage included name suggestions and overrides,
  GST/VAT validation and rollback, grants/tenant scope, idempotent retries, background
  lease recovery, owner outages, fiscal defaults and opening declarations.
  Live browser verification created `UK Review Nov04` (`CREATION-REVIEW-JK7B`,
  `01a1a45e-0de5-778f-9b38-049cd8c697bb`). The first successful creation response was
  deliberately interrupted; retry sent the same body/key and opened the same company.
  Preparation continued after leaving the wizard and reached COMPLETE, with seven
  READY steps and opening AWAITING_OPENING. GBP and the 6 April?5 April fiscal year
  were retained. Reports reached CURRENT / OPENING_REQUIRED / inventory READY;
  fiscal readiness reported only OPENING_NOT_FINALIZED as the posting blocker.
  A readiness read briefly timed out during preparation and succeeded on retry.
  Registration was deferred; no VAT number or business balances were invented.
  The test company remains available for inspection. Manual simplicity/security
  review found no additional issue in this scope; unavailable review slash commands
  were not claimed as executed. Server permissions and financial writes are unchanged.

- 2026-11-04: Restored the missing `company.update` permission handoff on the
  readiness page and exposed the existing retry command as **Complete remaining
  setup** for NEEDS_ACTION and RETRY_WAIT. Duplicate clicks are disabled while the
  request is pending; failures remain visible and retryable. Completion refreshes
  the server financial-year context once, without a reload loop on page entry.
  Regression tests first reproduced the missing action. All 97 affected Console
  tests and scoped TypeScript passed, including wrong-company permission isolation,
  denied access, pending/error behavior and completed-run refresh. Manual review
  confirmed that the server still enforces company scope and retains the original
  initiating actor, completed steps and financial declaration. No API, permission
  definition or financial posting rule changed.
  Live verification used the action once for MCPB (`MONTE-CARLO-T79W`): books and
  FY2026-2027 were initialized, reports reached READY, and the page automatically
  reloaded with the financial year and current book details. The run is COMPLETE
  with seven READY steps and opening AWAITING_OPENING. The only reported posting
  blocker is unfinalized opening balances; DECIDE_LATER was preserved and no zero
  opening was submitted. The authorized opening review action is now visible.

- 2026-11-04: Readiness review fixed three stale/draft states: background completion
  now refreshes checks even without clicking retry; verified Accounting readiness
  updates a historically deferred opening to Finalised; and manual books refresh
  or automatic reload cannot discard a dirty, pending or uncertain opening form.
  Unavailable Accounting evidence keeps deferred openings historical rather than
  claiming they still need a decision. Each regression was reproduced before its
  fix. All 71 affected Console tests
  and scoped TypeScript passed. Coverage includes explicit zero confirmation,
  exact-request replay, scoped permissions, wrong-company responses and refresh
  behavior. Manual simplicity/security review found no further issue in these
  changes; review slash commands are unavailable in this environment.
  Live MCPB checks retained the unfinalized-opening blocker, preserved a test draft
  on refresh, and submitted no financial writes. A transient readiness timeout
  recovered through Refresh. The 390px layout had no horizontal overflow or runtime
  error. Financial-year, opening-review and report links returned 200 with the
  expected page headings and no browser runtime errors. MCPB's opening decision
  remains with its user.

- 2026-11-04: The three-step opening workflow uses a configured equity offset for
  entered Dr/Cr differences, as explicitly confirmed by the user. Chart v5 adds
  `OPENING_BALANCE_OFFSET` under Capital and `MIGRATION_CLEARING` under Current
  Assets. Existing chart initialization installs missing fixed defaults through
  the existing company lock, field policies, conflict checks and audit transaction;
  it preserves existing identities and does not post money. Existing companies
  must apply setup defaults before automatic opening can use an absent account,
  or select an eligible account in the worksheet's manual mode.

# Company management and financial-year implementation review

Reviewed: 2026-10-22. Findings below describe that review baseline, not the current
management UI. The 2026-10-23 implementation and verification are recorded in
[company management](company-management-review.md) and
[company/year management](company-year-management.md). C01 now has a reviewed recovery
UI for unused books; distributed pre-commit prevention remains separate work. C02/C03
wizard/date fixes, C04 new-setup guards, C05 verified selection, C06/C07 pagination and
C08 custom fields have subsequent fixes documented there. Historical evidence follows.

The backend has substantial company and fiscal controls, but the Console currently provides company creation, company selection and financial-year selection rather than complete management screens. The review found reproducible setup, lifecycle, validation and pagination defects. Passing existing tests does not cover these integration cases.

## Findings, ordered by priority

### C01 — P1: A permitted pre-posting company edit leaves Accounting unable to continue

Locations: `apis/identity/src/identity/api/companies.py:396`, `apis/identity/src/identity/domain/company_immutability.py:80`, `apis/accounting/src/accounting/tasks/fiscal.py:51`, `:91`.

Identity permits changes to books-begin date, fiscal anchor, base currency, amount precision and rounding before first posting, subject to pending-reservation and reference checks. Accounting saves these values when financial setup is initialized and rejects a later mismatch. Calling initialize again validates the existing snapshot instead of updating it. There is no supported reconciliation/reset command.

Reproduction: initialize Accounting with books beginning 1 April 2026; before any posting, change the company's books-begin date to 22 October 2026. Identity accepts this type of PATCH with HTTP 200. Accounting initialization with the updated signed facts returns HTTP 409, `authoritative company settings differ from financial setup`, and generation also rejects drift. Repeating initialize cannot repair it. Reverting the Identity edit restores the original configuration, but applying the intended correction is unsupported.

Evidence: separate in-process Identity and Accounting probes confirmed both sides with `first_posted_at = null`. The existing fiscal snapshot-drift test also confirms generation refuses mismatched facts. This was not a deployed, cross-service end-to-end test.

Recommended fix: provide an explicit, audited pre-posting reconciliation workflow that serializes with reservations, generation, opening balances, numbering and posting. Reject unsafe changes before committing the Identity edit; never weaken Accounting's drift guard or mutate posted history. [company.md §5.2](company.md) permits pre-posting editing, so freezing at initialization instead would require an explicit policy/document change.

### C02 — P1: The wizard opens a period that cannot cover a mid-year books-begin date

Location: `mfes/apps/console/app/components/CompanyWizard.tsx:384`.

The wizard correctly generates the year containing `books_begin_date`, but always chooses period sequence 1 to open. For an April–March company whose books start on 22 October 2026, April becomes OPEN while October remains FUTURE. The shared posting guard rejects April dates before books begin and October dates in a FUTURE period. The wizard nevertheless completes successfully. The Console offers no fiscal-management screen to correct this.

Evidence: a rendered wizard probe supplied April and October periods, entered the October books-begin date and asserted October was opened. It failed because the transition targeted April.

Recommended fix: select the period by its inclusive date range, require readable dates and a unique match, and open the period containing the books-begin date. Separately address pre-books-begin periods in the close/readiness workflow so they do not leave future closure permanently blocked by preceding-period rules.

### C03 — P2: Identity persists invalid fiscal anchors

Locations: `apis/identity/src/identity/schemas/company.py:46`, `:62`, `:168`; `libs/platform/src/billing_platform/company_context.py:66`.

Month and day are validated independently. Company creation accepts 31 April and persists it with HTTP 201; PATCH has the same missing combination check. The shared financial context validates the combination with `date(2000, month, day)`, and Accounting generation also rejects it. Consequently an apparently valid company cannot supply valid financial configuration. The wizard preview clamps short months, further obscuring the disagreement.

Evidence: an in-process company-create probe expecting HTTP 422 received HTTP 201 with month 4 and day 31.

Recommended fix: share the fiscal-anchor validation rule across create, merged PATCH values, context generation and preview. Validate before persistence, allow the supported 29 February anchor, and test impossible dates plus partial month/day updates. Audit any repair of existing invalid rows.

### C04 — P2: Closed companies still accept new statutory/setup child records

Locations: `apis/identity/src/identity/api/company_statutory.py:115`, `:309`, `:412`, `:511`; compare `apis/identity/src/identity/api/children.py:41`.

Company lifecycle declares CLOSED terminal for new activity. Contacts and currency writes use an active-company guard. Address, licence, statutory-ID and tax-registration creation load the company and check scope but do not check its status. Closing a company therefore does not consistently prevent new setup activity.

Evidence: close a company through the lifecycle API, then POST a new registered-office address with the same authorized actor. The address is created with HTTP 201; the probe expected HTTP 409. The other creation paths have the same missing guard by inspection.

Recommended fix: apply a shared active-company guard to new child activity under the company lock. Keep historical reads available and distinguish any explicitly permitted historical corrections from creation. Test both SUSPENDED and CLOSED companies across the affected paths.

### C05 — P2: A failed explicit company resolution is saved as a successful selection

Locations: `apis/identity/src/identity/services/session_context.py:216`, `mfes/apps/console/app/api/company-context/route.ts:55`.

For a tenant-wide actor, an explicit missing, inactive or foreign-tenant company resolves to HTTP 200 with `company: null`. The Console checks only the HTTP status before saving the requested UUID in its eight-hour selection cookie and returning success. Reloading then renders no company, and the stale explicit selection prevents the usual default/fallback resolution.

Evidence: the existing Identity session test intentionally returns `company: null` for a foreign company. A Console route probe supplied that successful-but-unresolved session response and confirmed `janso-company` was still written.

Recommended fix: require a resolved company whose ID matches the requested ID before setting cookies. Return a consistent refusal for an unresolved explicit selection and preserve the previous valid selection. Preserve step-up handling and avoid revealing cross-tenant existence. This is a context/recovery defect; the probe did not demonstrate cross-tenant data access.

### C06 — P2: The company directory loses first-page pagination metadata

Locations: `mfes/apps/console/app/lib/company-context.ts:78`, `mfes/apps/console/app/components/Companies.tsx:75`, `:84`.

The server loader reduces the session company page to an array and discards `has_more` and `next_cursor`. The directory initializes metadata to `has_more: false` and skips fetching the unfiltered first page. Thus Next is disabled even when the tenant has more than the first 50 accessible companies. Searching or changing the page size can fetch metadata, but ordinary browsing cannot reach page two; returning to the default first page can also retain stale metadata from another query.

Evidence: a rendered directory probe with a full 50-row first page confirmed Next remained disabled.

Recommended fix: carry the actual first-page metadata through the server context and directory props, and restore rows and metadata together when resetting the query. Test 51+ companies and search/page-size resets with real continuation cursors.

### C07 — P2: Fiscal selection uses unsupported sorting and ignores continuation pages

Location: `mfes/apps/console/app/lib/company-context.ts:93`.

Both financial-year and OPEN-period reads send `sort=start_date`, which the current generic Accounting list implementation does not allow for either fiscal resource. A real request returns HTTP 422, so the selector can be unavailable even with a single year. This additional mismatch was reproduced during reconciliation regression testing; successful mocked responses in the earlier loader probe concealed it.

If the sort mismatch is corrected, the loader still requests only the first 200 rows and ignores continuation metadata. Years beyond that page cannot be selected. OPEN-period rows can reach this limit with only 17 years of twelve open periods each, making later years appear to have no open periods and affecting fallback selection. More than 200 years is an edge case, but the API explicitly permits such data. A failed periods request is also displayed as all years having `open: false` without indicating that status could not be loaded.

Evidence: a context-loader probe returned a valid next cursor and a second year on the next page; the loader never requested or included it.

Recommended fix: align sorting with the service's allowlisted, indexed list contract, then use bounded pagination/search or an API-provided year summary that derives open status. Preserve the selected/current year even if it is outside the first page, and distinguish unknown period status from a confirmed absence of OPEN periods.

### C08 — P2: Company creation ignores the supported field-set/custom-field contract

Locations: `mfes/apps/console/app/components/CompanyWizard.tsx:66`, `:162`; `apis/identity/src/identity/services/field_metadata.py:63`.

The wizard uses hardcoded fields and required-field lists and never loads `/v1/entities/identity.company/field-set`. It cannot collect configured custom fields or honor their labels, requirements, conditions and write restrictions. In a tenant with a required custom company field without a default, the backend correctly rejects creation, but the wizard presents no input capable of resolving that validation failure.

Evidence: an Identity probe created a required tenant custom field before any company existed. Company creation without the value returned HTTP 422; supplying `custom_fields.cf_external_company_ref` succeeded with HTTP 201. Wizard inspection confirms it neither requests the field set nor renders a custom-field section. This contradicts the repository's form contract in CLAUDE.md invariant 15.

Recommended fix: render supported metadata through the shared form/custom-field components and submit authorized values. Keep domain immutability and backend authorization authoritative. Test a required custom field, a conditional field and a denied field.

## CRUD and management coverage

| Area | Current backend | Current Console | Assessment |
|---|---|---|---|
| Company | Create, paged list, detail, PATCH, separate lifecycle and visibility commands | Directory, search, open/default selection, creation wizard | Edit/detail, suspend/reactivate/close and visibility management screens are absent; directory paging has C06 |
| Setup/readiness | Jurisdiction/reference validation, company readiness, financial context | Country/currency suggestions, capability selection and preview | Does not expose a combined statutory/opening/fiscal readiness workflow; C01–C03 and C08 affect setup |
| Tax registrations | Create, paged list, constrained PATCH; immutable registration identity and effective-date rules | No management screen | Backend supports amendment through validity windows; no hard delete is appropriate |
| Statutory IDs | Create and paged list; restricted identifiers reduced to permitted stored values | No management screen | Detail/amendment/deactivation endpoints are absent in the reviewed router |
| Licences | Create and paged list; jurisdiction, date, duplicate and premises checks | No management screen | Amendment/retirement workflow is absent in the reviewed router; new-child lifecycle has C04 |
| Addresses | Create and paged list | No management screen | Individual amendment/deactivation/primary-switch workflow is absent in the reviewed router |
| Contacts, banks, documents | Separate scoped CRUD/lifecycle routes; banks have sensitive-read controls, documents have upload lifecycle | No company-management screens | These use active-company guards for ordinary writes; this review inspected their integration boundaries rather than exhaustively retesting every operation |
| Transaction currencies | Read and version-checked PUT, feature/reference validation and audit | No management screen | Distinct from reporting currency; enabling FX alone does not authorize every foreign currency |
| Company features | Catalogue, read, dependency-aware enable/disable and posting locks | Creation-time toggles | Later feature management is absent; dependency and lock tests pass |
| Financial setup | Read and idempotent initialize | Wizard initializes it | No reconciliation command; C01 |
| Financial years | Idempotent generation, paged list, detail, export, field metadata and readiness | Selector; first year generated by wizard | Existing-company/next-year generation and readiness management screens are absent; C07 |
| Fiscal periods | Paged list/detail, authorized transitions, exports, revision and transition evidence | Wizard opens one period; selector shows derived open status | No calendar/open/close/reopen/lock management screen; C02 and incorrect retry status handling below |

Fiscal-year CRUD is intentionally constrained. Years are generated from company configuration, with twelve contiguous monthly periods. There is no arbitrary year PATCH/DELETE, year-level status, `is_current` flag or annual-close command. Periods control posting. These omissions follow [fiscal-year.md](fiscal-year.md), rather than representing missing generic CRUD endpoints. Selecting a financial year changes display context; it must not change a document's posting date.

## Permissions, audit and controls verified

- Company create requires tenant-level `company.create`; read/update/lifecycle and child operations check their own scope. Tenant filtering prevents foreign objects from being read as local companies.
- Company PATCH enforces field-write policy, custom validation, jurisdiction/reference availability, pending-reservation protection and immutable-after-first-posting fields. Visibility changes have a separate permission and field-write check. Company `status` is not a configurable native form field; the absence of `CompanyAccess.assert_write` on lifecycle is therefore not evidence of a supported status-field-policy bypass.
- Financial initialization accepts narrow `accounting.finance.initialize` or broader `accounting.finance.manage`. Year generation and FUTURE→OPEN require `period.manage`; closing, reopening and locking have distinct permissions. Replaying a command still requires the corresponding original authority.
- Fiscal transitions compare `expected_version`, serialize on the Accounting company lock, enforce legal/preceding-period transitions and check pending journals, prepared voucher executions and reconciliation prerequisites. LOCKED is terminal. Initial openings are separately controlled; the wizard does not finalize them.
- Company changes and fiscal mutations emit audit evidence through the owning service's transactional outbox. Fiscal changes also retain revisions and dedicated transition records. Audit history should be read through the Audit API with scoped authorization; browser mutations should call the business API, whose transaction writes the audit event. A separate browser POST to Audit would lose atomicity.
- General company audit history is available through the existing audit UI, but these management screens have no embedded history. Accounting exposes scoped `/history/{resource}/{object_id}` and fiscal transition evidence. Adding management UI should integrate these existing readers rather than create another history store.
- Audit and operational logging remain distinct. The implementation uses transactional outbox delivery and the Audit service. The documented OpenTelemetry/Grafana architecture is not proof of deployed OTel SDK/export or W3C trace propagation; the current clarification is recorded in [audit.md](audit.md).

## Additional implementation observations

1. `CompanyWizard.tsx:394` marks every non-FUTURE first period as `Already open`, including CLOSED and LOCKED. A targeted rendered probe confirmed a CLOSED period is treated as success. Accept ordinary OPEN explicitly; show the actual state and require a separately authorized reopen workflow for other states.
2. Company create has no idempotency key. The in-memory company ID prevents repeating a create only after its response has been received. If the server commits and the response is lost, retry receives a duplicate-code conflict and cannot resume setup. Reloading after a later failure also loses the in-memory progress. Add a supported idempotent/recoverable provisioning workflow; uniqueness alone does not recover an unknown outcome.
3. Creation and bootstrap UI gates use flattened session permissions rather than grant scope. A company-scoped `company.create` can expose a wizard that the tenant-only API rejects; tenant create combined with accounting permissions only on an existing company can also start bootstrap for a new company that those grants cannot reach. Backend denial remains intact. Derive these gates from valid tenant grants and the actual target scope.
4. Company creation is not the complete atomic provisioning flow described by the older company design. The current wizard creates the company, enables features and initializes/generates/opens fiscal state in separate transactions. It does not create statutory registrations/licences, seed all document sequences, assign the creator a new company role, or finalize initial openings. Current [company-context-ui-todo.md](company-context-ui-todo.md) documents that narrower scope. Reconcile the older creation contract with the intended management workflow and represent incomplete setup explicitly.
5. Company settings PATCH and lifecycle do not offer a client version precondition, unlike fiscal transitions and currency allowances. Concurrent admin edits are therefore not surfaced to callers as stale-edit conflicts. Lifecycle also does not acquire the same explicit `FOR UPDATE` company lock used by setup writes. Review concurrency before adding multiple management screens; no live race was reproduced in this review.

## Verification and limits

Existing focused suites:

- Identity company models, immutable settings, lifecycle, setup/reference validation, session selection, features and company child models: **198 passed**.
- Identity company HTTP API and setup catalogues: **32 passed**; the additional pre-posting review probe passed in the same run (**33 total**).
- Accounting fiscal API/domain, financial audit and event suites: **21 passed, 9 skipped**. The skipped cases require native database/broker integration prerequisites.
- Console company wizard, directory, pages, context route, resolution, proxy policy and context picker: **135 passed** across seven files.

Disposable probes demonstrated failures of the expected behavior for mid-year opening, CLOSED-period success, unresolved selection cookies, fiscal continuation pages, company-directory Next, invalid fiscal anchors and closed-company address creation. Separate successful probes verified accepted pre-posting Identity edits, unrecoverable Accounting initialization drift and required custom-field enforcement. Probe files were removed after collecting evidence; this review adds only this report.

These were local SQLite/ASGI and rendered component checks, not deployed browser, native locking or full-system acceptance tests. No application fixes, migrations, commits or publishing were performed in this review. Fix C01/C02 and the validation/lifecycle defects before treating company provisioning as ready; then repair selection/pagination/custom-field integration and add the missing management screens with narrowly scoped audit history.

## Remediation status — 2026-10-22

The user authorized proceeding one finding at a time. The original verification section above records the review-only stage.

| Finding | Current status |
|---|---|
| C01 | Accounting recovery implemented for unused books through an explicit, version-checked, audited command. Identity prevention before committing unsafe company edits and a complete management workflow remain pending. |
| C02–C08 | Pending. C07 now also records the confirmed unsupported `start_date` sorting. |

An automated content filter blocked the subsequent Identity/Console patch batch. That action was not retried. Independent verification and documentation of the existing Accounting change continued. No commits or publishing were performed. [Fix evidence](company-financial-year-fixes.md) records the API, safeguards, test results and limits.

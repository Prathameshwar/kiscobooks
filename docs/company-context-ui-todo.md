# Company context and company creation — live checklist

The subsequent priorities 1-4 company foundation work (2026-10-23), including settings
ownership, shared scoped navigation and the read-only readiness screen, is recorded in
[company-foundation-todo.md](company-foundation-todo.md) and
[company-foundation-review.md](company-foundation-review.md).

Part 1 (**UI only**) of the two-part delivery agreed on 2026-10-21, and **Part 2 (the Identity
APIs), authorized and delivered on 2026-10-22**. Keep this file current as each phase closes;
it is the live checklist, not a design document. The durable statement of the resolution chain,
the switcher's self-read list and the default-company self-write is
[org-model.md](org-model.md) §4.6.

**Scope:** default company and default financial year resolution, display in the left rail with
switching, and a company-creation wizard reachable post-login when no company exists.
Related: [company.md](company.md) · [company-setup.md](company-setup.md) ·
[voucher-financial-year-design.md](voucher-financial-year-design.md) ·
[design-system.md](design-system.md) · [roles-permissions.md](roles-permissions.md)

## Agreed decisions

| # | Decision | Date |
|---|---|---|
| D1 | Company creation, including the first financial year, is an **administrator** capability — offered to `tenant_admin` / `company_admin`-kind users. Part 2 adds the narrow `accounting.finance.initialize` key plus `period.read`/`period.manage` to those roles; `accounting.finance.manage` (opening balances) stays with `controller` | 2026-10-21 |
| D2 | Actors without `company.read` (clerks, controller) get their switcher list from a new grant-derived self-read `GET /v1/session/companies` in Part 2. Until then their switcher is empty and says so | 2026-10-21 |
| D3 | Delivery is split: Part 1 UI only (wired to endpoints that already exist), then Part 2 APIs and end-to-end | 2026-10-21 |
| D4 | Fiscal-year selection is **display and filter context only**. It never feeds `posting_date` (CLAUDE.md invariant 4; financial-year design §3 permits a scoped preference) | 2026-10-21 |
| D5 | That self-read is derived from **grants only**, never from memberships. A company someone is affiliated with but holds nothing in would be a switcher row that refuses to open, since the chain and every later request still check the permission | 2026-10-22 |
| D6 | Per-country setup suggestions live in Identity's domain, not in `billing_platform.jurisdiction`: nothing outside company creation reads a fiscal anchor or a date format, and replicating them into `vouchers`/`reports` would imply they govern something there | 2026-10-22 |

## Part 1 phases

- [x] **UI-1 · `@janso/ui` context switchers** — `ContextSwitcher` popup (listbox, search, footer
      actions, loading/empty/error), `OrgSwitcher` extended with an icon/compact trigger variant,
      CSS in `shell.css` + `overlay.css`, collapsed-rail behaviour, tests.
      *23 tests; `TextField` now forwards its ref so a popup's filter can take focus.*
- [x] **UI-2 · `@janso/ui` wizard primitives** — `WizardLayout` (owns the form, `noValidate` and
      step-change focus), `FieldGrid`, `ReviewList`, `Stepper` `reached` + incomplete state,
      `Checkbox` described `hint`, `asErrorStatus`, `businessToday`, CSS in `setup.css`, tests.
      *`apps/auth` `/setup` still hand-composes the same classes and should migrate to
      `WizardLayout` rather than growing a second copy.*
- [x] **UI-3 · Console data layer** — `lib/company-context.ts` (the Part 2 seam), `api/company`,
      `api/company-context` cookie writer, resolution rules, tests. *Extracted
      `lib/service-proxy.ts`, `lib/service-call.ts`, `lib/json-request.ts` and `lib/services.ts`
      rather than growing second copies of the proxy, the client envelope, the bounded body read
      and the service-origin table; `platform` and `product-fields` now use all four.*
- [x] **UI-4 · Console shell integration** — rail switcher + year selector, top-bar chips,
      `/companies` directory with keyset paging, shared "no company" empty state,
      `lib/page-context.ts`, removed the duplicate `/v1/session` fetches from four pages, tests.
      *A company-scoped page now tells a missing company (`NoCompany`) apart from a company the
      role cannot read (`ErrorState 403`), which the old "Select a company" copy conflated.*
- [x] **UI-5 · `/companies/new` wizard** — six steps, feature step with dependency closure,
      review and create as a retryable sequence, post-login redirect from the dashboard, tests.
      *Keys for the books commands are derived (`init-<company>`, `fy-<company>-<year>`,
      `open-<period>`) so a retry replays; the company id from the first attempt is reused, so a
      retry never creates a second company. The wizard suggests the currency's own symbol,
      because Identity stores only an override and otherwise every document prints
      `INR 1,200.00`.*
- [x] **UI-6 · Review and fixes** — `/simplify` (four review agents) and `/security-review` run;
      findings applied below; `@janso/ui` bumped to 0.1.15 (both consumers are `workspace:*`, so
      the lockfile records a link and needs no edit); docs and decision logs updated.

### Applied from the quality review

- One company→row mapper and one list query shape (`lib/company-list.ts`), replacing three
  copies that had already drifted — a searched row in the directory had lost its "Default" badge
  and the three callers asked for three different limits.
- One client call envelope (`lib/service-call.ts`): the **replay rule is now stated once** —
  a GET, or a write carrying an idempotency key, may be replayed after a token refresh; a
  keyless write may not. Three copies previously disagreed about it.
- `openCompany` in `lib/company-api.ts`: one path records a selection, hands a company that
  wants verification to auth, and re-renders. The step-up branch existed twice before.
- `api/platform` moved onto the shared proxy (it had kept its own token preflight and the
  `new URL(path, base)` form that drops a gateway path prefix); the proxy now also rejects an
  unrecognised envelope field for all three routes.
- One service-origin and company-scope table (`lib/services.ts`) for both the server-side reads
  and the browser proxy; `companyInPath` is anchored, where one of the two copies was not.
- Round trips per console page went from four serial to three: the company list now starts
  before the session is awaited and is shared by the chain and the rail, and the two fiscal
  queries run together. The display config stays sequential on purpose — the fiscal resolution
  needs the company's timezone to decide which year contains today. A session's *first* page
  load went from five or six hops to three, because the chain no longer probes the company list
  separately from the rail's copy of it.
- Wizard: `clearMessages` so every field clears its server message the same way (the legal-name
  field did not), a recursive `dependsOn` for turning a feature off (the old version assumed the
  catalogue was at most three deep), one `TASK_BADGE` table instead of two parallel ternary
  chains, the review list built only on the step that reads it, and no grid nested in a grid.
- `/companies` is keyset-paged with `useListQuery` + `Pager`, so company 51 is reachable.

### Applied from the security review

No reportable vulnerability. One real divergence was closed: the allowlists validate a path
against a bare origin, while the proxy resolves it against a base that may carry a service
prefix — and `%2e%2e` is a dot segment to the URL parser but not to a literal `'..'` check, so a
surplus one was absorbed during validation and would have popped the prefix during the request.
`proxyServiceRequest` now resolves the target once and refuses unless it *is* the approved route
under the configured prefix, which states the invariant in one place for all three routes. Its
impact today was a gateway 404 rather than a reachable endpoint, but the reasoning it required
was the problem.

Paths checked and found closed (recorded so the next review need not re-derive them): allowlist
bypass by traversal, encoded separators, protocol-relative or absolute re-pointing, query
smuggling and method confusion; `__proto__` and duplicate JSON members in the envelope; bearer
token and step-up proof exposure, and the company a proof is attached to (`companyInPath` is
anchored and leftmost-first, so a company id injected into a query value cannot win over the
path segment); cookie forgery before verification, cookie value mis-parsing, and cookie
attributes against the other writer of the same name; CSRF on all four console POST routes;
idempotency-key reuse across actors (closed server-side — the command digest includes the
actor); open redirect through `stepUpUrl`'s `returnTo` (auth validates the origin); and PII or
secrets in logs, cookies or URLs.

### Deferred, with reasons

- **`usePopupList` in `@janso/ui`** — `Menu`, `UserMenu`, `SearchSelect`, `CommandPalette` and
  `ContextSwitcher` each own a copy of the portalled roving-index/dismissal contract. Extracting
  it is the highest-value remaining cleanup, and it touches four tested components outside this
  feature, so it belongs in its own change. Once it exists, `ContextSwitcher`'s `search` slot
  should take `SearchSelect`'s loader shape so the debounce contract stops being the caller's.
- **One `safeRelativePath` for the five `*-request-policy.ts` files** — the traversal guard is
  copied six times now. Security-relevant and worth doing; four of the files are outside this
  change.
- **`router.refresh()` instead of a full reload after a switch** — faster, and it keeps client
  state; it puts a router dependency into two otherwise router-free components, so it is a
  follow-up.
- **Lazy company list** — the rail ships up to fifty rows on every page for a panel most views
  never open. Loading on first open would remove a round trip per page at the cost of a
  skeleton.
- **Jurisdiction defaults on `CountryChoice`** — the wizard's suggestion table for `IN`/`GB`
  duplicates facts the jurisdiction profile already owns. Part 2 should carry the fiscal anchor
  and display conventions on the endpoint the wizard already calls, leaving only the neutral
  fallback in the client.

## Part 1 degradations — all closed in Part 2

Each was visible in the UI rather than silent, and each is now gone:

- [x] Admin roles finished the wizard **without** books + first fiscal year. **Closed:** the
      bootstrap keys are seeded, and the page accepts *either* `accounting.finance.initialize`
      (the administrator's narrow key) or `accounting.finance.manage` (the controller's wider
      one). Requiring `manage` kept showing administrators the hand-off after they had been
      granted the key that works.
- [x] Clerk/controller roles saw an empty switcher. **Closed:** `GET /v1/session/companies`
      (D2, D5) serves them, and the rail and the `/companies` directory both read it.
- [x] No "Set as my default". **Closed:** `default_company_id` on
      `PATCH /v1/session/preferences`, offered in the switcher's footer when the open company
      is not already the default. The 8 h cookie still decides *this browser*; the stored
      default decides the next session.
- [x] Resolution chain lived in the console. **Closed:** it is
      `identity/services/session_context.py`, so mobile will share it; the primary-`membership`
      step exists, and the console's second session round trip is gone. This also fixed a real
      bug — the console's last step sent its fallback back as an *explicit* selection, which
      turned a first-readable company that requires step-up into a 403 on the whole page
      instead of a prompt.
- [x] Fiscal-year selector hidden from admins until `period.read`. **Closed:** the seeded
      administrator roles hold `period.read` and `period.manage`.

## Part 2 — delivered 2026-10-22

**No migration was needed.** `user.default_company_id` already had its column, FK and indexes,
and `membership.is_primary` already existed, documented as "drives default company on login".

- [x] Identity: `/v1/session` resolution chain (explicit → `default_company_id` → primary
      membership → first readable) + `selected_source`, plus `selected_company_id` and
      `step_up_required` so a company awaiting verification is distinguishable from no company;
      `GET /v1/session/companies`; `default_company_id` on `PATCH /v1/session/preferences`.
      *The grant-scope narrowing that `GET /v1/companies` had inline is now
      `identity/domain/company_scope.py`, shared by all three readers rather than copied twice
      more. `default_company_id`/`default_department_id` joined Identity's audit allowlist, so
      the change is recorded rather than `[redacted]`.*
- [x] Permission catalogue: `accounting.finance.initialize`; `tenant_admin` / `company_admin`
      gain it plus `accounting.finance.read`, `period.read`, `period.manage`; seeds and
      `roles-permissions.md` §2/§4/decision log
- [x] Accounting: `financial-setup/initialize` accepts the new narrow key
- [x] Nice-to-haves the UI had to work around: `requires_step_up` on `CompanyListItem` **and**
      on the switcher's own rows, a feature catalogue at `GET /v1/company-features`, and
      `setup_defaults` on `CountryChoice` (D6). All three client copies are gone; the wizard
      keeps only a neutral starting point for the moment before the first response lands.
- [x] Regenerated `clients/api-client`; the console's chain is deleted, and the rail, the
      directory and the server-rendered first page all read the one self-read list;
      cross-tenant isolation asserted on every new endpoint.

### Evidence

- Identity: four new test files (the chain, the self-read list, the stored default, the two
  catalogues) plus two pure-domain files (the scope narrowing, the suggestion table) — **55 new
  checks**; 170 existing company, reference and feature checks still green. Ruff and mypy
  strict clean across 176 source files.
- Console: **724 checks green** across 66 files, including 7 new switcher checks (the default
  action and its refusal, the verification prompt, the step-up marking, the self-read search)
  and 2 new `setDefaultCompany` checks. `@janso/ui` 1,781 checks unchanged. `tsc --noEmit` and
  the production build pass.
- `GET /v1/companies` left the console's request allowlist: nothing asks for it any more, so it
  is denied by default again.

### Still open

- [ ] Mobile has no company switcher. The chain is server-side now, so that is a client change.
- [ ] `openCompany` still does a full reload rather than `router.refresh()` — deferred for the
      same reason as in Part 1 (a router dependency in two otherwise router-free components).

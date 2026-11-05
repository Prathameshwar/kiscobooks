# Notification UI implementation reviews

Scope: the approved UI01-UI09 plan, both ownership roots, production Notification
proxy/API integration and the narrow API additions required by these screens. The
earlier provider/worker implementation reviews remain in
[notification-platform-tenant-reviews.md](notification-platform-tenant-reviews.md).

Review date: 2026-10-23. No separate `/simplify` or `/security-review` tool was
available in this session. Both passes were performed manually, with code inspection,
regression tests and browser execution; they are not independent external audits.

## Pass 1: authority, ownership, privacy and command replay

Inspected section/card/shell permission gates, direct server routes, proxy allowlist,
server credentials, owner/company changes, API actor/session scope, provider reference
selection, endpoint masking, policy writes, history realm and command receipts.

Findings fixed:

- Credential binding discovery used a database-space context outside the DB dependency
  scope and returned no choices in a real browser. It now derives the allowed space
  from the verified actor and configured platform identity; tenant/platform binding
  catalogues remain separate.
- New consent/suppression job receipts could fall through the provider-read mapping.
  Their job-detail reads now require their own policy permission family. A provider
  reader cannot inspect policy command metadata through that fallback.
- Route creation lacked replay protection after a lost response. Optional command
  receipts now replay a matching body and reject a different body under the same key.
  Consent and suppression writes use the same existing owner-bound receipt mechanism;
  consent also keeps its stable source evidence key. Existing clients may omit the
  optional header.
- Consent accepted arbitrary states or invalid evidence windows. Enumerated states,
  ordered expiry/occurrence and bounded future occurrence are validated server-side.
  Suppression windows/scope/category are validated and email hashes are normalized.
- All-company tenant audit emitted the sentinel as a business company. The emitter
  and UI now normalize it to tenant-wide history while retaining real company scopes.
- Server navigation helpers imported the client API module. Ownership and permission
  helpers now live in a server-safe module; server cards use no client exports.

Verification covers exact new proxy methods/queries, forged ownership rejection,
stable command forwarding, tenant/platform API isolation, policy receipt authority,
idempotent body comparison, enum/date rejection, normalized suppression identity,
all-company audit scope and policy-only card access. The proxy never exposes callback
or internal-source paths. Destinations are excluded from URLs and persistent browser
storage; message HTML is rendered as inert source.

## Pass 2: workflows, navigation, recovery and presentation

Inspected setup order, deep routes, paged selectors/tables, job polling, form failure
retention, concurrency errors, provider-authoritative approval, activation dates,
delivery evidence, retry/reconciliation confirmation, labels/hints and theme reuse.

Findings fixed:

- Channel readiness includes `channel_disabled`; that reason alone no longer prevents
  enabling an otherwise configured account.
- Detail back links now return to the actual parent template/variant/provider record.
- Masked endpoints no longer pass through a second table masking formatter.
- Activation inputs now preserve seconds and local timezone, avoiding a rounded
  immediate activation being rejected as too far in the past.
- Shared form controls connect errors and hints with accessible descriptions. Required
  fields, typed values and API field errors keep the dialog open for correction.
- Activation history refresh uses local parent state instead of a global browser
  event, avoiding unrelated owner/workspace refreshes.
- Resource loads abort on route/owner/company changes; action locks prevent duplicate
  submissions. Pending checks poll with a bounded lifetime and support manual refresh.
- Source links require matching company and source permission. Recovery lists retain
  unresolved sends and only offer server-authorized retry/evidence commands.

The browser fixture initially used the default email channel when inspecting an SMS
route and created a tenant endpoint without its company reference. Those fixture
assumptions were corrected; production authority/planning checks were preserved.
Existing tenant channels intentionally start enabled, so the tenant journey explicitly
exercises disable followed by enable.

## Final verification evidence

- Affected Console component/proxy/page tests: 113 passed, followed by four page tests
  including two additional deep-route assertions. Complete Console suite: 863 passed
  with bounded concurrency. Console TypeScript passed after the final changes.
- Complete Notification API suite: 220 passed, including all three native MySQL 9.6
  cases (migration/space constraints, concurrent version/activation and serialized
  dispatch/capacity). Domain coverage: 98.80%, above the required 90% floor.
- Notification Ruff and strict mypy: clean (58 source files). OpenAPI and signed audit
  contract drift checks: clean. Generated Notification client drift, client TypeScript
  and all eight transport tests: passed.
- Browser scope: production UI + real notification proxy + production API/planner/
  dispatcher/native signature verification, using fixture authentication and external
  providers. Platform email/SMS/WhatsApp, tenant SMS, read-only API denial and narrow
  light/dark/ledger layouts all passed. Screenshots were visually inspected with no
  horizontal overflow at 390px. Local artifacts are under
  `.tools/notification-ui-browser-c50f7ad5a3214b1fadc9c1ddce6e9a29`.
- A broad Console run hit two role-editor timing failures under unrestricted parallel
  load; the unchanged role suite passed in isolation and the bounded-concurrency full
  run passed all 863 tests. Unrelated role implementation was preserved.

Remaining operational limits are explicit in [usage](notification-ui-usage.md): no
global recipient directory, arbitrary send/campaign UI or attachment/media authoring;
no claim of a real IdP, cloud account, Audit-service browser or public HTTPS canary.
Production activation remains governed by [operations](notification-operations.md).

Both passes are complete with their fixes verified and no remaining blocking local
findings. The final check also confirmed clean task-file whitespace, fixture process
cleanup and shutdown of the disposable loopback MySQL used for the suite. Existing
unrelated edits and local folder mappings were preserved; nothing was committed or
published by this UI task.

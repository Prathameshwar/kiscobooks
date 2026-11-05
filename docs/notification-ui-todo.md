# Notification UI execution TODO

Plan: [notification-ui-plan.md](notification-ui-plan.md).

Status: implementation authorized on 2026-10-22; proceeding sequentially. This is a separate
UI refinement/coverage track; the earlier API implementation and its baseline UI remain
recorded in notification-platform-tenant-todo.md.

- [x] Inspect existing notification screens, Platform card, proxy/API coverage and shared UI.
- [x] Prepare a sequential plan using existing styles, CSS, layout and components.
- [x] UI01: platform Notification card, overview, section routes and shared area foundation.
- [x] UI02: channel readiness/controls and provider account management.
- [x] UI03: provider-scoped sender setup, verification and lifecycle.
- [x] UI04: channel/language templates, typed variables, versions and previews.
- [x] UI05: activation history, WhatsApp approval and dated purpose assignments.
- [x] UI06: routing and server-authoritative effective-policy inspection.
- [x] UI07: recipient lookup, consent and suppressions, including proxy/entry gates.
- [x] UI08: request/delivery detail, signed receipts and authorized recovery.
- [x] UI09: contextual Audit, accessibility/theme checks and integrated journeys.
- [x] Final review 1: security/ownership/command replay; fix findings and verify.
- [x] Final review 2: usability/navigation/recovery/integration; fix findings and verify.
- [!] Actual provider/IdP/HTTPS certification and deliberate deployment/activation remain
  external gates; local UI tests do not replace them.

For each phase, record changed screens, reused components, API prerequisites, checks
run and remaining findings before marking it complete. Preserve existing unrelated work.

UI01-UI03: direct owner routes, overview, provider account and sender lifecycle screens
implemented using shared components. Console TypeScript and 16 area/page tests passed.
Provider/credential conflict, validation replay, native account forms and sender
provider mismatch gates are covered. Further integrated coverage follows in UI09.

UI04-UI06: template/variable/channel/version editing, inert previews, dated activation,
purpose assignments and routing/effective policy are connected. Seventeen area tests
and console TypeScript passed. Route detail/edit now includes existing retry/backoff
settings; the scoped API regression passes. The affected existing API suite passed 17.

UI07-UI08: bounded masked recipient lookup, evidence-backed consent, suppressions,
request/outcome history, delivery attempts/timeline, receipt inbox and verified recovery
are connected. Thirteen area tests passed; four new real API contract tests cover
policy replay, validation, cross-owner access and route-policy editing. The complete
new-area suite passed 46 tests before final audit/accessibility additions.

UI09 and final verification completed on 2026-10-23:

- Contextual platform/tenant Audit uses existing history components, lazy reads and
  separate authority. Added all-company audit normalization, accessible field error/
  hint associations, parent navigation, owner-change cancellation and local history
  refresh. Existing shared CSS, layout and all three themes are reused.
- Review 1 fixed owner-specific credential discovery, policy job-read authority,
  route/policy command replay, policy validation and tenant-wide audit scope.
- Review 2 fixed channel-enable readiness, parent routes, double-masked addresses,
  local activation precision, field descriptions and cross-workspace refresh behavior.
  Both manual reviews have no remaining blocking local findings; unavailable dedicated
  review commands and operational limits are recorded in the review document.
- Complete Notification API suite: **220 passed**, including all three native MySQL
  9.6 cases; domain coverage **98.80%** (90% minimum). Ruff and strict mypy clean
  (58 source files); OpenAPI and signed audit-contract drift checks passed.
- Complete Console suite: **863 passed** with bounded concurrency. The affected-area
  run passed 113, followed by four deep-route/root page tests. Console TypeScript
  passed. Two role-editor timing failures in the unrestricted run passed in isolation
  and in the final complete run; no unrelated role changes were made.
- Generated Notification client drift, client TypeScript and **8 client tests** passed.
- Real browser-to-proxy-to-API fixture journeys passed for platform email, SMS and
  WhatsApp plus tenant SMS: provider -> sender -> channel -> template/preview ->
  approval/activation -> assignment -> routing -> source staging -> dispatch ->
  signed receipt -> request/delivery history -> masked recipient -> consent.
  Read-only controls and API write denial passed. Mobile 390px layouts had no horizontal
  overflow in light/dark/ledger; screenshots were visually inspected. Artifact folder:
  `.tools/notification-ui-browser-c50f7ad5a3214b1fadc9c1ddce6e9a29` (ignored local data).
- Browser services cleaned up by the runner; the disposable MySQL instance started
  for these checks was stopped. No live provider configuration, message submission,
  application migration, commit or publication was performed.

Details: [two reviews](notification-ui-reviews.md), [operator usage](notification-ui-usage.md).

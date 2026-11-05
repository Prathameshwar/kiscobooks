# Notification administration UI: phased plan

Proposed 2026-10-22, after the API implementation and final review. This plan covers
the console management experience, starting with platform administration. It builds
on the existing implementation; it does not mark these UI improvements implemented.

## 1. Existing foundation and gaps

- The Platform administration page already has a **Platform notifications** ActionCard
  linking to `/platform/notifications`. Tenant Settings links to
  `/settings/notifications`. Keep both entry points and their existing shell selection.
- Both pages currently render `NotificationWorkspace`, with six local-state tabs:
  Channels, Providers and senders, Templates and purposes, Routing, Requests, Deliveries.
  Creation, previews, several lifecycle actions, paging and receipt inspection exist.
- The current workspace uses shared UI primitives but groups many unrelated forms and
  detail states together. It lacks durable section navigation, fuller edit/detail flows,
  dedicated activation/assignment history, recipient/consent/suppression management,
  effective-policy inspection and a complete reconciliation workflow.
- The generated Notification client, server-side notification proxy, signed platform
  gateway and separate tenant/platform APIs already exist. The proxy currently excludes
  recipient-endpoint, consent and suppression routes even though the API exposes them.
- Existing platform card/navigation gates cover provider/template/route/request/delivery
  readers. Recipient-only and consent/suppression operators need corresponding entry
  visibility when those sections are delivered. A broad platform-admin role check must
  not replace section-specific permissions.

## 2. Navigation and layout

Entry flow: **Platform administration -> Platform notifications card -> Notification
overview -> one management area**. Use `/platform/notifications` as the stable home.
Tenant entry remains **Settings -> Notifications**, under `/settings/notifications`.

Use explicit routes for sections and substantial details, with the same relative paths
under each owner root. Proposed sections:

| Section | Main purpose |
|---|---|
| Overview | Email, SMS and WhatsApp readiness and next configuration action |
| Channels | Enablement, prerequisites and readiness explanations |
| Providers | Account setup, credential binding, validation and callback configuration |
| Senders | Sender identity setup, verification, status and maintenance within a provider |
| Templates | Purpose, channel/language variants, immutable versions and previews |
| Purpose assignments | Registered event/trigger -> channel/template, with effective dates |
| Routing | Provider/sender selection, delivery policy and effective-policy check |
| Recipients and policy | Masked endpoints, consent state and suppression administration |
| Requests | Planning history and per-channel outcomes |
| Deliveries and recovery | Delivery history, attempts, receipts and reconciliation cases |

Providers own their sender detail routes; templates own variant/version detail routes.
Receipt/recovery views can be subviews of Deliveries. Use shared Tabs or action-card
navigation for primary areas and shared PageNavigation for explicit breadcrumbs/back
destinations. Every supported section/detail can be bookmarked and opened directly;
back navigation restores supported filters and cursor state. Do not encode secrets,
destinations, preview variables or form drafts in URLs.

The platform header identifies **Platform notifications** and describes platform staff
and pre-tenant delivery. The tenant header identifies **Tenant notifications** and the
applicable company context. Platform pages never inherit the selected business company.
Ownership comes from the page boundary, not a client-supplied cross-tenant selector.

## 3. Style and component reuse

Preserve `ConsoleShell`, `Providers`, `janso-page`, existing page width/spacing and the
Platform/Settings card grids. Reuse these existing `@janso/ui` components as appropriate:

- PageHeader, PageNavigation, SectionHeader, ActionCard, Card/CardHeader/CardBody.
- DataTable, Toolbar, Badge, Tabs and existing opaque-cursor paging patterns.
- TextField, Select, SearchSelect, FieldGrid, WizardLayout/Stepper and ReviewList.
- Drawer/Modal for short contextual tasks; full pages for longer template/setup flows.
- ConfirmDialog, Notice, EmptyState, ErrorState and Skeleton.
- `useFormatters` and the existing display configuration for dates/times.
- PlatformHistory and existing tenant Audit components for authorized change history.

Use the styles already supplied by `shell.css`, `data.css`, `table.css`, `overlay.css`
and the existing form styles. No notification-specific stylesheet, hardcoded colors,
new visual theme or UI dependency is planned. If a missing reusable pattern is found,
extend the shared component/styles and its tests instead of creating app-local copies.
Keep light/dark/ledger, narrow screens, labels, focus and keyboard use working.

## 4. Delivery phases

Implement and verify one phase before starting the next. Each phase leaves existing
notification workflows usable. Platform admin is the first demonstrated flow; shared
screens are also verified through their tenant route and permissions as they land.

### UI01 - Platform card, overview and navigation

- Preserve and refine the existing Platform notifications card and its description.
- Add the overview and explicit section navigation, breadcrumbs and back destinations.
- Show Email/SMS/WhatsApp readiness from the channel API, with meaningful labels and
  links to the missing setup step. Existing push support remains secondary.
- Split the large workspace into area components while preserving tested actions.
- Establish shared loading/error/empty/forbidden behavior and owner-scoped route helpers.
- Show only sections available to the current permission set; support direct visits
  and users with permission to only one section. Add policy-only entry gates in UI07.

Acceptance: the platform card opens the platform overview; direct links and browser
back work; tenant and platform screens cannot exchange data or pending form state.
No delivery statistics are inferred from the first page of a list.

### UI02 - Channel controls and provider account management

- Build the channel readiness view, readable prerequisite reasons and enable/disable
  confirmations. Explain configuration readiness separately from actual live delivery.
- Build a paged provider table and account detail/create/edit forms for SES, Twilio
  and Meta, with channel-specific fields, clear help and field validation.
- Select registered credential references; show a useful unavailable-credentials state.
  Secret creation/storage remains in the existing operator configuration boundary.
- Support optimistic edit conflicts, validation jobs and bounded job-status refresh.
- Show callback URL/signature scheme from the API with copy actions and safe guidance.
- Explain when credential/region changes invalidate verification. Preserve command
  identity on uncertain responses; stop polling on navigation or terminal job status.

Acceptance: a platform admin can configure and validate a provider, inspect a failed
job, edit a stale record safely, and understand why a channel cannot yet be enabled.

### UI03 - Sender identities

- Provider-scoped sender table, detail/create/edit forms and verified-state badges.
- Appropriate inputs for email identities, SMS numbers and WhatsApp phone IDs.
- Verify/sync jobs, pending/failed outcomes, activation/deactivation and confirmations.
- Make re-verification requirements visible after account changes or reactivation.
- Use paged provider/sender selectors and clear choices when dependencies change.

Acceptance: an admin can take a sender from creation through provider verification;
unverified/inactive senders are clearly distinguished from usable route choices.

### UI04 - Template content, languages and versions

- Paged template catalogue and detail/edit pages, purpose/category and active state.
- Channel/language variants with typed variable definitions and required-field rules.
- Dedicated Email, SMS and WhatsApp editors using shared form/layout components.
  WhatsApp editor supports the existing positional text header/body/URL-button contract.
- Immutable version creation, version detail/history and sample-variable previews.
- Display limits and validation errors clearly. Render previews safely; do not insert
  untrusted HTML into the console document.

Acceptance: an admin can create and preview each supported channel template, change
language, create a new version and inspect older versions without mutating them.

### UI05 - Activation, WhatsApp approval and purpose assignments

- Activation history, immediate/scheduled activation, end dates and rollback by
  selecting an existing immutable version. Show a review step before changing live use.
- Bind WhatsApp versions to provider templates and display provider-authoritative
  pending/approved/rejected sync results. Never offer a local approval toggle.
- Dedicated registered purpose/trigger/channel/template assignment forms and history,
  with effective dates and readable company scope on tenant pages.
- Explain missing assignment, inactive locale/version, conflicting dates and missing
  WhatsApp approval using the API's result rather than a second client policy engine.

Acceptance: platform invitation/staff-alert purposes and tenant voucher purposes stay
separate; an admin can establish and inspect a complete executable assignment.

### UI06 - Routing and effective-policy inspection

- Paged route table plus detail/create/edit/enable/disable flows.
- Resolve human-readable template/provider/sender labels through authorized API reads;
  retain reference IDs in a secondary technical-details disclosure.
- Expose supported priority, weight, timeout, retry/backoff and scope controls with
  validation and sensible explanations; keep advanced controls in a disclosure.
- Add the existing effective-policy check for purpose, trigger, channel and tenant
  company context. Link returned route/version to their details.

Acceptance: an admin can configure a route and use the server's policy result to find
an incomplete provider/sender/template/assignment setup without sending a message.

### UI07 - Recipients, consent and suppressions

- Add exact proxy allowlist entries and generated DTO aliases for these existing APIs.
- Add authorized, masked endpoint lookup by the API's required subject reference and
  contextual links from source/request/delivery screens where references are available.
- Keep platform staff/pre-tenant endpoints within platform storage. Recipient lookup
  does not imply tenant membership or permission to edit the source-owned destination.
- Show consent state by endpoint/purpose; add evidence-backed consent event forms and
  suppression list/create/expire flows, including date/scope/channel and confirmations.
- Use current permissions: recipient.read, consent.manage and suppression.manage,
  translated to their exact platform families. Current consent/suppression reads also
  require manage permission; do not invent read grants in the UI.
- Extend Platform/Settings card and shell gates for operators who only have these
  permissions. Keep policy explanations consistent with the existing category rules.

Acceptance: authorized operators can manage recipient policy without exposing raw
stored destinations or entering another owner's space. Verify server-side allowed
states/scope/date validation before exposing writes; close any API validation gap in
the same phase with backend tests and regenerated contracts where needed.

The existing endpoint API requires a known subject ID and has no global recipient
directory/search. A browsable directory or friendly source-reference lookup is a
specific API prerequisite if required, not something a screen can synthesize by
fetching all delivery pages. Until then, use bounded reference/context lookup.

### UI08 - Request history, delivery history and recovery

- Add request and delivery tables with only API-supported filters/sorts, opaque paging
  and shareable non-sensitive view state. Do not invent unsupported date filters.
- Request detail shows source/purpose, planning completion and each channel's reason.
- Delivery detail shows frozen lineage, attempt history and timestamped receipt/state
  events. Distinguish planned, provider-accepted and delivered outcomes.
- Make receipt inbox and reconciliation cases first-class operational views. Link
  matching verified receipt evidence through the existing reconciliation command.
- Explain ambiguous sends and retry eligibility. Confirm permitted manual retries,
  retaining their original idempotency key/body after lost responses.
- Link back to source records only when the actor has source access; keep safe
  references available when that source cannot be opened.

Acceptance: an admin can trace a request to its delivery, identify a skipped/failed
channel, inspect an ambiguous attempt and perform only API-authorized recovery.
Arbitrary manual sends, bulk campaigns and a new test-send API are outside this UI plan.

### UI09 - Audit integration and final verification

- Add contextual history to provider/sender/template/assignment/route/policy records,
  using existing platform/tenant history surfaces and exact permission families.
- Finish accessible focus/keyboard behavior, mobile layouts and all three themes.
- Execute platform admin journeys for email, SMS and WhatsApp, staff/pre-tenant
  histories, tenant-scoped equivalents, read-only users and limited-permission users.
- Review 1: permissions, ownership, sensitive data, proxy routes and command replay;
  fix findings and run regressions.
- Review 2: navigation, usability, error/recovery behavior and API/UI integration;
  fix findings and rerun affected checks. Record unavailable review tooling explicitly.

Acceptance: no blocking local findings; completed per-phase evidence and TODO. Real
provider/IdP/HTTPS canaries remain the existing deployment gate.

## 5. Verification and API boundaries

Every phase adds meaningful UI tests for rendering, conditional permissions,
validation, success/failure/pending behavior, focus/labels and stale owner/company
responses. Run affected Vitest tests and console TypeScript before closing that phase.
Extend proxy policy tests whenever an exact method/path/query is added. Backend changes
require corresponding permission/scoping/domain tests, OpenAPI and generated-client
checks. No broad proxy wildcard or direct browser credentials.

Most work uses existing APIs. Keep API gaps explicit: global recipient discovery,
full activation/delivery aggregates, arbitrary test sends, unsupported filters and
external attachments are not established capabilities. Do not present fake counts,
derive totals from partial pages or imply that message bytes/attachments were sent.
Inspect a gap at the start of its phase and implement only the scoped API support
needed for the agreed screen, following the repository's contract/migration rules.

## 6. Decision log and execution order

2026-10-22: prioritize the existing platform Notification card, retain both ownership
roots, reuse the current design system/CSS/layout, and deliver UI01 -> UI09 sequentially.
Shared area components serve both ownership roots while authority and state remain
separate. No application code or live provider configuration was changed for this plan.

Execution checklist: [notification-ui-todo.md](notification-ui-todo.md).

2026-10-23 implementation decisions: preserved the two owner roots and existing design
system; added no stylesheet or production dependency. API prerequisites resolved in
scope were masked endpoint detail, policy proxy paths, validated/idempotent policy
commands, complete route detail/edit/replay, request source/timing detail, delivery
endpoint/provider references and owner-correct credential discovery. These extend
existing models and require no new migration. OpenAPI/client contracts were regenerated.
See [operator usage](notification-ui-usage.md) and [both review passes](notification-ui-reviews.md).

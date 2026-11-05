# Platform administration pages verification

All three phases were agreed and implemented: protected platform metadata editing
and shared cards; dedicated tenant forms; directory navigation and final review.

The database model is unchanged. Platform details reuse the existing singleton
installation row; metadata writes lock it, refresh authorization and emit a
redacted change event through the same transaction. Setup replay/authority fields
are preserved. OpenAPI and the Identity TypeScript client were regenerated.
Shared UI is version 0.1.10 with its workspace lockfile checked.

Initial checks demonstrated the missing endpoint/component and, during browser
review, missing mobile top-bar chip reflow. Regression checks cover all three.
Tests cover platform/tenant editor routes and permission gates, validation,
pending/success/error states, missing/closed tenants, reference lookup failures,
unchanged retry keys, invitation failures, directory state return, and explicit
sign-in draft recovery. API checks cover unauthenticated and revoked access,
fresh-auth requirements, invalid origins/extra fields, setup proof preservation,
redacted audit records and rollback when audit emission fails.

Checks completed:

- Console: 97 affected tests plus 4 recovery/state tests passed.
- Shared UI: 85 initial affected tests passed; 67 card/shell/top-bar checks passed
  after the mobile correction (37 top-bar tests add coverage beyond the first set).
- Identity: 41 related checks passed; the final 16 metadata/validation/rollback
  checks passed after review corrections.
- Console and shared UI TypeScript checks, focused strict Python typing and Ruff
  passed. The final Next.js production build and OpenAPI/generated-client checks
  passed.
- Native local MySQL: migrations through 0073, downgrade to 0066 and re-upgrade,
  platform metadata reads/writes, tenant create/replay, lifecycle/search and
  self-service isolation passed in a disposable schema.
- Production Next.js plus that native API passed browser checks for platform cards,
  metadata validation/persistence, tenant create/edit, list-state return,
  suspension/restoration, materialized regional catalogues and invitation handoff.
  Desktop 1440px and mobile 390px reflow passed; light/dark/ledger reloads produced
  no hydration or page errors. Screenshots were manually inspected.

Final simplification/security review consolidated platform requests/errors and
tenant forms, removed obsolete drawer forms, added control-character validation,
preserved loaded details on invitation failure, corrected stale suggested-ID
errors and mobile top-bar overflow, and checked authorization, singleton scope,
bootstrap immutability, audit redaction/atomicity and creation retry semantics.
No remaining finding was identified in the changed paths. The slash-command
review tools are unavailable; equivalent manual reviews were performed.

Limits: browser authentication used an isolated signed session rather than a new
interactive Authentik login. SMTP remains unconfigured. The local Audit broker
source configuration is absent, so audit events are durably queued in Identity's
outbox; delivery to Audit was not claimed. When configuring the Identity source
credential, include `platform.details_updated` in its event allowlist. The existing
audit consumers use configured service-key operations; no event payload version
or consumer code changes are needed. Local MySQL evidence does not replace a
release check against the pinned production database version.

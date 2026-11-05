# Platform administration audit review

Date: 2026-10-22. All three phases authorized and completed locally. Running
services still need the rollout steps below before the new history is available there.

## Delivery phases

1. Inventory platform pages and their owning operations; distinguish durable audit,
   activity projections and operational diagnostics.
2. Repair transactional emission and authenticated, narrowly scoped Audit API history;
   connect platform pages without granting access to tenant business evidence.
3. Verify regressions, current permissions, tenant isolation, redaction, delivery
   contracts and UI behavior; record security and simplification findings.

## Coverage and applicability

| Page or operation | Audit/activity applicability | Review finding and fix |
|---|---|---|
| Platform landing | Navigation alone needs no evidence event | Added administrative history entry under existing platform authority. |
| Platform details | Configuration changes need durable audit | Retained existing update evidence and changed-field markers; connected on-demand history. |
| Tenant directory/detail | Cross-tenant reads need security evidence | Existing read events live in the operating tenant; connected administrative history. |
| Tenant creation | Provisioning and initial authority need evidence in the same transaction | Added atomic operating-tenant evidence alongside existing created-tenant evidence. |
| Tenant edit | Metadata changes need audit; contacts must be redacted | Preserved affected-tenant evidence and added an operating-tenant record with contact values withheld. |
| Tenant suspension/restoration | Access lifecycle changes need security evidence | Preserved tenant evidence and added operating-tenant history with before/after status. |
| Initial administrator invitation handoff | Sensitive access needs audit | Distinguished invitation access without recording its URL or credentials. |
| Account directory/detail | Applicant PII reads need access evidence | Classified new reads as access and retained safe counts; connected directory and subject history. |
| Account import/sync | Projection changes need audit | Recorded each imported/changed row without profile values; unchanged sync emits nothing. |
| Account approve/reject/reopen/reconcile | Decisions and provider results need security evidence | Preserved exact safe reference/state facts and withheld free-text reasons; connected Audit history alongside operational decisions. |
| Settings landing | Navigation alone needs no event | Added history entry for platform managers. Unimplemented payment/notification cards remain unavailable. |
| Country/state/language/currency directories, detail/edit/create/archive/restore | Public reference reads need no audit; mutations need admin evidence | Preserved safe code/version facts and connected catalog/subject history under configuration authority. |
| Password change | Native credential change needs provider evidence | Authentik owns password entry/completion. Navigation is not proof of a change; retain native audit and existing application sign-out events. |
| Setup | First administrator and installation completion need security audit | Admitted existing `platform.setup_completed` to the exact Identity publisher allowlist. |
| Provider/API/database failure | Operational diagnostics | Added sanitized JSON diagnostics and generic non-cached unexpected-error responses at platform HTTP/provider boundaries, without request bodies, profile values, secrets or exception text. |

Activity is a projection of stored audit events; it is not a second event emitted by
the browser. The implemented platform history includes administrative and security events
under the matching platform permission, without exposing ordinary tenant evidence.
The ordinary `/v1/activity` feed excludes security events and is therefore insufficient
for account approval and tenant access administration.

## Access contract

Platform admins keep their existing permissions. No general `audit.read`,
`audit.read_security`, tenant selection or cross-tenant audit grant is added.
Identity must verify configured operator identity and live grants before signing a
purpose-bound platform history context. Audit reads only the operating tenant and an
exact event/entity allowlist, restricted by `platform.account.read`,
`platform.tenant.read` or `platform.config.manage` as appropriate.
Stored tenant business history and existing tenant audit surfaces remain separate.
No browser POST creates audit evidence; the owning service emits through its outbox.

## Implemented behavior

Every correction in the matrix is implemented in source. History is available at
`/platform/history`, with directory links and collapsed subject panels on tenant,
account, details and reference pages. Tenant forms link to the saved subject's history.
Lists/details call `/api/audit/v1/platform-events` through the generated Audit client
and the existing same-origin Console proxy. Subject scope survives clearing filters;
safe primitive facts and before/after values display correctly. A refresh control
handles eventual delivery. No platform export control is offered.

Identity writes new `platform.tenant_provisioned`, `platform.tenant_updated`,
`platform.tenant_lifecycle_changed`, `platform.account_imported`,
`platform.account_drift_detected` and `platform.administrator_invitation_read` evidence.
The publisher now also admits existing `platform.setup_completed`. Tenant mutation
events are atomic with both the operator and affected-tenant records. Replayed
provisioning and unchanged import do not duplicate evidence.

Emission preserves only bounded status/action, boolean attestation/provider flags,
integer count/version, canonical command UUID, reference kind/code and fixed error
codes. Everything else becomes a changed-field marker. Platform free-text reasons
stay in the owning workflow; immutable platform evidence omits them. Historical
detail reads independently apply this policy to protect previously stored values.
Stored chain hashes are untouched; the projected response cannot recompute them alone.

Unexpected platform/setup failures now return a generic JSON error with `no-store`
and a generated request ID, after the owning transaction rolls back. Sanitized
diagnostics record only code-owned event/service names, exception type, timestamp
and validated trace reference. The setup/details rollback tests were updated to
assert this deliberate HTTP behavior change instead of expecting an escaped exception;
their database rollback/retry assertions remain intact.

## Verification

- Final combined Identity setup/platform/account/reference/audit regression suite:
  **70 passed**. Includes live grant removal, dual-tenant evidence, idempotency,
  lifecycle correlation and sanitized-error/rollback/retry assertions. A prior
  68-pass run exposed two tests expecting escaped exceptions; their assertions were
  updated for the deliberate generic 500 response and the final combined run passed.
- Full Audit suite: **183 passed, 8 skipped**, **93.02% coverage**; new platform
  endpoint coverage **95%**, new event-family domain module **100%**. Skips require
  unavailable native/container integration prerequisites.
- Full Console suite: **66 files, 708 tests passed**. Includes the new page,
  on-demand panel, generated client, proxy guards and fixed-filter/refresh coverage.
  Console `tsc --noEmit` passed. React test harness emits existing act warnings;
  these do not represent a completed real-browser verification.
- Strict mypy: Audit **30 files** and affected Identity **8 files** passed; Ruff
  passed for affected Python sources/tests. Regenerated Audit OpenAPI and TypeScript
  contract; exporter `--check` passed. Deferred integration-log routes are excluded
  from the published schema, matching `audit.md` rather than introducing unfinished
  integration-log clients.

Security review walked CLAUDE.md §§5-6: configured operator and live grants,
signature failure/unauthenticated denial, company-scoped grant rejection, exact
permission families, wrong tenant/detail rejection, Identity issuer provenance,
company/department exclusion, query/cursor validation, conservative legacy redaction,
idempotency and rollback, non-cached responses, and safe diagnostics. No unresolved
source-level security finding identified within this change. General money/domain
rules, shared permissions, migrations and datastores were not changed.

Simplification review reused the shared audit request/actor mechanism, outbox,
diagnostic helper, session isolation, cursor codec, existing Audit list/detail schemas,
generated client, and shared UI components. Identity emission policy and Audit
historical projection remain service-owned security policies, rather than a
cross-service import. No new dependency or shared-library version is needed.
`/simplify` and `/security-review` were unavailable in this session; these reviews
were performed manually and recorded here.

## Runtime rollout and remaining infrastructure gaps

Read-only checks found local Identity/Audit listeners on ports 8001/8002. The running
Audit OpenAPI **does not yet include `/v1/platform-events`**. Its existing private
`identity.current` source credential **lacks all seven new event names**. Those live
processes/configuration were not changed as part of source verification.

1. Deploy/restart matching Identity, Audit, publisher/consumer and Console code.
2. Extend the existing Identity issuer credential's exact event allowlist with the
   seven names above, preserving issuer, secret, broker user, other issuers and the
   historical publish cutoff. No wildcard route is needed. The local
   `start/win/registration/prepare-review-audit.ps1` already derives the current
   Identity allowlist, but is tied to its test broker/vhost; use it only for that
   configured local environment, not as a production configuration command.
3. Confirm signed delivery of exact new event IDs, clean queue/dead-letter behavior,
   and an authenticated history list/detail through the gateway. Exercise permission
   removal and a second tenant. These live browser/MySQL/RabbitMQ checks remain
   deployment verification; source tests do not prove them.

Previously missing operator-tenant records are not retroactively reconstructed.
Historical source-null events are excluded by the issuer gate. Publisher cutoffs
continue to hold historical events; no backfill or hash-chain rewrite is performed.

OpenTelemetry instrumentation, W3C `traceparent` propagation and Grafana exporters
remain architecture targets. Current evidence uses the custom signed outbox event
schema and bounded `X-Trace-Id`/request correlation. Failure diagnostics are sanitized
JSON via Python logging. The deferred integration-log surface is not used for these
diagnostics. Native password audit remains owned by Authentik.

Concurrent Identity session/company changes were preserved. No commit/publication
was requested or performed.

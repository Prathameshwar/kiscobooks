# Generated workspace IDs and simple location setup ? 2026-10-21

User-approved three-phase plan, extended by user to Country and State only for
regional creation controls. Registration credentials remain on the existing page.

Implementation: Identity derives immutable `workspace-<UUIDv7 hex>` identifiers
inside the existing atomic/idempotent provisioning service. No sequence or
browser ID generation. API request schemas reject slug inputs. Country/State
choices come from active database references, state resets on country change,
and creation validates country membership. Default currency comes from country;
English and Asia/Kolkata (India) or UTC defaults are resolved server-side and
copied into the initial administrator's locale/timezone. Optional regional API
overrides remain available. Both creation paths use the shared responsive
`janso-form-grid--pair`; tenant editing retains its existing default controls.

Database: reversible revisions 0074?0076 separately add a nullable state column,
supporting index and composite FK. Existing tenants retain NULL and all existing
IDs remain unchanged. The local Identity database was upgraded to 0076 using
migration credentials and installation reference seeds were refreshed; the
runtime database user's permissions were not expanded.

Validation:
- 54 API tests passed initially; the expanded generated-ID suite passed 6 tests.
- 625 migration-shape, target, tenant-model and self-service HTTP tests passed.
  The DDL counter now checks each direction independently and counts Alembic
  index helpers, fixing five false failures in existing 0067?0071 migrations.
- 49 Console editor/BFF checks passed; after directory and country-state updates,
  42 focused Console tests and 14 Auth onboarding tests passed.
- Both production Next builds and strict TypeScript checks passed; focused Ruff,
  strict mypy and generated Identity OpenAPI/client consistency checks passed.
- Native MySQL disposable schema upgraded to head, downgraded to 0066 and upgraded
  again; generated IDs, replay, distinct same-name tenants, stored state/defaults,
  lifecycle, search and self-service isolation passed. Tenant metadata matches head.
- Actual production Console with native MySQL passed tenant creation, invitation,
  edit/rename and state/default persistence. Browser checks verified hidden ID,
  desktop Country/State row, mobile stacking, state filtering, no horizontal
  overflow and no runtime/hydration errors. Auth layout checked in an isolated
  browser fixture with real components and shared styles.

Final manual simplification and security review: identifiers remain metadata,
not authorization. Existing fresh operator proof, live permission/object checks,
fixed bootstrap grants, transaction/audit boundaries and unique slug constraints
remain intact. No new event type or payload shape, no broker consumer change.
The final review also removed generated IDs from the organisation switcher,
using a Workspace label while retaining existing codes. The final session and
shell run passed 25 tests; strict TypeScript passed. No blocking findings. Slash review tools are unavailable in this session; the
CLAUDE sections 5/6 checklist was reviewed manually. SMTP remains deferred.
Native browser proof is disposable, loopback-only; no live administrator session
or production tenant was created for verification.

Local launchers confirmed Auth 4310, Console 4320, all seven APIs, MySQL,
Redis, RabbitMQ and nginx UP. Disposable database, proof file and isolated
browser/API servers were removed or stopped after verification.

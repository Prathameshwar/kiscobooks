# Reference catalog management verification

Completed 2026-10-21 under the user's agreed three-phase plan.

## Delivered behavior

Settings at http://localhost:4320/settings links Countries, States, Languages and
Currencies for platform configuration administrators. Every catalog has a signed,
bounded directory with search, status filter, name/code sorting, refresh, paging,
kebab actions and dedicated new/view/edit pages. Country actions open the States
directory filtered by that country. Back navigation, breadcrumbs, cards, table
cells, form grids, semantic review lists, notices and confirmation dialogs reuse
the central design system; no per-catalog stylesheet was added.

Delete archives with a reason and optimistic version. Restore is explicit. Codes,
ISO identifiers, state parent/tax mappings and currency financial metadata stay
fixed. Active tenant, company, address, currency allowance and parent-reference
dependencies prevent unsafe archival. Inactive historical references stay stored
and readable. Operator rows survive canonical seed reruns.

Identity owns the durable transactional change journal. Catalog and Accounting
workers verify signed requests/responses, apply bounded ordered changes to local
tables, commit versions/checkpoint together and acknowledge afterward. New custom
references wait for both consumers before becoming selectable. A crash after
commit retries its acknowledgement; consumers rebuild from canonical seeds and
the retained journal. No remote financial-transaction reads were introduced.

## Verification evidence

- Identity reference CRUD, permission, paging, replication and regional-selection
  suites: **29 passed**. Final fresh-auth/live-permission/verified-email change
  separately rechecked the CRUD suite: **9 passed**.
- Migration and reference regression batch: **641 passed**, three Docker-specific
  checks deselected. Native MySQL integration independently upgraded/downgraded/
  re-upgraded the new migrations in all three disposable databases.
- Shared canonical reference seed/data/language/composite-key checks: **64 passed**.
- Affected company currency/address/statutory/jurisdiction suites: **27 passed**.
- Console Settings, reference screens/routes, session proxy and duplicate-JSON
  checks: **33 passed**. Status-badge regression was observed failing and then fixed
  using the shared DataTable status type.
- Backend launcher and reference-worker checks: **24 passed**. Managed workers
  also stopped/restarted cleanly, and repeated starts did not duplicate processes.
- Ruff passed; strict mypy passed for nine affected API/service/replication files.
  Identity OpenAPI check passed; client types regenerated, API client version
  0.2.3 and shared Python version 0.35.0 recorded in consuming lockfiles.
- Console production build passed with all catalog routes and type checks.
- Edge/Playwright exercised actual shared screens through a native disposable API:
  four create-validation/create/view/edit/archive/restore/filtered-list flows and
  **12 viewport/theme combinations** (320, 390, 768, 1440; light, dark, ledger).
  Browser errors absent; document and main-region horizontal overflow checked.
- Actual production Console, authenticated fixture cookie and real session proxy:
  Settings cards, all eight catalog list/view routes, edit and persistent reload
  passed against the disposable native API. Fixtures replaced the external OIDC
  provider only; no new real Authentik account or email delivery was needed.

## Final review

Manual simplicity and security reviews performed against CLAUDE.md sections 5/6
(slash review commands are unavailable in this environment). Fixed findings:
MySQL reserved cursor quoting; nested duplicate JSON/body bounds; stale-edit
reload; creation synchronization preserving the saved record; failed-option-load
blocking forms; missing status cell type; address/currency dependency protection;
worker response streaming bounds; response signature validation; replica rollback;
monotonic committed journal order; protected-code checks; verified-email writes;
and live database grants for writes despite a cached session grant set.

No remaining blocking finding in the reviewed scope. Tenant information is never
exposed by global reference operations. Audit and journal commit with the mutation;
audit failure rolls everything back. Archive retains foreign keys/history;
DECIMAL storage and existing financial/tax execution remain unchanged. Added
languages do not supply translations and added countries do not enable tax profiles.

## Running local platform

Live migration heads: Identity **0079**, Catalog **0180**, Accounting **0154**.
Managed canonical seeds applied. Reference workers use separate scoped MySQL
accounts with SELECT/INSERT/UPDATE on only their six reference-management tables.
Secrets remain in ignored local environment files and are absent from runtime
process state. Both workers completed a signed live synchronization cycle with
their actual local credentials after the final restart.

All seven APIs, Auth 4310, Console 4320, nginx 8090, Redis, RabbitMQ and MySQL
reported UP. Standalone worker controls and normal backend start/stop integration
are documented in start/win/README.md. Disposable schemas, access token file and
browser/API processes were removed; normal databases and user accounts preserved.
No commit or publishing was requested or performed.

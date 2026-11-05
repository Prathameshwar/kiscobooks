# identity — build-to-done todo

Tracking completion of the `identity` service per `docs/identity-db-plan.md`.
Owner: uninterrupted build. Review pass (§5/§6 + /simplify + /security-review) after the last phase.

**2026-09-12 review follow-up:** [Findings](../../docs/identity-api-review-2026-09-12.md),
[separate bug-fix plan](../../docs/identity-bug-fix-plan.md), and
[separate gap-completion plan](../../docs/identity-gap-completion-plan.md).
The bug-fix plan is completed and reviewed: 1,081 Identity/MySQL tests passed with
93.97% coverage. Final evidence is recorded in
[the corrective review](../../docs/identity-bug-fix-results-2026-09-12.md). The gap plan
remains separate. Historical counts below are snapshots of earlier phases.

**Datastore: MySQL 9.6** (tech-stack.md decision log, 2026-09-11 — reversed from MariaDB 11.4). No Docker on this workstation.
- SQLite suite (`uv run pytest`) — authoritative for logic, isolation, domain, routes.
- MySQL migration smoke (`IDENTITY_SMOKE_SERVER_URL=... uv run python tools/mysql_smoke.py`) — proves DDL applies/reverses on the real engine.
- Containerised `@mysql` drift + dialect tests — **CI-pending** (need Docker).
- Every phase must end: SQLite green · MySQL smoke pass · ruff clean · mypy strict clean.

## Baseline (done)
- [x] Toolchain verified: 488 passed / 2 skipped, ruff clean, mypy clean, MySQL smoke pass.
- [x] `tools/mysql_smoke.py` migration smoke runner.
- [x] Design decisions: department nesting cap = 6 (`/`-delimited uuid-hex path); `field_config` tenant-only at launch.

## Track A — HTTP/API layer (deferred across P2–P5; no blockers)
- [x] **A0 foundation:** deps added · `config.py` · `api/auth.py` (scope-aware Actor + `require`/`require_scope`, signed-context decode, 401) · `api/dependencies.py` · `api/listing.py` (keyset helper) · `schemas/base.py` · `main.py` (app factory, PlatformError handler, field-registry boot check, health) · conftest app+client fixtures + `api_support` signer. Added `AuthenticationRequiredError` (401) to libs/platform (v0.2.0); libs suite still green (476).
- [x] **A1 company:** `field_registry` (identity.company, 45 fields) · schemas · CRUD + `field-set` + `display-config` + feature enable/disable (409) + visibility (security audit) + object-scope on every handler + list scope-narrowing + outbox audit. 22 API tests: 401/403-wrong-company/404-cross-tenant/422/immutability(422)/feature-ratchet/field-set/isolation. **510 passed / 2 skipped, ruff+mypy clean, MySQL smoke pass.**
- [x] **A2 statutory & licences:** tax_registration create/list/amend (posting-date resolution deps, overlap→409, tax_system immutable, jurisdiction-code check) + statutory_id (AADHAAR/SSN **discarded before store**, absent from response/row/audit; PAN in full) + licence (expiry gate) + address (composite-FK check) + object-scope everywhere + outbox audit. 11 tests incl. the redaction invariant asserted across the whole row. Green.
- [x] **A5 tenant:** `GET/PATCH /v1/tenant` self-service (tenant-scope object check, slug/status/plan not editable) + isolation + audit. 6 tests. Platform provisioning still deferred (documented).
- [x] **A3 user:** invite + read + update + deactivate(anonymize, tombstone in domain) + user_identity link/list + tenant-scope object checks + outbox audit. 10 API tests: 401/403/409-dup/422/404-cross-tenant/company-scope-403/anonymize-keeps-row/no-self-deactivate/isolation. Green.
- [x] **A4 roles/permissions/assignments:** role compose (guard 1 + SoD warnings) + edit (system 422) + clone + list + `GET /permissions` catalogue + assignment grant/revoke wiring all 3 escalation guards + object-scope via guards + security audit. 15 API tests incl. all three guards, system-role-immutable, company-scope. Green. (Boot check on seeded permission keys already enforced at import in system_roles/permissions.)
- [ ] **Platform tenant provisioning:** tenant self read/update is implemented. platform tenant provisioning (create/list/suspend across tenants) needs an unfiltered platform-session pattern — deferred as platform-ops, documented.

## Track B — remaining migrations + models + domain + schemas + routes + tests
- [x] **P6 structure & groups:** 0019 department · 0020 ALTER user FK (single ALTER: index+FK) · 0021 user_group · 0022 user_group_member · 0023 membership. Models+factories+migrations in sync (211 migration tests green). `department_tree` domain (path, ancestor-or-self, cap 6, reparent rewrite, cycle guard) + 6 domain tests. Two-tenant isolation for all 4 tables. Org API: department create/nest/reparent + group create/add-member + membership + **department-scope assignment now enabled** in roles. 7 API tests. Updated the Phase-5 FK-absence test (behaviour changed). 26 tables → wait, 23. Green + smoke.
- [x] **P7 remaining children (schema):** 0024 company_contact · 0025 company_bank_account · 0026 company_document · 0027 user_notification_preference · 0028 user_api_token. Models+migrations in sync (256 migration tests), factories, two-tenant isolation for all 5, structural checks (api_token has no raw-token column; bank redaction columns present). 28 tables, smoke pass. **Routes deferred** (schema-complete per DB plan; CRUD is API-phase follow-up).
- [x] **P8 impersonation (schema+domain):** 0029 impersonation_session + `domain/impersonation` (expired-refused-even-if-not-ended) + 3 domain tests + isolation. **Start/end HTTP endpoints deferred** (API-phase).
- [x] **P9 field policy (schema+domain):** 0030 field_policy (SCOPE_ALL scope_id) + `domain/field_policy.assert_fields_writable` (default-allow, deny-wins, specificity-override, diff-based) + 7 domain tests + isolation. Company route enforcement now implemented and covered by the corrective review; policy administration remains a gap.
- [x] **P10 extensibility (schema):** 0031 custom_field_definition · 0032 field_config (SCOPE_ALL, tenant-only) · 0033 custom_field_value_index (natural-key PK; value_date exemption documented) · 0034 custom_field_sequence + factories + isolation (incl. SCOPE_ALL sentinel) + models sync. **CRUD/machinery routes deferred** (API-phase; invariant 14 — no domain reads a custom field — holds structurally).

## Cross-cutting / close-out
- [x] `tests/test_role_seed.py` written (idempotency, no-op reseed, grants, name-drift correction). 4 tests.
- [x] §2 sync honored per change (model↔migration↔schema↔factory). **TS client regen is out-of-repo — pending** (no `clients/api-client` in this repo; OpenAPI is generatable from the app).
- [x] Plan §8 open questions resolved in the doc + decision log (department.path cap 6, field_config tenant-only). `plan`/`language` kept deferred.
- [x] Final review: §5 security + §6 invariants walked. `/simplify` (manual, no git): consolidated `looks_like_email` and `load_company` into shared helpers. `/security-review` (manual, no git): **found + fixed** a hardcoded DB password default in `tools/mysql_smoke.py` (§5.9). Remaining findings reported to user.
- [x] Plan status header updated to "Executed".

## Known gaps (reported honestly, not silently closed)
- MySQL 9.6 is the current datastore. Local migration/constraint/concurrency evidence is recorded in the corrective review.
- P7 (contact/bank/document/notif-pref/api-token), P8 (impersonation start/end), P10 (custom-field CRUD/machinery) are **schema+domain complete with tests, but lack HTTP routes** — API-phase follow-up.
- Package-wide coverage ~76% (domain/ ≥90% met; route branches lower). `fail_under=90` gate will flag until more route tests or a domain-scoped gate.
- Platform tenant provisioning (cross-tenant create/list/suspend) deferred — needs an unfiltered platform-session pattern.
- No logging-redaction middleware yet for bank/statutory values (values are not currently logged; middleware is API-phase).

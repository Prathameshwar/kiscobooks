# Platform administration implementation tracker

Approved by the user on 2026-10-21: implement all six phases of
[the plan](platform-admin-first-three-plan.md), in order, with phase reviews/fixes.
No commit or publication is included in this implementation request.

- [x] Phase 1 — Verify provider capabilities and finalize contracts
- [x] Phase 2 — Full View tenant page
- [x] Phase 3 — Change password with Authentik
- [x] Phase 4 — Account-review API, database and provider coordination
- [x] Phase 5 — Account-review Console pages
- [x] Phase 6 — End-to-end verification and final review

## Evidence and findings

The existing tenant detail API and registration path are reused. Authentik owns
passwords; no privileged password-reset API is planned. Existing company setup
and Notification work is concurrent and must be preserved.

Phase 1: disposable Authentik object-permission proof passed: list/read/update only
the assigned applicant, unrelated-user read/update denied, password reset denied.
Contract saved in `platform-account-review-contract.md`. Provider has no CAS API;
external concurrent edits are explicit drift, not silently successful approval.

Phase 2: full tenant view and directory navigation delivered; 20 component/directory
checks passed. Review corrected date display to use shared installation formatting.
Optional reference label outages preserve stored codes; invitation drawer stays separate.

Phase 3: protected Auth page/API/layout and shared menu checks passed. Native
Authentik proved wrong-current-password, mismatch, unchanged, 5/129 rejection,
6/128/Unicode acceptance, configured TOTP and anonymous/passwordless denial.
The live account menu opens the current-password challenge without exposing credentials.

Phase 4: review API approval/replay/outage/drift/revocation/rollback checks (7),
domain checks (12), native MySQL schema/model and migration round trips passed.
Native MySQL competition accepts one decision and rejects the competing version;
intent and audit roll back together. Restricted service preparation and native
registration permission handoff applied. The final security review corrected
cached grant reuse: all account operations and queued delivery check live grants.

Phase 5: account list/detail checks passed (15), including reconciliation and
per-reviewer draft recovery without storing account profiles or attestation.
Review corrected the shared checkbox contract and accessible action-card naming.

Phase 6 complete: public signup → platform UI approval → normal OIDC login →
workspace creation passed with a disposable account. Native Identity checks verified
India/Maharashtra defaults, a generated workspace identifier and exactly one
tenant-admin grant. Tenant full View/Back and password-menu navigation passed.
Live Identity-to-Audit delivery was verified in the actual Audit database, including
hash-chain entries and absence of applicant profile fields. Password cancellation
preserved the original password; inactive/rejected users were denied by the native
authentication backend. Native password bounds and configured MFA passed again.

Verification: Auth 136 client and 74 server checks passed; one optional real-Redis
refresh fixture was skipped. Console affected pages/proxy/menu: 76 passed. Shared
checkbox/menu: 51 passed. Identity review/provider/worker: final 25 passed;
domain/migration checks and native MySQL concurrency/schema round trips passed.
Invitation, onboarding, revocation and company-reference regressions: 58 passed.
Audit configuration/worker checks: 4 passed; explicitly configured real RabbitMQ
transport checks: 6 passed. Windows launcher/registration checks: 27 passed.
Strict Identity typing (173 files), Audit configuration typing, affected Ruff,
Auth/Console/shared UI TypeScript, both production builds and generated-contract
checks passed. Shared-library version 0.37.0 is consistent in all 11 consumer locks.

Final review fixes: bounded streamed provider responses, numeric native pagination,
live grant checks on reads/write/retry, default chronological query index (0083),
safe process timestamp handling, graceful review-worker stop, scoped draft recovery,
and anchored shared checkbox positioning. Equivalent manual simplification/security
review covered CLAUDE.md §§5–6; the named slash commands are unavailable in this
environment. No blocking application finding remains.

Desktop Light/Dark/Ledger and 390px mobile account views were inspected. The last
browser repeat was interrupted by laptop sleep/resume while navigating Tenant Edit;
the server returned 200, and dedicated edit/navigation tests passed. Earlier live
signup/approval/onboarding, tenant View/Back and native password navigation passed.
After resume, the trusted provider tunnel/clock and empty bounded provider listing
were verified again. This limitation is recorded rather than treating that repeat
as a fully successful browser run.

Cleanup: disposable provider accounts were removed. Disposable Identity users were
deactivated/anonymized, assignments withdrawn, and the test workspace closed;
audit/history remain. Original operator mapping restored. Normal development UI,
seven APIs, MySQL, Redis, RabbitMQ, nginx, review worker and audit delivery restored.
The new worker's start/stop/start cycle passed cleanly. SMTP remains deferred.

# Identity gap implementation todo

User authorized GP0-GP8 and final review on 2026-09-12. Azure Blob is the selected
private document provider. RabbitMQ was checked, installed locally and verified.
Scope: [approved plan](identity-gap-completion-plan.md). A checked item means tested
completion. Live integration gates below remain open; no production deployment occurred.

## GP0 - Contracts and environment

- [x] Read architecture, approved plan and corrective baseline.
- [x] Record routes, permissions, scope and deployment contracts.
- [x] Inventory dependencies and provide isolated MySQL, RabbitMQ and Azurite commands.
- [x] Document missing external configuration and affected release gates.

## GP1 - Durable audit (G07)

- [x] Authenticated publisher/consumer, explicit allowlist and tenant/company scoping.
- [x] Confirms, bounded retries, quarantine, diagnostics and explicit recovery.
- [x] Commit/rollback, duplicate inbox and invalid-signature verification.
- [x] Real RabbitMQ outage/restart/redelivery test with Audit persistence on SQLite.

## GP2 - Authentication and invitations (G01)

- [x] OIDC/JWKS validation, live identity/grants, session and browser integration.
- [x] Invitations, Notification commands/templates, verified acceptance and identity linking.
- [x] Activation/revocation, platform authority and tenant bootstrap.
- [ ] Real Authentik + TLS gateway + invitation email + browser acceptance/sign-out flow.

## GP3 - Organization lifecycle (G02)

- [x] Group assignments, update/deactivation and member removal.
- [x] Membership end and atomic primary switch.
- [x] Company/department/custom-role lifecycle, historical reads and live grant resolution.
- [x] Authorization, replay and disposable MySQL concurrency checks.

## GP4 - Child resources (G03)

- [x] Contacts/preferences and Notification consent/suppression precedence.
- [x] AES-GCM bank encryption, masked reads, audited reveal and key rotation.
- [x] Azure document upload/finalize/snapshot download and bounded reconciliation.
- [x] Hash-only tokens, one-time issue, bounded live authority and revocation.
- [x] Actual encryption/token consumption and local Azurite HTTP protocol verification.
- [ ] Azure account managed identity/user-delegation RBAC, CORS and cloud recovery check.

## GP5 - Customization (G04)

- [x] Company definitions, tenant layout and merged field metadata.
- [x] Validated policy subjects/scopes/conditions and self-escalation protection.
- [x] Typed values/indexes/sequences and bounded rebuild/backfill recovery.
- [x] Catalog source contracts, replay and enforced query/read/write permissions.

## GP6 - Step-up and support access (G05)

- [x] Fresh company challenge/proof and path/query/body/reference enforcement.
- [x] Audited support start/end/expiry, read-only authority and real/effective attribution.
- [x] Auth/Console flows and signed downstream consumer verification.
- [ ] Real Authentik + Redis + gateway/browser proof flow and Redis outage/recovery.

## GP7 - First-use locks (G06)

- [x] Durable reservation/confirm/abort contract outside money transactions.
- [x] Identity freeze/irreversibility enforcement and source propagation.
- [x] Signed Billing client, terminal publisher, replay/unknown-outcome and MySQL race tests.
- [ ] Actual Billing ledger/outbox/inbox integration; the Billing service is absent.

## GP8 - Verification and review (G08)

- [x] Final Identity: 1,224 passed, 1 opt-in skip; 93.97% coverage. Shared: 771 passed, 98.56%.
- [x] Every Identity domain clears 90%; overall matches the 93.97% baseline.
- [x] 483 MySQL migration/constraint/race checks through revision 0057.
- [x] Identity OpenAPI, generated TypeScript client and affected consumers synchronized.
- [x] Ruff and strict typing clean, including the Billing client and browser consumers.
- [x] Manual correctness/security/simplification review and reproduced fixes.
- [x] Final results ledger completed with explicit remaining release gates.
- [ ] Full live deployment/performance/recovery evidence on the configured release target.

## Final review fixes

- Protected company selection in session bootstrap now enforces step-up.
- Field metadata reflects actual write permissions and inactive/posted restrictions.
- Shared AES-GCM accepts a valid empty plaintext without weakening AAD/tamper checks.
- Invalid timezone paths and malformed gateway company UUIDs return validation errors.
- Audit retry diagnostics flush the reset before reporting current delivery status.
- Regression tests failed before each code correction and passed afterward.

## Evidence and limitations

Reproduction/configuration: [operations](identity-gap-operations.md) and
[local RabbitMQ](local-rabbitmq.md). Detailed final evidence belongs in
[results](identity-gap-results-2026-09-12.md).

The historical corrective baseline was 93.97% Identity coverage. Initial gap runs
failed that gate despite passing functional tests. Further tests cover session,
credential, posting and recovery boundaries. The final stable-source run passed at
93.97%, matching that baseline. No threshold or exclusion was relaxed.

Actual local verification includes RabbitMQ restart/inbox/DLQ behavior, MySQL 9.6 and
Azurite. Azurite does not prove Azure managed identity. RSA-signed provider fixtures do
not prove an Authentik deployment. Captured email delivery does not prove an external
provider. Adapter tests do not prove a Billing money transaction. These remain explicit
release gates rather than being marked complete from mocks.

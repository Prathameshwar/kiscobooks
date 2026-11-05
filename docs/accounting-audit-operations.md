# Accounting audit operation and recovery

Run the HTTP services independently from the workers. Use
`start/win/audit-workers.ps1 -Action start|status|stop` with an explicit private env directory.
The default env directory is `start/win/env`; use a different private directory explicitly
when separating worker grants from HTTP grants. `-RuntimeDirectory` optionally isolates
process records inside the workspace for a test run. Workers have tracked process identities,
hidden windows and private logs under ignored
`.tools/audit-workers/`. A running process is not evidence that messages were ingested.

## Configuration

Accounting publisher uses the existing `ACCOUNTING_DATABASE_URL`,
`ACCOUNTING_AUDIT_BROKER_URL`, `ACCOUNTING_AUDIT_BROKER_USER`,
`ACCOUNTING_AUDIT_EVENT_SECRET` and optional key ID/exchange settings.
Its database credential accesses only Accounting outbox infrastructure.

Audit consumer uses `AUDIT_DATABASE_URL`, `AUDIT_BROKER_URL`,
`AUDIT_ACTOR_SIGNING_SECRET`, `AUDIT_CURSOR_SIGNING_SECRET` and
`AUDIT_SOURCE_CREDENTIALS`. Sources are exact issuer/broker-user/key/event allowlists.
Install new consumer routes before enabling new producer events. No wildcard subscriptions.
Use durable topology, publisher confirms, validated RabbitMQ user IDs and least-privilege ACLs.

Audit's own publisher uses `AUDIT_PUBLISHER_DATABASE_URL`,
`AUDIT_PUBLISHER_BROKER_URL`, `AUDIT_PUBLISHER_BROKER_USER`,
`AUDIT_PUBLISHER_EVENT_SECRET`; default key ID is `audit.current`.
Its sole route is `audit.exported`. Include that source in the consumer credentials.
Accounting delivery uses `accounting.env`, `audit.env`, `audit-publisher.env`.
The launcher now also manages Catalog: `-Worker all` requires `catalog.env` too.
Use an explicit `-Worker` to operate one configured worker independently.

Audit table grants permit INSERT/SELECT only; outbox and inbox infrastructure need their own
appropriate grants. Partition maintenance uses a separate privileged credential.
Run the existing partition scheduler and chain verifier under the deployment scheduler.

## Health and recovery

From `apis/accounting`, run `python -m accounting.tasks.audit_publisher --env-file PATH --status`.
It reports pending/exhausted counts, oldest age and at most 100 IDs without event payloads.
Alert on exhausted attempts, increasing oldest age, dead-letter count and ingestion lag.
Compare a canary's message ID with Audit persistence; broker confirmation alone is insufficient.

Run `--retry UUID [UUID ...]` for a dry run, then the same explicit IDs with `--apply`.
Only pending rows belonging to that publisher are eligible. At most 100 distinct IDs can be selected.
Recovery resets retry scheduling only; event body, original timestamp and message ID survive.
Published outbox rows are deliberately refused.

For broker-confirmed events rejected by Audit, use
`--dead-letters audit.events.authenticated.v1.dead` to inspect a bounded queue window.
Add explicit `--retry UUID ...` and then `--apply` to republish selected authenticated originals.
Nonselected messages are requeued; replay ACK occurs only after positive broker confirmation.
Provide the original signing key ID/secret and original broker identity when recovering events
signed before rotation. A 100-message window can prevent selection of deeper entries; repeat
inspection during a controlled drain and resolve earlier entries instead of bypassing the bound.
Inventory reports invalid originals as `verified: false` and continues inspecting the window.
Explicitly selected invalid messages block recovery before any publish. Messages for another
publisher are left alone. Unknown/forged messages require investigation, not a verification bypass.
Never delete a queue, reset all published rows or generate new message IDs for retries.

A valid signature does not guarantee a valid payload. Oversized fields and non-finite JSON
are permanent payload defects and are dead-lettered before database access. Replaying the
unchanged invalid original will be rejected again; investigate the producer/contract defect
and retain the original evidence. Genuine database failures remain unacknowledged for retry.

Key rotation: deploy both verification keys first, switch producers, drain old pending and
dead-lettered events, then retire the old verification key. Durable signatures do not expire
merely because a broker delivery was delayed. Do not remove a key with unresolved old messages.

## Rollout

Deploy legacy-compatible consumption and field-policy enforcement before richer producers.
Configure bindings, verify worker startup, then enable authenticated UI reads. Run a canary
Accounting mutation, verify its persisted Audit row and scoped API result, and check the chain.
Review a concrete backlog inventory before applying recovery to existing deployment data.
Rollback stops new producer workers if needed and preserves queues, committed business data,
outboxes and immutable Audit rows. It never rewrites history.

## Audit export publisher and maintenance

The Audit publisher offers the same operations from `apis/audit`:

```powershell
uv run --frozen python -m audit.tasks.publish --env-file PATH --status
uv run --frozen python -m audit.tasks.publish --env-file PATH --retry MESSAGE_UUID
# After reviewing the selected IDs:
uv run --frozen python -m audit.tasks.publish --env-file PATH --retry MESSAGE_UUID --apply
```

Run chain verification from the deployment scheduler using
`audit.tasks.verify.verify_tenant_chain(session, tenant_id)` or `verify_all_chains(session)`.
Use a read-only Audit connection and alert on any returned break. Tenant discovery uses pages
of 100 IDs; each chain uses pages of at most 1000 rows and caps diagnostics at 1000 per tenant.
Rows are ordered by `(sequence, occurred_at, id)` so duplicate sequence values cannot escape
verification at a page boundary.
Verification runs against original stored evidence, independently of an API reader's field
projection. A restricted API response cannot be used as the complete hash input.

Schedule `audit.tasks.partitions.provision_ahead(connection, today=UTC_DATE, ahead=3)` with
an Audit maintenance connection, separate from runtime credentials. It is repeatable and
splits one missing month per DDL statement. Keep the existing retention/archive job separate;
`drop_expired` drops only whole partitions past the longest configured category floor. This
integration does not register a machine-wide scheduled task or change deployment retention.

For delivery monitoring, combine publisher inventory with RabbitMQ queue consumer/ready/unacked
and dead-letter counts. Alert on any exhausted event, no active consumer, a growing backlog,
or a missed canary. Ingestion lag for a canary is `ingested_at - occurred_at`; retain the source
message ID so a broker-confirmed delivery can be reconciled to persistence. Do not infer loss
from an empty console list; delivery is asynchronous and reads may have narrower authority.

## Reproducible isolated verification

The probes create and drop their own Accounting/Audit schemas and queues. Point them only at
the dedicated loopback test MySQL server and test RabbitMQ vhost; HTTP production databases
and queues are never selected. See `docs/local-rabbitmq.md` for local broker provisioning.

```powershell
# Repository root: prepare the existing disposable infrastructure.
.\start\win\identity-test-mysql.ps1 -Action start
.\start\win\rabbitmq-local.ps1 -Action start
. .\start\win\rabbitmq-local.ps1 -Action environment

# apis/identity: native command -> gateway -> encrypted session -> real Chrome.
$env:PYTHONPATH = '../accounting/src;../audit/src;.'
$env:AUDIT_TEST_MYSQL_SERVER_URL = 'mysql+asyncmy://root@127.0.0.1:13396'
$env:AUDIT_TEST_NGINX_BINARY = 'C:/path/to/nginx.exe'
$env:AUDIT_TEST_BROWSER_PYTHON = 'C:/path/to/python-with-playwright.exe'
.venv\Scripts\python.exe -u tools/verify_accounting_audit.py

# apis/accounting: native financial command-to-Audit checks.
$env:PYTHONPATH = '.'
$env:ACCOUNTING_TEST_MYSQL_SERVER_URL = 'mysql+asyncmy://root@127.0.0.1:13396'
.venv\Scripts\python.exe tools/verify_mysql.py --tests tests/test_audit_native_financial.py
# Full service suite and migration round trip (longer):
.venv\Scripts\python.exe tools/verify_mysql.py --full-suite
```

The browser probe uses real Identity JWT verification with generated disposable JWKS and an
isolated Identity SQLite fixture. Accounting and Audit use native MySQL. This exercises the
application auth boundary without claiming contact with an external Authentik deployment.
JSON results, query plans and browser screenshots are written below ignored `.test_artifacts`.
Worker env files are removed by the probe; access credentials are never printed or committed.

## Release gate and rollback

1. Validate private producer identities, exact route bindings, database grants and both
   verification keys during rotation. Deploy the compatible consumer first.
2. Deploy Identity policy/step-up context and gateway authorization, then Audit response
   projection before enabling safe before/after values in Accounting producers.
3. Start the three workers, check process identity/status and publisher inventory, then serve
   the generated client and console. Production scheduling and alert destinations are supplied
   by the deployment, not inferred from an HTTP health response.
4. Send one authorized canary and reconcile its message ID, immutable row, scoped detail,
   current field policy, browser export and the export's own access event.
5. Inventory the actual historical backlog and recover explicit reviewed IDs. Never mark
   broker-confirmed rows pending globally or rewrite existing evidence.

Rollback can stop the new console/producer deployment and its workers. Keep the compatible
consumer, field-policy projection, pending outboxes, queues and existing chain intact. There
is no schema migration in this change and no reverse migration that erases audit history.

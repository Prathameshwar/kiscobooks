# Catalog audit operations

Catalog HTTP and audit delivery are independently supervised. Broker confirmation means
accepted by RabbitMQ; only a scoped Audit row for the message ID proves ingestion.

## Workers and credentials

The shared launcher now supports four workers: catalog-publisher, accounting-publisher,
audit-consumer and audit-publisher. `-Worker all` requires all four private env files:
`catalog.env`, `accounting.env`, `audit.env`, `audit-publisher.env`. Use an explicit
`-Worker catalog-publisher` to operate only Catalog. Supply private configuration under
`-EnvDirectory`; tracked process records/logs stay under the workspace. No secrets belong in
command arguments or repository files. HTTP startup does not launch workers.

```powershell
.\start\win\audit-workers.ps1 -Worker catalog-publisher -Action start -EnvDirectory PRIVATE_PATH
.\start\win\audit-workers.ps1 -Worker catalog-publisher -Action status -EnvDirectory PRIVATE_PATH
.\start\win\audit-workers.ps1 -Worker catalog-publisher -Action stop -EnvDirectory PRIVATE_PATH
```

Catalog uses `CATALOG_DATABASE_URL`, `CATALOG_AUDIT_BROKER_URL`,
`CATALOG_AUDIT_BROKER_USER`, `CATALOG_AUDIT_EVENT_SECRET`, optional
`CATALOG_AUDIT_EVENT_KEY_ID` (existing default `current`) and `CATALOG_AUDIT_EXCHANGE`.
`CATALOG_AUDIT_MAXIMUM_ATTEMPTS` defaults to 12; batch and timeout remain bounded.
Consumer source entries must identify Catalog's issuer, original broker user, key ID/secret
and exact routes from `apis/catalog/contracts/audit-events.json`. No wildcard authority.
For a new deployment, use an explicit service-qualified key ID such as `catalog.current`
and the identical consumer entry. Preserve an existing `current` key ID while its original
backlog drains. Use independent producer credentials/keys and append-only runtime grants
for Audit evidence.
Partition maintenance retains its separate privileged credential.

## Inventory and recovery

From `apis/catalog`:

```powershell
uv run --frozen python -m catalog.tasks.audit_publisher --env-file PRIVATE_PATH --status
uv run --frozen python -m catalog.tasks.audit_publisher --env-file PRIVATE_PATH --retry MESSAGE_UUID
uv run --frozen python -m catalog.tasks.audit_publisher --env-file PRIVATE_PATH --retry MESSAGE_UUID --apply
uv run --frozen python -m catalog.tasks.audit_publisher --env-file PRIVATE_PATH --dead-letters QUEUE_NAME
```

Status reports bounded IDs/counts/age without event bodies. Retry selects at most 100 explicit
eligible unpublished IDs. Published and unrelated events remain unchanged. Dead-letter replay
adds the same exact retry IDs and then `--apply`; original signatures, bodies, timestamps and
message IDs survive. Original deliveries are ACKed only after positive broker confirmation.
Inventory marks invalid originals unverified; selecting one prevents replay before publication.
Malformed payloads need producer/contract investigation, not blind retry or evidence rewriting.
Keep both verification keys through rotation until old pending and dead-lettered events drain.
The recovery CLI verifies against the key in its private env file: use the matching historical
key ID/secret for old dead letters. Recovery forwards the original signed body; it does not
replace its signature with the new producer key.

Alert on pending age, exhausted attempts, dead letters and absent ingestion canaries. HTTP
health and a running worker are insufficient delivery evidence. Use the existing bounded
chain verifier against stored rows and alert on returned breaks.

## Native verification

Use only dedicated loopback test MySQL and the isolated `bill_identity_test` RabbitMQ vhost.
The probes create and drop their own schemas, queues and users. Existing schemas are never
selected for reset. Bootstrap the repository's existing test infrastructure first.

```powershell
# Repository root
.\start\win\identity-test-mysql.ps1 -Action start
.\start\win\rabbitmq-local.ps1 -Action start
. .\start\win\rabbitmq-local.ps1 -Action environment

# apis/catalog: products, pricing, tax, bulk CSV/XLSX -> RabbitMQ -> Audit; migrate to head
$env:PYTHONPATH = '.'
$env:CATALOG_TEST_MYSQL_SERVER_URL = 'mysql+asyncmy://root@127.0.0.1:13396'
.venv\Scripts\python.exe -u tools/verify_audit_workflows.py

# apis/identity: Catalog HTTP -> actual gateway -> Audit -> encrypted session/Chrome
$env:PYTHONPATH = '../accounting/src;../catalog/src;../audit/src;.'
$env:AUDIT_TEST_MYSQL_SERVER_URL = 'mysql+asyncmy://root@127.0.0.1:13396'
$env:AUDIT_TEST_NGINX_BINARY = 'C:/path/to/nginx.exe'
$env:AUDIT_TEST_BROWSER_PYTHON = 'C:/path/to/python-with-playwright.exe'
.venv\Scripts\python.exe -u tools/verify_catalog_audit.py
```

The workflow proof upgrades fresh schemas to head. It does not downgrade: existing revision
0131 deliberately requires explicit data migration before downgrade. This integration adds no
application schema migration. Individual workflow tests use their existing fixed authorization
clock; the gateway proof retains real clocks. Both probes remove only their owned disposable schemas.

The gateway proof runs Catalog in its own interpreter to preserve service-owned ORM mappings.
Catalog/Audit databases and RabbitMQ are native. Identity is an isolated SQLite fixture with
real JWT/JWKS validation; Catalog source facts are explicit test snapshots. This is not a
certification of an external Authentik deployment. Browser credentials are process-private;
worker env files are removed during cleanup. Artifacts go under ignored `.test_artifacts`.

## Rollout and rollback

1. Configure compatible consumer routes/keys, then Identity/Catalog historical field policies
   and Audit projection before enabling richer Catalog producer evidence.
2. Deploy the Catalog gateway authorization subrequest. Client actor headers are overwritten;
   company access and step-up are checked at Identity, with resource authority still in Catalog.
3. Start workers with the reviewed private configuration. Verify a Catalog mutation's message
   ID, scope, stored evidence and chain; verify download access and Audit-export self-events.
4. Enable the existing console's Catalog filters/details/export and verify live policy changes.
5. Inventory the actual backlog; apply only explicitly reviewed recovery selections.

Rollback may stop a new producer/console deployment, but preserves queues, outboxes, immutable
rows and read-policy protection. Production scheduler registration, alert destinations and
backlog replay remain deployment actions, not consequences of local tests.

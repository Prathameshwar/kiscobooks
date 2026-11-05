# Catalog audit delivery increment

This C2.04 increment follows the reviewed index rebuild workflow. It does not add
Billing workflows, change the Audit hash chain, or complete the whole Catalog release.

1. Add optional company identity to the shared audit payload, preserving the legacy
   payload when no company is supplied. Pass the authoritative company from every
   Catalog command, including hierarchy edges and index jobs. Verify regression,
   rollback and replay behavior; never put custom values in audit change markers.
2. Extract the existing Identity publisher supervision into a shared bounded outbox
   runner. Services own the exact event allowlist, issuer, audience and exchange.
   Preserve mandatory routing, durable messages, positive confirms, stable message
   IDs, backoff and cancellation cleanup. Do not acknowledge unrelated outbox routes.
3. Add Catalog's independently supervised audit publisher with environment-only
   broker credentials and an explicit allowlist covering implemented commands only.
   Review runtime settings and provide the Audit consumer binding contract. An
   unroutable event stays pending; publication is not proof of Audit persistence.
4. Finish API failure logging with bounded structured diagnostics: only service,
   event, error class, timestamp and validated trace ID. Handle unexpected failures
   before response start without passing private exception text to the ASGI server;
   a failed stream aborts with a sanitized error because its status is already sent.
5. Run shared, Catalog and affected Identity/Audit regressions, strict typing/lint,
   generated contract checks and milestone review. Update all shared lockfiles.

The deployment must bind Audit's durable queue to the configured audit exchange for
the exact Catalog event routes and enforce publisher/consumer broker ACLs. HMAC
signatures are emitted by the shared transport and verified by the current authenticated
Audit consumer. Exact issuer/user/key/routes must be configured before producer rollout.
Real command-to-MySQL/RabbitMQ verification remains a release gate; fake transport tests
are not its substitute. The older dated checkpoints below are historical.

Decision 2026-09-12: reuse the confirmed publisher mechanism, retaining event names
and schema version 1. Adding optional company_id uses Audit's existing nullable
column and validated payload contract; no Audit schema migration is required.

## Running the publisher

Run `python -m catalog.tasks.audit_publisher` as a separate supervised process after
Catalog migrations. HTTP startup neither launches workers nor migrates a database.

| CATALOG_ setting | Contract |
|---|---|
| DATABASE_URL | Catalog database only; hidden from settings representation. |
| AUDIT_BROKER_URL | Secret connection URL for the deployment's broker/vhost. |
| AUDIT_BROKER_USER | RabbitMQ user matching the connection; no impersonator privilege. |
| AUDIT_EVENT_SECRET | Independent signing secret, minimum 32 bytes. |
| AUDIT_EVENT_KEY_ID | Rotation identity, default current. |
| AUDIT_EXCHANGE | Durable topic exchange, default platform.audit. |
| AUDIT_BATCH_LIMIT | Default 50; range 1-100. |
| AUDIT_TIMEOUT_SECONDS | Per-publication timeout, default 5; range 1-30. |

Bind Audit's durable `audit.events` queue to these exact routes on that exchange:

| Catalog entity prefix | Audit action suffixes |
|---|---|
| unit_of_measure; pack_type; category_scheme | create, update, activate, deactivate |
| item_group; item_category | create, update, activate, deactivate, move |
| unit_conversion | create |
| unit_tax_code | create, close |
| item_group_parent | create, close |
| field_rebuild_job | start, cancel, chunk, cleanup, failed |
| brand | create, update, activate, deactivate, move |
| brand_series; manufacturer; manufacturer_site; product_type | create, update, activate, deactivate |
| brand_manufacturer | create, close |
| product_type_revision | create, update, publish |
| attribute_definition; attribute_option; attribute_set | create, update, activate, deactivate |
| attribute_set_revision | create, update, publish (membership is audited through its revision) |
| identifier_profile | create, update, activate, deactivate (requirements are audited through the profile) |
| inventory_profile_template | create, update, activate, deactivate |
| inventory_profile_template_revision | create, update, publish |
| warranty_policy | create, update, activate, deactivate |
| warranty_policy_revision | create, update, publish |
| return_policy | create, update, activate, deactivate |
| return_policy_revision | create, update, publish (conditions are audited through the revision) |
| handling_profile | create, update, activate, deactivate |
| handling_profile_revision | create, update, publish |

Every route is `catalog.{entity}.{action}`; the code registry contains 353 exact
contracts across 102 entities as of 2026-09-19 (count from `AUDIT_EVENTS` in
`events/audit_contract.py`, which is the authority — the historical decision-log entries
below capture prior checkpoints). `/reparent` HTTP actions emit `.move`, matching the
original event contract.
Emitters check this same registry inside the domain transaction: a missing registration
rolls back the domain change, receipt and audit event. Future domain publication routes
are separate contracts and cannot accidentally be sent to Audit by this worker.

Publishing marks an outbox row only after a positive broker confirmation. Missing
bindings, disconnects and negative confirms retain the original message ID for retry;
unrelated routes remain untouched. Idle polling waits one second, reconnect failures
wait five seconds, and individual outbox retries back off to a maximum of one hour.
Shutdown closes the channel, connection and database engine. Broker confirmation is
distinct from Audit's durable ingestion, whose inbox remains responsible for deduplication.

Legacy events without company_id remain unchanged. Their visibility requires the
existing tenant audit authority; do not invent company attribution or rewrite an
immutable audit history. New Catalog events use the actual command company, including
hierarchy edges, original-actor job chunks and service cleanup.

Unexpected HTTP failures emit only a timestamp, service, event, error class and a
validated hexadecimal trace ID. They expose the standard safe error envelope. An
already-started stream aborts with a sanitized server error; its status cannot be
rewritten after headers have been sent. Neither request bodies, URLs, SQL parameters,
raw exception messages nor original tracebacks are added to these diagnostics.

Health probes check process/schema readiness. They do not claim broker delivery,
consumer persistence or completion of Product Configuration and other Catalog capabilities.

Verification 2026-09-12: full Catalog 233 passed/one MySQL skip, 99.57% overall and
100% domain coverage.


Decision 2026-09-12: shared 0.14.0 separates exact contract registry capacity (1..1,024)
from delivery batch and prefetch size (1..100). Handling raised Catalog to 105 routes and
reproduced startup/delivery/binding rejection under the old limit. Regressions cover 105 and
1,024 accepted routes, 1,025 rejected routes, unrelated outbox rows staying untouched and
prefetch/batch bounds remaining unchanged. Wildcards remain rejected. This is capacity for
explicit subscriptions, not broader event authority or proof of live broker delivery.


Decision 2026-09-12 (C6.07): master_alias and master_external_key add create/activate/deactivate
audit keys (six total), bringing the exact registry to 111. The existing shared 1024-key registry
bound remains sufficient. There is no mapping update/retarget event. Domain releases remain
separate; publishing an audit event does not assert that Billing has adopted a definition.

Decision 2026-09-12 (V1.2 draft authoring): product_family/item create/update add four exact audit routes; the current registry contains 115 routes. Family/default-SKU creation emits both events within the same aggregate transaction. No activation event is registered before that workflow exists.


Decision 2026-09-12 (V1.2): implemented native configuration and product authoring through
migration 0082. See [V1.2 routes and constraints](catalog-v12-api.md). Earlier checkpoints
above remain historical; activation is documented in [V1.4 contracts](catalog-v14-api.md).

V1.4 adds 44 registered tax/activation audit names (284 total). They remain transactional audit events; complete domain release/consumer acknowledgement remains a separate external integration gate.


V1.5 registers 24 bulk administration audit names (308 total). Job transitions and native
command events commit with the change-set effect and outbox; preview rollback leaves neither
native effects nor native audit events. Internal row outcomes are represented by the owning job
transition. Real RabbitMQ tests verify confirmed routing, unroutable retry, redelivery,
consumer deduplication and dead-letter handling for `catalog.bulk_job.update`. This proves
transport behavior, not Billing policy adoption.

Decision 2026-09-17: the accepted [integration plan](catalog-audit-integration-plan.md) and
[Catalog event contract](catalog-audit-contract.md) extend the existing signed delivery with
current read policies, safe evidence, download events and shared operational recovery.
The generated event matrix is authoritative for current route/category/evidence coverage.

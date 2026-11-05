# Notification Service — Database & Transport Plan

**Status:** Table inventory and MySQL schema implemented under `dbs/notification` and `apis/notification` (26 revisions); send pipeline and management APIs in progress
**Date:** 2026-09-03
**Database:** MySQL 9.6, owned exclusively by `notification`
**Channels:** Email · SMS · WhatsApp · Push
**Related:** [tech-stack.md](tech-stack.md) rules 4.4, 4.6, 4.8, 4.12 · [audit.md](audit.md) · [identity-schema.md](identity-schema.md) §4.3 · [api-conventions.md](api-conventions.md)

This document governs notification transport, tables, migration order and ownership. The service delivers transactional and operational notifications. Marketing-campaign orchestration and a two-way WhatsApp support inbox are separate bounded contexts and are out of scope. The documented schema is implemented under `dbs/notification` and `apis/notification`; live provider certification remains an environment deployment gate.

---

## 1. Ownership and layout

```text
apis/notification/src/notification/
  api/       authenticated management/query routes plus provider callbacks; no send route
  domain/    preference, consent, suppression, routing and state rules
  models/    notification-owned ORM models
  schemas/   messages, callbacks and internal contracts
  events/    consumed and emitted event contracts
  tasks/     delivery workers, retries, expiry and retention

dbs/notification/
  alembic.ini, env.py, versions/    one independent revision chain

libs/platform/
  shared mechanism only
```

`libs/platform` supplies the common SQLAlchemy base/session, UUIDv7 type, tenant filter, `Outbox`, `ProcessedMessage`, outbox writer, RabbitMQ publisher/consumer primitives, callback-verification interfaces, encryption interfaces, logging/OTel setup and test helpers.

`notification` owns provider policy and domain data: templates, routes, provider accounts, recipient delivery health, consent projection, suppressions, requests, deliveries, attempts and receipts. Provider-specific signature algorithms live behind the shared verification interface but are implemented by notification adapters. No notification model moves into `libs/platform` merely because another service publishes notification requests.

Authenticated CRUD and operational list endpoints follow [api-conventions.md](api-conventions.md). In particular, delivery/request lists select lean projections and never load encrypted content or provider payloads; growing history uses keyset cursors rather than offsets.

References to tenant, company, user, invoice or another service's entity are UUID values with no cross-service foreign key.

---

## 2. Transport — decided

### 2.1 Outbound

RabbitMQ is the only send-command transport. Producers write the business change and notification request to their transactional outbox. There is no public or synchronous `send` endpoint. Redelivery reuses the producer's `message_id`; `ProcessedMessage` makes its effect idempotent.

### 2.2 Provider callbacks

Provider-specific HTTPS callbacks terminate in `notification`:

```text
/callbacks/email/{callback_key}
/callbacks/sms/{callback_key}
/callbacks/whatsapp/{callback_key}
/callbacks/push/{callback_key}
```

These are the only unauthenticated HTTP routes. Each route reads and size-limits the raw body, resolves the globally unique non-secret callback key, verifies the provider signature against the raw bytes, enforces timestamp/replay protection where the provider supports it, and validates only the provider's stable envelope fields.

A valid callback commits its encrypted raw body to the deduplicated `provider_event` inbox together with a receipt audit/outbox row, then returns success. A duplicate valid callback also returns success. An asynchronous normalizer parses the versioned event body, writes `delivery_event`, advances `notification_delivery` without state regression, and emits resulting audit/outbox rows in a second transaction. This short durable-inbox path prevents slow normalization or downstream contention from amplifying provider retries. nginx and the application both rate-limit these routes; IP allowlists are defence in depth, never a replacement for signature verification.

This replaces the earlier “consumer-only, no inbound API” wording. The intended boundary is **no client-facing send API**, not “discard provider delivery evidence.”

---

## 3. Database conventions

- Singular snake_case table names; UUIDv7 IDs as `BINARY(16)`.
- UTC `DATETIME(6)` timestamps ending `_at`; codes/states are `VARCHAR`, never DB enums.
- Every tenant-owned table has `tenant_id BINARY(16) NOT NULL` and a two-tenant isolation test.
- `SCOPE_ALL` (zero UUID) represents all-company/all-event scope inside a tenant's unique keys; nullable wildcard columns are forbidden. `provider_account.tenant_id` is always a real tenant.
- Credentials and callback secrets stay in workload identity or the secret manager. Tables store only `credential_ref` / `callback_secret_ref`, never credential material.
- Destinations and rendered content are application-encrypted. Equality lookup uses keyed HMAC, not plain SHA.
- JSON is only for unqueried provider detail. Anything filtered, joined or deduplicated is a real column.
- Semantic evidence is immutable in `consent_event`, `delivery_attempt`, `provider_event` and `delivery_event`. `provider_event.processing_status`/`processed_at` and an in-progress `delivery_attempt` outcome are controlled projections that may advance; raw hashes, provider facts and completed outcomes never change. The only later mutation is an audited retention scrub of encrypted payload bytes.
- One `CREATE TABLE` per revision with indexes and constraints inline; every revision has a downgrade.
- No initial partitioning. In MySQL a partitioned table cannot participate in foreign keys; measured volume must justify weakening those constraints.
- Every table is `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC`. Security tokens such as `callback_key` and `trace_id` override their column to ASCII binary collation.
- `JSON` is MySQL's native binary JSON type. JSON values are never used as primary, unique or foreign keys, and a JSON path is indexed only via a generated column.
- SHA-256 and HMAC-SHA-256 values use `BINARY(32)`, not 64-character hex. Booleans use `TINYINT(1)`; counters use unsigned integer types where negative values are invalid.
- Encrypted variable-size values use `BLOB` or `MEDIUMBLOB`; ciphertext is never indexed. Its keyed HMAC or content hash is indexed instead.

Foreign keys exist only within the notification database. All notification-owned references use named FKs with `RESTRICT` deletion; evidence is never cascade-deleted. Cross-service references (`tenant_id`, `company_id`, `subject_id`, `aggregate_id`, actor ids, correlation ids) deliberately carry no FK. Every FK column has an explicit supporting index so InnoDB never creates a hidden index with an uncontrolled name.

All declared unique keys fit InnoDB's 3072-byte limit under `utf8mb4`; the widest is `(tenant_id, storage_key)` at 2016 bytes. Every unique-key component is `NOT NULL`, avoiding MySQL's multiple-`NULL` uniqueness behaviour.

---

## 4. Migration plan

26 revisions, 25 tables (revision 0026 alters recipient_endpoint). `idempotency_key` is intentionally absent: broker commands dedupe through `processed_message`, and callbacks through `provider_event`. Add it only if a command API is introduced.

### Phase N0 — shared delivery guarantees

| Rev | Table | Important shape |
|---|---|---|
| `0001` | `outbox` | Shared `libs/platform` model unchanged; outgoing audit and status events |
| `0002` | `processed_message` | Shared model unchanged; PK `(consumer_name, message_id)` |

`outbox` uses the shared physical shape:

```text
id             BINARY(16) NOT NULL
tenant_id      BINARY(16) NULL
aggregate_type VARCHAR(80) NOT NULL
aggregate_id   BINARY(16) NOT NULL
event_type     VARCHAR(120) NOT NULL
payload        JSON NOT NULL
schema_version SMALLINT NOT NULL
message_id     BINARY(16) NOT NULL
trace_id       VARCHAR(32) NULL
occurred_at    DATETIME(6) NOT NULL
available_at   DATETIME(6) NOT NULL
published_at   DATETIME(6) NULL
attempt_count  SMALLINT NOT NULL
last_error     TEXT NULL
```

Keys: PK `id` · UNIQUE `(message_id)` · INDEX `(published_at, available_at)` · INDEX `(aggregate_type, aggregate_id)`.

`processed_message` uses:

```text
consumer_name VARCHAR(120) NOT NULL
message_id    BINARY(16) NOT NULL
processed_at  DATETIME(6) NOT NULL
```

Keys: PK `(consumer_name, message_id)` · INDEX `(processed_at)`.

**Exit:** one source `message_id` creates one request; rollback leaves neither the request nor dedupe/outbox rows.

### Phase N1 — providers and recipients

#### `0003 provider_account`

```text
id                  BINARY(16) NOT NULL
tenant_id           BINARY(16) NOT NULL
key                 VARCHAR(80) NOT NULL
callback_key        CHAR(43) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
channel             VARCHAR(20) NOT NULL
provider_key        VARCHAR(60) NOT NULL
display_name        VARCHAR(150) NOT NULL
credential_ref      VARCHAR(500) NOT NULL
callback_secret_ref VARCHAR(500) NULL
region              VARCHAR(40) NULL
status              VARCHAR(20) NOT NULL
capabilities        JSON NULL
created_at          DATETIME(6) NOT NULL
created_by          BINARY(16) NULL
updated_at          DATETIME(6) NOT NULL
updated_by          BINARY(16) NULL
```

Channels: `email | sms | whatsapp | push`. Status: `pending | active | suspended | disabled`. `callback_key` is a random, globally unique, non-secret routing identifier; it reveals no tenant or provider credential.

Keys: UNIQUE `(tenant_id, key)` · UNIQUE `(callback_key)` · INDEX `(tenant_id, channel, status)`.

`credential_ref` may identify a secret-manager entry, AWS IAM role, GCP workload identity/ADC configuration, or another code-registered credential source. `callback_secret_ref` may be null only when the provider's registered verifier uses an asymmetric/provider-native trust mechanism; domain validation rejects a provider account with no usable verifier.

`tenant_id` is always a real tenant. When the platform supplies one provider credential to many tenants, provisioning creates one logical account row per tenant and may give those rows the same `credential_ref`. This preserves the ordinary session filter and prevents one special provider row becoming a cross-tenant metadata path.

Callback lookup is the sole pre-tenant query: it runs under the shared audited `unfiltered()` escape hatch and selects exactly one row by globally unique `callback_key`. The adapter immediately establishes that row's tenant context before reading or writing any other table. The callback key is never accepted as authority; the provider signature is still mandatory.

#### `0004 sender_identity`

```text
id                  BINARY(16) NOT NULL
tenant_id           BINARY(16) NOT NULL
provider_account_id BINARY(16) NOT NULL
key                 VARCHAR(80) NOT NULL
sender_type         VARCHAR(30) NOT NULL
external_sender_id  VARCHAR(255) NOT NULL
display_name        VARCHAR(150) NOT NULL
reply_to_ciphertext BLOB NULL
verification_status VARCHAR(20) NOT NULL
capabilities        JSON NULL
verified_at         DATETIME(6) NULL
is_active           TINYINT(1) NOT NULL
created_at          DATETIME(6) NOT NULL
created_by          BINARY(16) NULL
updated_at          DATETIME(6) NOT NULL
updated_by          BINARY(16) NULL
deactivated_at      DATETIME(6) NULL
deactivated_by      BINARY(16) NULL
```

Represents an email address/domain, SMS sender id/number, WhatsApp business number, or Push application. A route may use only an active verified sender matching its provider channel.

Keys: UNIQUE `(provider_account_id, key)` · UNIQUE `(provider_account_id, external_sender_id)`.

#### `0005 recipient_endpoint`

```text
id                     BINARY(16) NOT NULL
tenant_id              BINARY(16) NOT NULL
subject_type           VARCHAR(40) NOT NULL
subject_id             BINARY(16) NOT NULL
channel                VARCHAR(20) NOT NULL
destination_ciphertext BLOB NULL
destination_hmac       BINARY(32) NOT NULL
destination_masked     VARCHAR(320) NOT NULL
locale                 VARCHAR(35) NOT NULL
timezone               VARCHAR(64) NOT NULL
verification_status    VARCHAR(20) NOT NULL
health_status          VARCHAR(20) NOT NULL
failure_count          INT UNSIGNED NOT NULL
last_success_at        DATETIME(6) NULL
last_failure_at        DATETIME(6) NULL
source_version         BIGINT UNSIGNED NOT NULL
is_active              TINYINT(1) NOT NULL
created_at             DATETIME(6) NOT NULL
updated_at             DATETIME(6) NOT NULL
deactivated_at         DATETIME(6) NULL
```

`identity` remains master for user contact data; this local projection owns delivery health. Shared household addresses are valid, so a destination is not globally unique.

An active endpoint requires ciphertext. Deactivation/anonymization may purge it while retaining the keyed HMAC, masked evidence and historical delivery references.

Keys: UNIQUE `(tenant_id, subject_type, subject_id, channel, destination_hmac)` · lookup indexes by subject and destination HMAC.

#### `0006 notification_preference`

```text
id                BINARY(16) NOT NULL
tenant_id         BINARY(16) NOT NULL
subject_type      VARCHAR(40) NOT NULL
subject_id        BINARY(16) NOT NULL
event_key         VARCHAR(120) NOT NULL
channel           VARCHAR(20) NOT NULL
is_enabled        TINYINT(1) NOT NULL
source_version    BIGINT UNSIGNED NOT NULL
source_updated_at DATETIME(6) NOT NULL
projected_at      DATETIME(6) NOT NULL
```

Read-only projection of `identity.user_notification_preference`.

Keys: UNIQUE `(tenant_id, subject_type, subject_id, event_key, channel)`.

#### `0007 consent_state`

```text
id                    BINARY(16) NOT NULL
tenant_id             BINARY(16) NOT NULL
recipient_endpoint_id BINARY(16) NOT NULL
purpose               VARCHAR(30) NOT NULL
state                 VARCHAR(20) NOT NULL
lawful_basis          VARCHAR(40) NULL
evidence_ref          VARCHAR(500) NULL
effective_at          DATETIME(6) NOT NULL
expires_at            DATETIME(6) NULL
last_event_id         BINARY(16) NOT NULL
updated_at            DATETIME(6) NOT NULL
```

Fast current projection. State: `granted | denied | withdrawn | unknown`.

Keys: UNIQUE `(recipient_endpoint_id, purpose)` · INDEX `(tenant_id, state, expires_at)`.

#### `0008 consent_event`

```text
id                    BINARY(16) NOT NULL
tenant_id             BINARY(16) NOT NULL
recipient_endpoint_id BINARY(16) NOT NULL
purpose               VARCHAR(30) NOT NULL
state                 VARCHAR(20) NOT NULL
source                VARCHAR(40) NOT NULL
source_event_key      VARCHAR(255) NOT NULL
actor_user_id         BINARY(16) NULL
evidence_ref          VARCHAR(500) NULL
occurred_at           DATETIME(6) NOT NULL
recorded_at           DATETIME(6) NOT NULL
metadata              JSON NULL
```

Append-only legal evidence.

Keys: UNIQUE `(tenant_id, source, source_event_key)` · history index by endpoint/purpose/time.

#### `0009 suppression`

```text
id                    BINARY(16) NOT NULL
tenant_id             BINARY(16) NOT NULL
recipient_endpoint_id BINARY(16) NULL
channel               VARCHAR(20) NOT NULL
destination_hmac      BINARY(32) NOT NULL
scope_type            VARCHAR(20) NOT NULL
scope_key             VARCHAR(120) NOT NULL
reason                VARCHAR(40) NOT NULL
source                VARCHAR(40) NOT NULL
source_event_key      VARCHAR(255) NOT NULL
valid_from            DATETIME(6) NOT NULL
valid_to              DATETIME(6) NULL
created_at            DATETIME(6) NOT NULL
created_by            BINARY(16) NULL
```

Covers opt-out, complaint, hard/temporary bounce, invalid address, provider rejection and manual block. Validity dates—not `is_active`—retain evidence after a temporary suppression expires.

Keys: UNIQUE `(tenant_id, source, source_event_key)` · resolution index `(tenant_id, channel, destination_hmac, valid_from, valid_to)`.

**Exit:** tenant isolation passes; raw destinations never appear in logs/outbox/audit; preference, consent and suppression resolve independently; active suppression and expired consent block delivery.

### Phase N2 — templates and routing

#### `0010 notification_template`

```text
id               BINARY(16) NOT NULL
tenant_id        BINARY(16) NOT NULL
company_id       BINARY(16) NOT NULL
key              VARCHAR(80) NOT NULL
event_key        VARCHAR(120) NOT NULL
category         VARCHAR(30) NOT NULL
description      VARCHAR(500) NULL
default_locale   VARCHAR(35) NOT NULL
variable_schema  JSON NOT NULL
is_active        TINYINT(1) NOT NULL
created_at       DATETIME(6) NOT NULL
created_by       BINARY(16) NULL
updated_at       DATETIME(6) NOT NULL
updated_by       BINARY(16) NULL
deactivated_at   DATETIME(6) NULL
deactivated_by   BINARY(16) NULL
```

Categories: `security | transactional | operational | marketing`. `company_id = SCOPE_ALL` means tenant-wide.

Keys: UNIQUE `(tenant_id, company_id, key)` · event lookup index.

#### `0011 template_variant`

```text
id               BINARY(16) NOT NULL
tenant_id        BINARY(16) NOT NULL
template_id      BINARY(16) NOT NULL
channel          VARCHAR(20) NOT NULL
locale           VARCHAR(35) NOT NULL
is_active        TINYINT(1) NOT NULL
created_at       DATETIME(6) NOT NULL
created_by       BINARY(16) NULL
deactivated_at   DATETIME(6) NULL
deactivated_by   BINARY(16) NULL
```

Keys: UNIQUE `(template_id, channel, locale)`.

#### `0012 template_version`

```text
id                  BINARY(16) NOT NULL
tenant_id           BINARY(16) NOT NULL
template_variant_id BINARY(16) NOT NULL
version             INT UNSIGNED NOT NULL
subject_text        VARCHAR(998) NULL
body_text           MEDIUMTEXT NOT NULL
body_html           MEDIUMTEXT NULL
channel_payload     JSON NULL
content_sha256      BINARY(32) NOT NULL
created_at          DATETIME(6) NOT NULL
created_by          BINARY(16) NULL
```

Immutable. Editing creates a new version. Only Email may use subject/HTML. Template expressions have no code execution, network access, attribute traversal or raw SQL.

Keys: UNIQUE `(template_variant_id, version)` · UNIQUE `(template_variant_id, content_sha256)`.

#### `0013 template_activation`

```text
id                  BINARY(16) NOT NULL
tenant_id           BINARY(16) NOT NULL
template_variant_id BINARY(16) NOT NULL
template_version_id BINARY(16) NOT NULL
valid_from          DATETIME(6) NOT NULL
valid_to            DATETIME(6) NULL
activated_by        BINARY(16) NULL
activation_reason   VARCHAR(500) NULL
created_at          DATETIME(6) NOT NULL
```

Date-effective publication history. Overlaps are rejected in `domain/` under a lock; historic deliveries retain their selected version.

Keys: indexes `(template_variant_id, valid_from, valid_to)` and `(tenant_id, valid_from, valid_to)`.

#### `0014 provider_template_binding`

```text
id                    BINARY(16) NOT NULL
tenant_id             BINARY(16) NOT NULL
template_version_id   BINARY(16) NOT NULL
provider_account_id   BINARY(16) NOT NULL
external_template_id  VARCHAR(255) NOT NULL
external_name         VARCHAR(512) NOT NULL
external_language     VARCHAR(35) NOT NULL
external_category     VARCHAR(40) NULL
approval_status       VARCHAR(20) NOT NULL
quality_status        VARCHAR(20) NULL
rejection_code        VARCHAR(120) NULL
rejection_detail      VARCHAR(1000) NULL
submitted_at          DATETIME(6) NULL
reviewed_at           DATETIME(6) NULL
synced_at             DATETIME(6) NOT NULL
```

Mandatory for outbound WhatsApp template delivery. Approval: `pending | approved | paused | rejected | disabled`.

Keys: UNIQUE `(provider_account_id, external_template_id)` · UNIQUE `(template_version_id, provider_account_id)`.

#### `0015 routing_rule`

```text
id                      BINARY(16) NOT NULL
tenant_id               BINARY(16) NOT NULL
company_id              BINARY(16) NOT NULL
event_key               VARCHAR(120) NOT NULL
category                VARCHAR(30) NOT NULL
channel                 VARCHAR(20) NOT NULL
provider_account_id     BINARY(16) NOT NULL
sender_identity_id      BINARY(16) NOT NULL
priority                SMALLINT UNSIGNED NOT NULL
weight                  SMALLINT UNSIGNED NOT NULL
max_attempts            SMALLINT UNSIGNED NOT NULL
timeout_seconds         SMALLINT UNSIGNED NOT NULL
initial_backoff_seconds INT UNSIGNED NOT NULL
max_backoff_seconds     INT UNSIGNED NOT NULL
conditions              JSON NULL
is_active               TINYINT(1) NOT NULL
created_at              DATETIME(6) NOT NULL
created_by              BINARY(16) NULL
updated_at              DATETIME(6) NOT NULL
updated_by              BINARY(16) NULL
deactivated_at          DATETIME(6) NULL
deactivated_by          BINARY(16) NULL
```

Resolution is deterministic: company/event, company/category, tenant/event, tenant/category, then the tenant's provisioned platform-default route. Selected configuration is copied to the delivery so later edits cannot rewrite history.

Keys: UNIQUE `(tenant_id, company_id, event_key, category, channel, priority)` · active resolution index.

**Exit:** versions cannot mutate; activation cannot overlap; routing fixtures are deterministic; WhatsApp refuses an unapproved provider binding; deactivation does not hide history.

### Phase N3 — requests, delivery and receipts

#### `0016 notification_request`

```text
id                 BINARY(16) NOT NULL
tenant_id          BINARY(16) NOT NULL
company_id         BINARY(16) NOT NULL
source_service     VARCHAR(40) NOT NULL
source_message_id  BINARY(16) NOT NULL
source_event_key   VARCHAR(120) NOT NULL
event_key          VARCHAR(120) NOT NULL
category           VARCHAR(30) NOT NULL
aggregate_type     VARCHAR(80) NOT NULL
aggregate_id       BINARY(16) NOT NULL
correlation_id     BINARY(16) NULL
causation_id       BINARY(16) NULL
trace_id           CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL
priority           TINYINT UNSIGNED NOT NULL
scheduled_at       DATETIME(6) NULL
expires_at         DATETIME(6) NULL
context_ciphertext MEDIUMBLOB NOT NULL
context_sha256     BINARY(32) NOT NULL
encryption_key_ref VARCHAR(500) NOT NULL
status             VARCHAR(20) NOT NULL
received_at        DATETIME(6) NOT NULL
completed_at       DATETIME(6) NULL
```

One logical source event. Context is encrypted because variables contain names, invoice references and amounts.

Keys: UNIQUE `(source_message_id)` · INDEX `(tenant_id, status, scheduled_at)` · aggregate/correlation indexes.

#### `0017 notification_delivery`

```text
id                           BINARY(16) NOT NULL
tenant_id                    BINARY(16) NOT NULL
request_id                   BINARY(16) NOT NULL
recipient_endpoint_id        BINARY(16) NOT NULL
channel                      VARCHAR(20) NOT NULL
destination_hmac             BINARY(32) NOT NULL
destination_masked           VARCHAR(320) NOT NULL
template_version_id          BINARY(16) NOT NULL
provider_template_binding_id BINARY(16) NULL
provider_account_id          BINARY(16) NOT NULL
sender_identity_id           BINARY(16) NOT NULL
routing_rule_id              BINARY(16) NOT NULL
status                       VARCHAR(20) NOT NULL
status_reason                VARCHAR(120) NULL
attempt_count                SMALLINT UNSIGNED NOT NULL
next_attempt_at              DATETIME(6) NULL
accepted_at                  DATETIME(6) NULL
delivered_at                 DATETIME(6) NULL
read_at                      DATETIME(6) NULL
failed_at                    DATETIME(6) NULL
completed_at                 DATETIME(6) NULL
provider_message_id          VARCHAR(255) NULL
created_at                   DATETIME(6) NOT NULL
updated_at                   DATETIME(6) NOT NULL
```

Mutable current projection. States: `pending | scheduled | suppressed | sending | accepted | delivered | read | retry_wait | failed | cancelled | expired`. Boot-validated state precedence prevents late callbacks from regressing delivered/read state.

Keys: UNIQUE `(request_id, recipient_endpoint_id, channel)` · INDEX `(tenant_id, status, next_attempt_at)` · INDEX `(provider_account_id, provider_message_id)`.

#### `0018 notification_content`

```text
delivery_id          BINARY(16) NOT NULL
tenant_id            BINARY(16) NOT NULL
subject_ciphertext   BLOB NULL
body_text_ciphertext MEDIUMBLOB NULL
body_html_ciphertext MEDIUMBLOB NULL
payload_ciphertext   MEDIUMBLOB NULL
content_sha256       BINARY(32) NOT NULL
encryption_key_ref   VARCHAR(500) NOT NULL
created_at           DATETIME(6) NOT NULL
expires_at           DATETIME(6) NOT NULL
purged_at            DATETIME(6) NULL
```

Cold sensitive snapshot separate from the hot delivery row. A newly rendered row requires body ciphertext; the database permits `NULL` only so retention purging can remove it while retaining the hash and delivery evidence.

#### `0019 delivery_attempt`

```text
id                    BINARY(16) NOT NULL
tenant_id             BINARY(16) NOT NULL
delivery_id           BINARY(16) NOT NULL
attempt_number        SMALLINT UNSIGNED NOT NULL
provider_account_id   BINARY(16) NOT NULL
sender_identity_id    BINARY(16) NOT NULL
attempt_key           VARCHAR(255) NOT NULL
provider_message_id   VARCHAR(255) NULL
started_at            DATETIME(6) NOT NULL
completed_at          DATETIME(6) NULL
latency_ms            INT UNSIGNED NULL
outcome               VARCHAR(30) NOT NULL
http_status           SMALLINT UNSIGNED NULL
provider_error_code   VARCHAR(120) NULL
error_class           VARCHAR(80) NULL
retry_after_at        DATETIME(6) NULL
request_sha256        BINARY(32) NOT NULL
response_sha256       BINARY(32) NULL
metadata              JSON NULL
```

Prepared before the network call and immutable after finalization. Outcome: `in_progress | accepted | retryable_failure | permanent_failure | unknown`. `attempt_key` remains stable across an ambiguous timeout retry when the provider supports idempotency. When it does not, an ambiguous result stays `unknown` for reconciliation or an authorized manual decision; the worker never blindly creates a possible duplicate.

Keys: UNIQUE `(delivery_id, attempt_number)` · UNIQUE `(provider_account_id, attempt_key)` · provider-message index.

#### `0020 provider_event`

```text
id                   BINARY(16) NOT NULL
tenant_id            BINARY(16) NOT NULL
provider_account_id  BINARY(16) NOT NULL
external_event_key   VARCHAR(255) NOT NULL
provider_message_id  VARCHAR(255) NULL
event_type           VARCHAR(80) NOT NULL
signature_verified   TINYINT(1) NOT NULL
provider_occurred_at DATETIME(6) NULL
received_at          DATETIME(6) NOT NULL
payload_ciphertext   MEDIUMBLOB NULL
payload_sha256       BINARY(32) NOT NULL
encryption_key_ref   VARCHAR(500) NOT NULL
delivery_id          BINARY(16) NULL
processing_status    VARCHAR(20) NOT NULL
processed_at         DATETIME(6) NULL
processing_error     VARCHAR(500) NULL
```

Durable callback inbox. Valid unmatched callbacks are retained for reconciliation instead of discarded. Persisted external events always have `signature_verified = true`. Raw provider facts are immutable; only processing state advances. A new row requires payload ciphertext; retention purging may later null it while keeping its hash and normalized event.

Keys: UNIQUE `(provider_account_id, external_event_key)` · provider-message and unmatched-processing indexes.

#### `0021 delivery_event`

```text
id                   BINARY(16) NOT NULL
tenant_id            BINARY(16) NOT NULL
delivery_id          BINARY(16) NOT NULL
source               VARCHAR(40) NOT NULL
source_event_key     VARCHAR(255) NOT NULL
from_status          VARCHAR(20) NULL
to_status            VARCHAR(20) NOT NULL
reason_code          VARCHAR(120) NULL
provider_occurred_at DATETIME(6) NULL
observed_at          DATETIME(6) NOT NULL
metadata             JSON NULL
```

Append-only normalized history. Every current-state transition has exactly one event; out-of-order provider events retain both provider and observation timestamps.

Keys: UNIQUE `(source, source_event_key)` · INDEX `(tenant_id, delivery_id, observed_at)`.

**Exit:** duplicates have one effect; retries create attempts, not deliveries; callbacks cannot regress state; unmatched callbacks survive; rollback leaves no event/outbox row; every channel passes accepted, delivered and permanent-failure fixtures.

### Phase N4 — attachments

#### `0022 attachment`

```text
id                  BINARY(16) NOT NULL
tenant_id           BINARY(16) NOT NULL
storage_key         VARCHAR(500) NOT NULL
filename_ciphertext BLOB NOT NULL
media_type          VARCHAR(255) NOT NULL
byte_size           BIGINT UNSIGNED NOT NULL
sha256              BINARY(32) NOT NULL
scan_status         VARCHAR(20) NOT NULL
created_at          DATETIME(6) NOT NULL
expires_at          DATETIME(6) NOT NULL
purged_at           DATETIME(6) NULL
```

Bytes live in private object storage. Scan status: `pending | clean | infected | failed`; only `clean` can send.

Keys: UNIQUE `(tenant_id, storage_key)` · expiry and scan-status indexes.

#### `0023 delivery_attachment`

```text
delivery_id  BINARY(16) NOT NULL
attachment_id BINARY(16) NOT NULL
tenant_id     BINARY(16) NOT NULL
disposition   VARCHAR(20) NOT NULL
content_id    VARCHAR(255) NULL
display_order SMALLINT UNSIGNED NOT NULL
```

Keys: PK `(delivery_id, attachment_id)` · UNIQUE `(delivery_id, display_order)`.

**Exit:** unclean attachments cannot send; object purge retains checksum evidence; cross-tenant association is rejected and tested.

---

## 5. Send-time resolution

The planning transaction performs these gates in order:

1. Dedupe the source message.
2. Resolve an active endpoint.
3. Resolve preference for subject/event/channel.
4. Resolve category-specific consent.
5. Reject an active suppression.
6. Resolve the active template variant and immutable version.
7. Require an approved binding for WhatsApp.
8. Resolve route, provider and verified sender.
9. Create delivery and encrypted content snapshot.
10. Emit audit/status events through the local outbox.

Security, transactional, operational and marketing category policies are a code catalogue—not tenant-authored expressions.

---

## 6. Retention defaults

| Data | Default | Treatment |
|---|---:|---|
| Rendered content and raw callback payload | 90 days | Cryptographic purge; retain hashes and normalized evidence |
| Requests, attempts and delivery events | 13 months | Archive, then delete under jurisdiction policy |
| `processed_message` | 90 days | Must exceed maximum broker replay window |
| Consent and suppression evidence | 7 years after final validity | Archive; longer jurisdiction rules win |
| Provider configuration and template history | While referenced + 7 years | Deactivate; never delete while referenced |

These are minimum platform defaults. Shortening one is a documented compliance decision; jurisdiction requirements may extend it.

---

## 7. Decisions recorded

- Provider callbacks live in `notification`; a separate callback service adds a hop and another dedupe boundary without creating a bounded context.
- Business sends enter only through RabbitMQ/outbox; no public send API exists.
- WhatsApp is first-class, not disguised as SMS: it has approved template bindings and read receipts.
- WhatsApp is outbound-only here. Conversations, agent assignment and inbox state belong to a future support-messaging context.
- Core tables are provider-neutral; provider-specific parsing and signature logic are adapters.
- Preference, consent and suppression remain separate.
- Template versions and delivery evidence are immutable.
- Sensitive content expires before delivery evidence.
- No table is partitioned until measured volume justifies losing foreign-key support.

## 8. Open questions

None for database structure, ownership or transport. Provider vendor selection populates `provider_account` without changing the schema.

#### `0024 party_endpoint_checkpoint`

One tenant/company/party/purpose/channel checkpoint holds Accounting's monotonic
source version and selected endpoint id. Contact replacement deactivates the old
endpoint; stale snapshots cannot reactivate it.

#### `0025 voucher_send_state`

One tenant/company/voucher row records the latest terminal voucher version and
status. It fences late send commands and cancels pending deliveries while preserving
already accepted provider attempts as evidence.

#### `0026 recipient_endpoint company fence`

Projected party endpoints carry a non-null company id. Existing general/Identity
endpoints are backfilled with the all-company sentinel; Accounting replays its
contact snapshots to create company-owned party endpoints. The endpoint uniqueness
key and voucher recipient lookup include company id, preventing a same-ID contact
in another company from being selected. Downgrade refuses to collapse two
company-specific endpoints into a conflicting legacy uniqueness key.


## 9. Platform and tenant API ownership amendment (2026-10-22)

The [platform/tenant API plan](notification-platform-tenant-api-plan.md) is accepted
for phased implementation. See the [execution TODO](notification-platform-tenant-todo.md)
for current evidence. The earlier 26-revision inventory is the legacy baseline.

`notification_space` adds an isolation dimension inside a real owning tenant. Tenant
space IDs equal tenant IDs. The platform space belongs to a configured real operating
tenant and has a distinct space ID. Session guards and composite foreign keys enforce
both dimensions. The all-company sentinel never denotes platform ownership.

`/v1/platform/...` requires Identity's purpose-bound configured-operator proof and
`platform.notification_*` grants. `/v1/...` retains tenant authority. Platform staff
and pre-tenant delivery evidence stays in platform space; target tenant IDs are only
external references. Platform grants never expose customer business deliveries.

Dated use-case assignments choose templates by purpose, trigger, company and channel.
Existing unambiguous tenant templates retain a compatibility resolver; platform traffic
requires explicit assignments. There is no implicit cross-owner/channel fallback.
Credentials use operator-registered owner-bound bindings. Workers obtain provider
approval and sender verification; administrator assertions are not provider evidence.
External attachments are explicitly unavailable pending private artifact/scanner handoff.

Decision log: adopted spaces, platform/pre-tenant execution, native SNS/Twilio/Meta
callback trust, durable planning outcomes and typed template variables. The existing
seven-service architecture, datastore, RabbitMQ transport and category policy remain.

The implementation now has matching models/migrations through **0116**. Platform
channels require explicit enablement; only existing tenant space retains the legacy
unset-channel compatibility default. An assignment's history disables legacy fallback,
and selection uses a requested language only if it has an active version. Delivery
snapshots preserve the assignment and ordered provider parameters. Provider approval
sync compares positional WhatsApp text content/components with the local version.

Audit includes safe realm/space context. Ordinary tenant audit/activity/detail/export
surfaces exclude platform Notification evidence, which is available through platform
history under exact Notification permission families. Callback query values are
redacted before application access logging as well as at nginx.

Native callback trust amendment: Twilio has no signed freshness timestamp, and delayed
SNS/Meta delivery retries cannot use the gateway's short clock window. Native raw-body
or URL/form signatures, owner-bound routing and durable constituent-event deduplication
are the replay boundary for these callbacks. SNS rejects future timestamps and verifies
certificate validity; provider occurrence times are retained when supplied. This is the
explicit provider-protocol qualification to the general webhook timestamp rule, not a
generic unsigned or shared-secret email fallback.

Decision log (2026-10-22, implementation reviews): adopted fail-closed expired assignment
selection, provider/credential verification invalidation, immutable rendered provider
payloads, callback access-log redaction, provider content comparison, bounded DB-backed
dispatch admission and separate platform Audit visibility. Supported WhatsApp components
are positional text header/body and URL buttons; named parameters/media need a separately
versioned contract. See [operations](notification-operations.md) for configuration,
compatibility, migration/recovery and deliberate channel activation.

Decision log (2026-10-27): platform tenant provisioning stages
`tenant.administrator.ready` with trigger `identity.tenant_administrator.ready`,
email destination, and typed `sign_in_url`/`username` variables. Passwords are
excluded. Delivery still depends on an enabled platform email channel, template
assignment and provider routing; manual handoff is always available.

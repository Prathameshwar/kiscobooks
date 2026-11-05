# Voucher notification execution

Voucher sharing is opt-in per published voucher configuration. Vouchers owns the
decision to notify; Notification owns party endpoints, template/route selection,
delivery attempts and provider receipts. A send command and audit event are committed
with the voucher operation through the outbox. A send failure never changes posting.

## Implemented phases

1. Separate signed Vouchers and Accounting publishers and authenticated,
   company-scoped Notification consumers. Legacy unauthenticated send ingress is
   disabled. Broker replay deduplicates by message id.
2. Accounting emits a versioned contact snapshot. Notification projects one selected
   destination for each party, purpose and channel, deactivates replaced destinations,
   and rejects stale versions. Party endpoints are fenced by company; the Accounting backfill emits fresh versions after the fence migration.
3. Published configuration controls eligible channels and automatic lifecycle events.
   Manual share requires `vouchers.share`, voucher read access, field visibility,
   final status, a party on the frozen revision, and an idempotency key. Ambiguous
   automatic recipients are skipped with an audit event.
4. Notification exposes company-scoped voucher request/delivery evidence. Terminal
   voucher states fence late send commands and cancel pending deliveries.
5. The dispatch worker supports SES, Twilio SMS, Meta WhatsApp and FCM through
   environment credential references. Dispatch is disabled by default and is started
   only with `NOTIFICATION_DISPATCH_ENABLED=true`. Retryable provider failures get
   bounded backoff. Unknown/stuck sends require reconciliation, not blind retry.

## Release controls and current limits

- No voucher artifact or statutory invoice attachment is sent. Voucher artifact
  rendering is permission-specific and the current invoice artifact is not a
  certified statutory export. External attachment delivery needs a separate
  immutable, party-safe artifact contract and malware-scan handoff.
- Templates, active routes, verified senders, provider accounts, permitted endpoint
  and consent/suppression policy must be provisioned before enabling a channel.
  No default voucher configuration enables sending.
- Provision the two publisher secrets, broker identities and exact tenant/company
  source grants in Notification. Credentials referenced by `ProviderAccount` must
  be injected into the dispatch process environment; they are never stored in SQL.
- Live provider callback certification, MySQL migration/EXPLAIN checks and
  company-by-company canary remain deployment gates. Automated fixture tests
  cannot prove a provider will accept a real send.

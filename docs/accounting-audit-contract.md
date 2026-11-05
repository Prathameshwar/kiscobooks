# Accounting audit contract

Accepted with the seven-phase plan on 2026-09-17. Execution is tracked in
[the integration review](accounting-audit-integration-review.md).

## Events and cardinality

The source of current event names is `accounting.events.audit_contract.AUDIT_EVENTS`.
`apis/audit/src/audit/data/accounting-legacy-v1.json` is a frozen compatibility registry;
it is not expanded when new events are added. The generated event matrix is
`apis/accounting/contracts/audit-events.json`.

| Operations | Category | Evidence and cardinality |
|---|---|---|
| Master create/edit/activate/retire; aliases, profiles, dated policies | admin | One event per changed business row, with existing local revision |
| Setup, template installation, metadata upgrade | admin | Parent receipt plus each explicitly changed master; derived hierarchy/bindings covered by parent |
| Mapping draft create/edit/publish | admin | Draft revision plus actual mapping changes; IDs distinguish draft and published mapping |
| Import preview | none committed | All tentative business rows, revisions and outbox entries roll back |
| Import apply | underlying category | Events for committed row changes; command replay adds no events |
| Financial setup, fiscal year/period creation and transitions | money | Each changed period/setup row; transition record represented by period event |
| Journal draft/prepare/post/void/reversal and lines | money | Each explicit command/changed row; reversal retains original journal reference |
| Opening batches, source documents, open items, allocations | money | Explicit create/post/finalize/reverse and resulting changed records |
| Credit reservations and overrides | money | Create/consume/release/approve and related state changes |
| Charge policy | admin | Effective configuration changes |
| Charge assessments and tax snapshots | money | Calculate/approve/waive/reject/post/reverse and changed records |
| Accounting paginated exports | access | One event per successful page, including an empty page; safe row count/resource |
| Bank/tax/payment master detail reads | access | One event per successful detail response; references only |
| Audit export | access | One event per successful bounded export; delivered through Audit's own outbox |
| Ordinary lists, metadata, history and ordinary details | none | No access event |

All events carry authoritative tenant/company, entity reference, original/effective actor IDs,
source timestamp and a stable message ID. Event names are full `accounting.<entity>.<action>`
strings in both the route and new `payload.action`. Existing local revision actions stay short.
No synchronous Audit HTTP call is permitted inside an Accounting mutation.

## Compatibility and evidence

Authenticated Accounting schema-v1 messages whose exact route/entity/short-action tuple exists
in the frozen registry may be ingested with their original action unchanged. Their event body,
message ID and occurrence time are not rewritten. Source identity, signature, audience, route,
schema and entity remain validated. New access events are not part of this legacy exception.
Audit's historical `audit.exported`/`exported` pair has the same explicit, issuer-bound exception.

Safe evidence is allowlisted by resource; unlisted values remain `{changed: true}`. Dates,
status, structural UUID references and exact Decimal money/quantity strings can be recorded.
Money changes carry their currency field when present. Names, descriptions, arbitrary JSON,
custom values, contact details, identifiers, bank data and unrestricted reasons are excluded.
A reason is represented by its owning entity reference and a changed marker, never copied text.
Unknown old values are represented as markers, not fabricated nulls. Actual creates use null
as the old value. Trusted trace/request identifiers are bounded and validated.

Read policy is resolved by Identity for the actual reader, separately from the writer. For
historical data, conditional denies are applied conservatively because current row state cannot
prove a historical condition. Tenant-wide policy transport includes applicable scoped role
assignments; it must not discard company/department policies. Missing policy context hides
Accounting field evidence. Denied field names and their values are omitted from Audit responses.
Accounting context is separately restricted to an integer returned-row count (0-5000). Legacy
free-text context and reasons are omitted from detail and export responses so they cannot carry
denied field values around the field-policy projection. Stored evidence and hashes remain
unchanged; a redacted response is not a complete hash input.

## Delivery and recovery

Publication success means broker confirmation, not ingestion. HTTP readiness and delivery
health are separate. Exhausted rows and dead letters are visible. Recovery selects explicit
message IDs after a dry run and preserves identities; it never resets the entire outbox.
Audited exports are bounded API responses; access events mean served data, not a saved file.
No new public file-download/storage facility is introduced.

Authenticated payloads must also fit the existing Audit storage contract: action 60 characters,
entity type 80, reason 500, actor type 32, actor IP 45, user agent 400, source service 40 and
request ID 64. Changes/context must contain JSON-compatible finite values. Invalid payloads
are rejected to the dead-letter queue before a database session opens; database outages remain
retryable. Stored or signed evidence is never truncated or rewritten to fit these bounds.

## Decision log

- 2026-09-17: retain schema version 1 and original legacy actions using exact authenticated
  compatibility entries; new producers emit canonical full actions. Keep marker support and
  local revision contracts. Add private safe-value snapshots and conservative read redaction.
- 2026-09-17: an export page and each sensitive detail read is a distinct access operation;
  mutation idempotency remains unchanged. Free-text reasons remain referenced in the source.

- 2026-09-17 review: suppress legacy Accounting context/reasons at the response boundary;
  resolve optional actor names separately through Identity `user.read`, with ID fallbacks.
- 2026-09-17 final review: enforce existing storage limits and finite JSON at ingress;
  detect duplicate sequences across verifier pages using the physical row key as a tie-breaker.

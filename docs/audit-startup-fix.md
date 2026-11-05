# Audit delivery startup repair, 2026-11-03

## Follow-up: Design migration blocks startup, 2026-11-04

Design's working-tree build expects revision `0009`, while the local database is
at `0008`. The startup failure returned before audit contract preparation and
worker launch, leaving all nine configured audit workers stopped. Design also
needed its private publisher configuration refreshed.

Audit preparation and worker startup now run before the API-failure exit, alongside
the existing execution and report recovery workers. A failed API still makes startup
fail. Audit contract preparation must succeed before workers start, and a worker
failure stops the audit launch sequence and preserves the failed startup result.

The regression fixture reproduced the missing audit launch, then passed after the
change. All 12 focused startup/audit lifecycle tests passed. Live recovery reported
all eight producers configured, zero pending/exhausted events, one broker consumer,
zero queued messages and zero dead letters. Privacy cutoffs were preserved.

Design's forward migration remains pending administrator credentials. The ignored
`.tools/design-startup-upgrade.py` helper prompts without echo, backs up the database,
rehearses upgrade/downgrade/upgrade in an isolated schema, and applies `0009` only
after that succeeds. It verifies schema parity, retained row counts and unchanged
runtime grants. Startup does not migrate or stamp the database automatically.

Manual simplicity/security review checked recovery ordering, strict readiness,
explicit audit contracts, credential handling and preserved historical cutoffs;
no additional finding. `/simplify` and `/security-review` are unavailable in this
session, so those checks were performed directly. Unrelated working-tree changes
were preserved; no commit or publication was performed.

The requested startup repair concerns a healthy API stack with a degraded audit
pipeline. Review found five new Identity event types missing from the consumer's
private allowlist: company setup requested/retried/progressed and report source
discovery/enrollment. Broker identity and signing credentials matched. Roughly
21,000 eligible Identity events were pending; other producer outboxes were clear.

Authorized repair phases:

1. Inventory contracts, pending events and broker state; review retained evidence
   without exposing payloads or credentials. Preserve original message identities,
   privacy cutoffs, retry history and immutable audit records.
2. Synchronize native explicit contracts, reload the affected audit delivery
   processes, and make configured local startup refresh changed contracts before
   launching its consumer/publishers. Improve health messages to identify the
   offending producer. Retain strict failure for real delivery problems.
3. Verify regression tests, drain through normal confirmed delivery, inspect
   consumer/dead-letter health and rerun backend startup/readiness.

An additional diagnostic gap was found: the recovery preflight knew safe discovery
counts for Catalog/Vouchers but omitted Report discovery. Its safe field check
must recognize that same counter for the new explicit event, while continuing to
reject private field values. No model, schema or public API change is required.

## Implementation and review

- Recovery preflight recognizes the Report discovery count under its exact event
  type. Cached source metadata is copied before adding route-specific fields, so
  this exception cannot leak into other Identity events. Private field rejection
  remains covered by regression tests.
- `start-services.ps1` refreshes the configured pipeline through `audit-prepare.ps1`.
  It does not implicitly enable an unconfigured consumer. Existing secrets, broker
  identities and privacy cutoffs are preserved; native contracts remain explicit.
- `runtime/audit-contracts.sha256` records the last completed worker stop for a
  configuration. First use or drift stops configured publishers before the consumer;
  the normal launcher then starts the consumer before publishers. The fingerprint
  is recorded only after all stops succeed, so an interrupted reload retries even
  when the environment file is already updated. Unchanged configurations reuse
  workers. The fingerprint contains no credentials.
- Health detail identifies the offending issuers and stale backlog. Final startup
  errors identify unhealthy components instead of directing an audit-only failure
  toward sign-in or database migrations. Backlog, dead-letter and worker checks
  retain their failure thresholds.

The local preflight reviewed 21,350 eligible Identity events with no invalid payloads
after correcting its discovery-counter vocabulary. Contract synchronization and
normal confirmed publishing resumed delivery. No messages were deleted, marked
published by an operator, or reset wholesale; no historical cutoff was moved.

Verification so far: 15 Python delivery/source-contract tests passed, Ruff passed,
and strict mypy passed for the tool and its two imported domain modules. The Windows
suite passed 22 tests across delivery/startup/provider behavior; the subsequent
fingerprint/interrupted-stop refinement passed both focused lifecycle tests.
The startup fixture now explicitly declares its intended Authentik provider.

Manual security/simplicity review covered explicit source allowlists, safe diagnostic
output, native process ownership checks, retry behavior, unchanged privacy cutoffs,
and the original confirmed-delivery/inbox/chain semantics. `/simplify` and
`/security-review` commands are unavailable here; their equivalent checks were
performed directly.

## Final live result

- `start/win/start-all.ps1` completed with **exit code 0 at 19:00:11**. Every API,
  infrastructure component and Audit delivery reported **UP**. The delivery row
  showed `pending=0; exhausted=0; unconfigured=0; stopped workers=0; broker ready`.
- The subsequent independent broker check also passed: **one consumer, zero queued
  messages, zero dead letters**. Two newly generated Identity events were briefly
  in flight with age zero; the historical backlog was drained.
- Read-only verification found **zero broken tenant chains**. A single-statement
  count check found **125,042 audit rows and 125,042 distinct message IDs**. An earlier
  two-statement diagnostic observed different totals during live ingestion; the
  check was corrected to count rows and distinct IDs in the same database snapshot.
- The new startup refresh path was exercised against the running installation:
  publishers stopped before the consumer, all nine audit workers restarted, and
  unrelated API processes were reused. Existing historical cutoffs were preserved.

No unresolved issue remains in the reviewed startup/audit-delivery paths. No
database schema, business balance, posted transaction or recorded audit payload
was rewritten to resolve this startup failure.

# Voucher ↔ Audit integration review

**Date:** 2026-10-11. **Scope:** existing backend audit trail; no new Audit write API.

## Quick plan and completed work

1. Trace voucher mutations from their transaction-local outbox through the exact-route
   publisher and Audit's authenticated consumer. Check company/actor scope, deduplication,
   retention category, and detail/export projection.
2. Repair the identified contract gaps: include `vouchers.operation.create` in the
   publisher route set; classify voucher lifecycle and execution events as `money` (the
   seven-year default), leaving type/configuration administration as `admin`. An operation
   result may represent artifact work; retaining it for the longer period is intentional
   because the same route also records financial execution.
3. Add regression coverage for producer routes/categories, ingestion by Audit, and current
   field-policy projection of voucher evidence. Extend Identity's signed historical policy
   context and its shared verifier to include voucher entities; run the affected checks.

## Operating contract

Vouchers stages audit rows in the same transaction as the document/configuration/operation
change. The Vouchers Audit publisher signs and confirms each outbox delivery; Audit accepts
only configured issuer, broker user, key and exact event routes, then deduplicates on message
ID and appends to its tenant hash chain. The Audit read API filters `entity_type`, `entity_id`,
`action`, company and category; `audit.read` and `audit.export` govern voucher history and
exports, with current voucher field policies applied to historical `changes`. Free-text
`reason` and unapproved `context` are withheld from voucher detail/export. If a voucher
header event ever aggregates item evidence, an applicable item-field deny withholds the
aggregate `changes` rather than exposing a child value through the parent.

Deployment must configure `VOUCHERS_AUDIT_*` and matching `AUDIT_SOURCE_CREDENTIALS` with
the current `vouchers.events.audit_contract.AUDIT_EVENTS` allowlist. Existing credentials
must be updated before enabling the newly permitted operation-create route. Verify the
publisher's `--status` and `--dead-letters` output plus Audit ingestion after rollout;
HTTP health alone does not prove delivery. Previously stored `admin`/`system` voucher rows
retain their original category and hash; pending historical operation-create outbox rows
also retain their original `admin` payload when delivered. This change affects new events
only.

The present voucher producer records reference-only actions, rather than field-level
before/after snapshots. Detailed voucher revisions and transitions remain in Vouchers;
Audit links to their IDs and records the actor, company, time, action and integrity chain.

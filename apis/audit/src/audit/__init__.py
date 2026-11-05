"""The `audit` service: immutable audit trail, activity feed, and export.

Fed only from the platform outbox event stream (docs/audit.md §2.1) — there is no
write API. The service's database user holds INSERT and SELECT only (§4.1); the
single ingestion consumer assigns the per-tenant ``sequence`` and computes the hash
chain (§4.2), so tamper-evidence and monotonic ordering hold by construction.
"""

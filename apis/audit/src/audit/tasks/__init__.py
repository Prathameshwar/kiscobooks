"""Background tasks for `audit`: the ingestion consumer and the scheduled jobs.

The consumer is the service's single chain writer (docs/audit.md §4.2); the scheduled
jobs provision partitions ahead, drop expired ones, and verify the hash chain (§6).
"""

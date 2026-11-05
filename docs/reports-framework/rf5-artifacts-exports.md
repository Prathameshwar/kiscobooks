# RF5 — private files and independent exports

Status: implementation complete within the revised functional scope. Load/soak acceptance
was removed by the user; historical measurements below are not production capacity approval.
No production admission flag has been enabled. User decisions D02/D03 are unchanged.

The default artifact adapter is a private persistent filesystem folder, configured through
`REPORTS_ARTIFACT_ROOT`. It has no S3/Azure dependency. Provision a directory accessible only
to the Reports service account; POSIX mode is checked, and Windows needs an equivalent ACL.
Multiple hosts require the same durable mount. Atomic hard-link creation without overwrite is
required; an unsupported filesystem fails publication rather than replacing existing bytes.
Windows directory durability and shared-volume guarantees require deployment verification.

Each export has its own durable job, fenced attempt and `report_export_artifact` record
(migration 0031: one CREATE TABLE). The staging record exists before filesystem writes. Byte
hash/count and row count become published evidence in the same transaction as job completion
and audit/outbox emission. A stale, cancelled or revoked worker cannot publish an artifact.
Failures leave the source report complete and available for a separate export attempt.

Completed object bytes are retained indefinitely. Temporary cleanup uses database attempt
ownership and terminal state, never file age alone. A bounded indexed sweep marks temporary
cleanup evidence and emits audit records. It never deletes the objects folder, including
unreferenced finalized files left by a crash between file finalization and DB publication;
these remain available for operator reconciliation. Ordinary successful exports immediately
remove scratch files. Cleanup can later record that no scratch remains.

Run the scoped maintenance command using a configured worker authority scope:

```powershell
python -m reports.tasks.artifact_cleanup --tenant <tenant-uuid> --company <company-uuid>
```

V2 exports are independent of report runs. Current routes create an export from a completed
run, read/cancel/retry its job, issue a short-lived actor/scope-bound token, and stream a
private download. Object access and current permissions are checked before token validation.
Storage paths are not returned. Completed exports remain readable when new admission is off.
Discovery advertises enabled formats only when local dependencies and storage are ready.
HTML/PDF presentation is implemented in RF6.

Both renderers consume one bounded reader over immutable batches or the packaged retained
ledger runtime. Ledger streaming carries account balances between pages. CSV uses UTF-8 BOM,
explicit ISO dates, exact decimal strings, ordered registered columns and spreadsheet-text
escaping. XLSX uses sequential constant-memory writes, disables formula/URL inference, keeps
identifiers as text, splits at 1,048,576 sheet rows including headers, and preserves amounts
beyond 15 significant digits as exact text. Portable text cells are capped at 32,767 characters
with explicit rejection, not truncation. Aggregate export values support DECIMAL(38,4).
RF6 applies the authoritative display configuration and shared visual token bundle.

Evidence as of 2026-10-15:

- API/recovery: 7 passed, including native comparative ledger stream equality, retry keys,
  stale attempt fencing, revocation, cancellation, wrong actor/company/permission downloads,
  immutable publication, tenant isolation and completed-object retention.
- Renderer/storage: 14 passed and one Windows symlink-privilege skip after the aggregate fix;
  includes exact values, formula text, Unicode, leading zeros, forced sheet boundaries,
  overlong cells, quotas, no-overwrite publication and nonrecursive temporary cleanup.
- Native MySQL: 38 passed with migration/model/index parity and downgrade/upgrade verification.
- Full Reports suite before RF6: 312 passed, five environment skips, 93.56% domain coverage.
- Million-row, 20-column CSV after bounded per-export numeric caching: 69.58 seconds,
  72,671,232 B peak RSS and 190,240,176 output bytes. Every row verified; output hash matches
  the initial 243.54-second implementation exactly.
- Million-row XLSX: 379.42 seconds, 73,932,800 B peak RSS and 56,469,051 bytes; all million
  rows/20 million cells verified. The proposed 300-second target remains unmet.
- Ten-million-row CSV: 693.91 seconds, 73,359,360 B peak RSS and 1,902,400,176 bytes;
  every row verified. The completed historical ten-million-row XLSX result, including native
  sheet splits, is recorded in [RF8](rf8-capacity.md).
- These are synthetic renderer/storage measurements under overlapping development load,
  not DB-to-export, mixed-tenant or production SLO acceptance. They predate RF6 workbook
  styling. The later styled result is recorded in RF8; no further capacity runs are in scope.

Upstream implementation constraints were rechecked against the
[XlsxWriter memory contract](https://xlsxwriter.readthedocs.io/working_with_memory.html) and
[workbook options](https://xlsxwriter.readthedocs.io/workbook.html).

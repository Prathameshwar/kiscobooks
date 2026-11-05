# Unit and stock High-finding fixes, 2026-10-31

The four High bugs are fixed: opening binding queries, native dated SKU-unit
admission, exact BIGINT ratio strings, and physical pack-scan refusal before line
mutation. Signed source projections validate date, role, dimensions and both the
master and SKU quantity grids. Missing or stale owner evidence fails closed.

Fixed and measured entered-stock capture now preserves the entered revision and
quantity alongside authoritative base quantity. Measured base quantity is an
explicit observation; nominal weight does not produce executable stock. Catalog
proof is acquired before the writer transaction and Accounting validates it again.
Legacy payloads omit absent evidence, preserving their original wire/digest shape.

Native physical counts support non-serial, company-owned USABLE warehouse/bin/batch
positions. Immutable book-at-cutoff generations, explicit counted zero, versioned
recounts and retained root claims prevent balance overwrite and duplicate variance.
Later movements are reconciled. Verified single FIFO cost or moving average is
automatic; missing/mixed cost needs authorized review with a current pool version.
Native reversal restores movement/value/GL while retaining the old count claim.
Serial counts and damage/disposal remain pending, along with broader B25/B27/C3
release evidence. Existing financial activation and permission controls apply.

Saved [findings](testing/unit-stock-review/findings.csv) distinguish FIXED from
IMPLEMENTED_SCOPED and leave Medium work open. [Cases](testing/unit-stock-review/cases.csv)
include new count, stale UI, replay and schema regressions. The reusable probe
runner now checks the fixed High behavior and labelled still-open Medium diagnostics.

Verification includes 70 affected UI tests, TypeScript, 33 voucher capture/source
regressions, 14 shared protocol tests, 18 count API/audit tests, 12 count domain/effect
tests and the earlier native stock/opening/quantity suites. These native effect
tests use disposable databases and transport doubles; they are separate from live
MySQL schema rehearsal and do not certify broker-backed financial release.

Manual simplification/security review checked exact arithmetic, signed dated
sources, indexed bounded selection, cross-company/tenant scope, nested field
permissions, stale UI cancellation and pending-save guards. It caught and fixed
count JSON persistence, source-independent retained-command replay, stale reviewed
cost and invented surplus receipt age. No additional unresolved High finding was
identified within the implemented contract. Named `/simplify` and `/security-review`
tools were unavailable; the equivalent manual reviews were performed.

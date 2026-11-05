# Tenant admin #9: live report readiness

The user authorized the remaining sequence and short High-complexity plans. This
slice uses the existing Accounting/Identity/Reports contracts and private local
configuration for the retained QA tenant's three companies. It does not activate
money, invoices, statutory issuance or stock execution.

1. **Connections and startup:** configure explicit company-scoped snapshot and fresh
   authority credentials; private artifact storage and the existing broker; provide
   managed source, dispatcher and short/bulk/render worker lifecycle. Keep production
   admission defaults disabled. Verify startup selection and configuration refusal.
2. **Sources:** request generations through the real authenticated UI/API. Accounting
   builds owner snapshots, Reports verifies/publishes READY generations. Verify empty
   source controls and cross-company refusal; record any owner/source prerequisite.
3. **Runs and exports:** use discovered supported definitions and typed parameters;
   verify completed rows, pagination/history, advertised CSV/HTML/XLSX/PDF exports,
   signed download scope/expiry, cancellation and retry where applicable.
4. **Review:** run affected tests and checks, recheck all three companies, record
   current evidence and remaining financial/stock dependencies. Populated financial
   reconciliation follows #12/#13; stock sources follow #15.

Missing sources remain unavailable, not zero. Verified empty snapshots may yield
zero financial totals. Existing immutable source generations and completed jobs
remain unchanged; credentials and private artifacts stay outside committed files.

## Owner generation regression found during live acceptance

The Services source copied all 65 facts with matching counts and controls, then
was quarantined because its snapshot generation differed from the pinned feed head.
`AccountingSetup.generation` is a mutable administration/concurrency counter;
non-source actions can advance it without a new committed report bundle. It must
not define the immutable report-source lineage.

Write owner regressions first for setup-only counter changes and later committed
source changes. Derive report generation from the preceding sealed feed manifest
(initial source generation 1), preserve existing stored receipts, and retain all
Reports generation/schema/scope/permission/control comparisons. Verify owner and
consumer tests, restart affected owner processes, and request a new FRESH generation
through UI/API. Do not rewrite quarantined generations or manually repair source rows.

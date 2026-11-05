# Account opening UI fixes - 2026-10-31

Scope: AO-B01 and AO-B02 from the account opening/ledger review. The four AL-G
ledger gaps remain in the separate ledger backlog.

- [x] Confirm failing regression cases for company date/time display and posting-link failure/pending states.
- [x] AO-B02: distinguish loading, unavailable, explicitly unprepared and native journal states; retain native error/retry handling.
- [x] AO-B01: use shared resolved formatters for evidence/history, document due dates and worksheet summaries; preserve native date input values.
- [x] Run affected opening lifecycle/UI suites and Console TypeScript checks: 137 tests passed; one existing unrelated stock route type error documented.
- [x] Review correctness/security and update the findings CSV, reusable cases and replay checks: two reusable opening acceptance checks passed.

Review follow-up: a field-denied finalization date was reproduced as falsely
"Not finalized" and now has an explicit restricted label. Full Console TypeScript
currently reports an unrelated existing physical-stock route kind mismatch; no
account-opening type errors were reported. Preserve that concurrently modified route.

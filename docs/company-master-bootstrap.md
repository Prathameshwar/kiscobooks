# Company master bootstrap

## Plan

The original implementation/evidence below is historical. The 2026-11-03 v4
extension is recorded in [accounting defaults delivery](company-accounting-defaults-delivery.md).

1. Completed: Accounting reuses chart v3 during company initialization to create five fixed heads, 28 groups and 12 starter accounts atomically. The bounded finance-initialization authority, field policies, current company scope and transactional audit remain enforced. Charts or installations already managed by the company are preserved.
2. Completed: Console shows chart initialization as a setup step, provisions Catalog's existing General product group, Main/transit locations and price levels through authorized owner APIs, and provides management guidance and explicit hand-offs. Existing controls, styles and layouts are reused. Retries skip completed steps and reuse request keys. Successful setup saves selected-company context and opens the company page (or chooser for an actor without company-read authority).
3. Completed: the missing chart was reproduced before the fix. Targeted checks cover atomic rollback, retry, company/tenant isolation, revocation, later edits, UI ordering, conditional authority and failures. Correctness, simplicity and security were reviewed and the findings below fixed.

## Scope and decision, 2026-10-26

The user requested default company masters at creation, followed by normal management. Identity company creation remains its own transaction; service-owned masters are provisioned through the existing retryable company setup sequence. Calling Identity alone creates the company record; Accounting initialization also establishes its chart. There is no cross-service database write or money transaction.

The fixed business chart uses the existing seed catalogue, without inventing balances, journals, bank details, customers, suppliers, tax registrations, tax rates or payment contracts. Tax-specific chart installation still requires a verified registration and existing tax/master permissions. Catalog defaults use its existing General product-group seed and warehouse/pricing bootstrap commands and current tenant-wide grants; unavailable authority produces a named hand-off. Main exists as metadata even when inventory is disabled, as required by the warehouse contract; this enables no stock operations or balances.

Five heads are fixed accounting classifications; groups and accounts use existing management pages and identity/classification safeguards. Existing installations and authored charts are preserved. Schema, stored model and seed version stay unchanged.

## Verification

- Accounting: **59 passed, 1 skipped** across company bootstrap, foundation, masters, groups, template regressions, authorization, financial-year management, legacy metadata, audit evidence/transport and configuration-consumption tests. The skipped existing large-decimal test requires native MySQL; the new seed creates no monetary amounts or balances.
- Catalog: **27 passed**, including native ASGI warehouse bootstrap/replay and pricing foundation, plus General seed checks.
- Console: **148 passed** across wizard, independent bootstrap authority, page guards, request allowlist, company selection/navigation and service calls; TypeScript passed.
- Accounting Ruff, strict mypy and OpenAPI freshness passed. No API shape, model, migration, seed-version, permission-catalogue or role-grant change is required.
- Live read-only schema verification: **109 Accounting tables aligned**, database/Alembic/readiness head **0167**, no missing/extra tables, no native differences, Alembic check exit 0.
- The verified managed Accounting process was reloaded locally and is ready on port 8011. No business company records were created for live testing.
- An exploratory full Accounting run was stopped after locating obsolete initialization assumptions. The affected suites above were then run to completion; this is not a claim that the full Accounting suite passed.

## Review and corrections

1. Missing chart: initialization now shares the transaction-local writer with the existing template command. Conditional/write field denies roll back heads, groups, accounts, bindings, receipts and audit together. Existing installations and authored charts are not upgraded implicitly.
2. Retry: a later Catalog failure previously re-ran completed financial-year/period work. Completed periods and default-master steps are now skipped; failures retain the company ID and stable keys.
3. Navigation: successful setup previously reloaded the new-company wizard. It now saves company context and navigates to the company management page, while retaining Auth step-up handling.
4. Applicability: Main metadata is provisioned even with inventory disabled, as required by the warehouse contract; it enables no movement, stock balance or inventory feature.
5. Compatibility tests: seed counts, audit evidence and legacy fixture setup now reflect automatic business-chart initialization. The status/conditional-policy probes exercise the new chart-writing step and still require transactional denial.

Manual simplification and security review walked CLAUDE.md sections 5 and 6: tenant/company scope, current grants, field policies, origin/token/proxy boundaries, signed company facts, idempotent retries, money isolation and transactional audit. No unresolved findings remain. `/simplify` and `/security-review` slash commands are unavailable in this session; the equivalent review was performed manually.

## Decision log

- 2026-11-03 (approved High-priority defaults): chart v4 supplies 20 accounts in
  28 groups and five heads. Inventory adds five stock accounts and COGS (26 total).
  Applicable registrations/features add tax profiles and supported dated mappings;
  Tax Recoverables is added when required. Discount Allowed uses Indirect Expenses,
  Discount Received uses Indirect Income. Fixed additions share existing scoped
  initialization authority, field policies, transaction locks and audit. Existing
  charts receive missing fixed additions only when initialization is invoked;
  collisions fail for review, and operator mappings and posted facts are preserved.
  Tax registration added after creation requeues the enrolled books step with a
  facts-specific idempotency key. No model or API-shape change is required.

- 2026-11-03: the owner asked that a new company be ready to bill goods and take cash without further setup. The
  books step now also creates the standard stock accounts and their policy when inventory is on, and chart
  initialization gives a chart without any cash account its Cash account in Cash-in-hand. Both only create template
  masters under fixed system keys; neither adopts or changes an authored master, and a taken code skips them rather
  than failing setup. Details: [purchase-product-review](purchase-product-review.md#company-setup-defaults-2026-11-03).

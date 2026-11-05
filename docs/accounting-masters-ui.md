# Accounting master UI delivery

Requested masters: account heads, account groups, ledger accounts, parties,
commercial types, payment terms, withholding sections/rates, exchange rates and
charge policies. Extend the existing company-scoped Accounting screens and shared
design system; preserve independent local navigation and Design changes.

## Phases

1. Audit existing contracts and add failing regressions. Complete native charge
   policy form metadata and exchange quote context/save/review recovery contracts.
   Preserve exact decimal strings, current company/field authority, version checks,
   audit events and the separate exchange-rate reviewer. No speculative datastore
   or financial-posting changes.
2. Implement missing rate/policy directory, creation, details and native actions.
   Improve all eight existing masters: clear explanations and form sections,
   usable filters, permitted related references/actions, accurate empty/error/saved
   messages, and filtered back navigation. Use existing CSS/layout/controls.
3. First review: functional/API integration, validation, permission branches,
   immutable/draft/dated lifecycles, stale responses, pending/uncertain recovery and
   exact numeric handling. Fix findings and run relevant regressions.
4. Second review: real shared styles, desktop/mobile/themes, keyboard menus,
   dropdowns, related links, back/cancel and page entry points. Fix findings, check
   generated clients, types/lint/build, and native readiness without live business
   writes. Record outcomes below.

Account heads remain native read-only chart references. Exchange quotes are
immutable candidates followed by approve/withdraw decisions. Charge policies use
dated creation/closure, not invented editing or activation. Models/migrations must
remain aligned if any data-model change proves necessary.

## Implementation and review outcomes

All ten masters are reachable under Books > Accounting configuration and the
company settings Accounting card. Existing native editors, directories, details,
history and lifecycle actions now share clear descriptions, grouped forms,
permission-derived filters, clear/reset actions and related record navigation.
Account heads remain read-only chart references. Ledger accounts retain the native
draft/profile/activation workflow. Withholding sections link to their dated rates;
heads and groups link to their dependants; payment terms retain instalment setup.

Exchange rates now have a directory, candidate form, exact quote details and
versioned approve/withdraw actions. Company currency choices come from verified
native context. GST goods select Customs evidence. The maker cannot approve their
own candidate. Save and review retries retain the exact request and idempotency
key; reopening an unconfirmed review retains its reason and expected version.

Charge policies use native form metadata, dated creation and explicit end-date
closure. Active party accounts and active base-currency general offsets use
bounded reference controls. No unsupported PATCH, activate, delete or generic
history action is offered. Decimal bounds come from native field constraints;
comparison and submitted values retain exact decimal strings.

Review one fixed missing bridge paths/reference links, inherited filters that
could not be cleared, integer choices submitted as strings, empty-state flicker,
filter-clear duplication and uncertain review dismissal/recovery. Native tests
proved that a repeated quote save/approval retains one identity/version and that
lost current authority cannot replay a decision.

Review two fixed missing local percentage bounds, ineligible charge offsets,
duplicate menu destinations, indistinguishable charge-policy labels and textarea
error styling. Native regressions reproduced missing decimal-bound metadata and
the missing offset filter before the corresponding API/control changes.

## Verification

- 308 Console tests across 12 affected suites passed, including route authority,
  closed bridge forwarding, exact numbers, validation, references and recovery.
- Two browser passes each completed 426 checks across all ten masters at 1440 px
  and 390 px in light, dark and ledger themes. Actual shared providers, shell and
  CSS were used with native-shaped fixtures. No page errors, document overflow or
  business writes occurred. Browser writes against real business data were not run.
- Console TypeScript and production build passed; the managed Console was restored
  and verified UP on port 4320.
- Ruff and strict mypy passed for the seven changed Accounting source files.
  Generated field and financial contracts remain current. Accounting OpenAPI,
  native form fixtures and SDK 0.2.24 were regenerated and checked; SDK tests passed.
- All 43 Accounting service regression tests passed, including quote recovery,
  reviewer separation, field authority, offset eligibility and existing charge
  assessment/history/tax rules. Managed Accounting was reloaded and verified UP
  on port 8011. The running API exposes the new contracts; database/schema
  readiness passes and the unsigned browser bridge rejects requests with 401.

No Accounting data-model or migration change was needed. Existing table/models,
field contracts and financial schema exports were retained. Independent local
navigation and Design edits were preserved. This task has not been committed or
published.

During verification, sign-in failed because the Authentik VM/tunnel was stopped.
After the user started the VM, the managed tunnel was restored and trusted TLS
health, OpenID discovery and an OAuth authorization redirect all passed.

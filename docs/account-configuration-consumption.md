# Account and company configuration consumption

Requested 2026-10-25. Existing Accounting setup, company features, currencies,
registrations, banks and native master policies remain the source of truth.

## Audit and delivery phases

1. **Native form and choice contracts.** Add bounded company-aware hints and
   defaults under existing company/field authority. Restrict new account currency
   and related policy currency choices to enabled company currencies; withholding
   amounts use base currency.
   Filter enabled withholding kinds and compatible reference choices. Preserve
   exact lookup of historical references. Regenerate OpenAPI and the SDK.
2. **Editors and related pages.** Consume those hints in the existing shared
   controls. Apply conditional required fields and clear dependent values only
   after an explicit change, and only when writable. Keep stored values visible.
   Explain disabled features and link to company configuration. Keep existing
   navigation, permission checks and command version/idempotency handling.
3. **Review and verification.** Run regression tests, API/client consistency and
   TypeScript checks, then two focused reviews with fixes. Verify responsive
   layouts and production build using fixture writes only for UI scenarios.

## Confirmed gaps

- Form defaults are static schema defaults rather than company base currency.
- New account currency choices include every ISO currency, including currencies
  that native commands reject for this company.
- Withholding forms offer TDS/TCS even when the matching feature is disabled.
- Account currency, party, rounding and credit-limit dependencies remain enabled
  when irrelevant, causing avoidable validation failures and stale paired values.
- Account bank/tax profile reference search does not filter matching account kind.
- Company bank and registration selectors exist, but their search lists do not
  consume the signed Accounting context's allowed identifiers.
- Conditional selectors can drop the display of a previously stored choice.

## Boundaries

Hints guide authoring; native commands remain the authority. Field permissions
are never expanded. Read-only, active, dated and used records retain their native
restrictions. Preparing credit policies while credit enforcement is disabled is
supported by the existing API; explain this rather than inventing a write gate.
No new account-settings store or database columns are required for these fixes.

## Verification

Implementation and both focused reviews completed. Visual review added a final
message correction: disabled withholding no longer reports a field-permission
problem, and currency notices appear only for readable currency fields.

- Native regression baseline: five expected failures before company-aware hints
  and currency filtering; separate message regression reproduced the misleading
  warning using the native disabled-field shape.
- API review: 22 tests passed across configuration consumption, existing editor
  contracts and Accounting master UI contracts. After the final notice correction,
  all eight consumption tests passed (23 distinct API tests overall).
- UI review: 307 tests passed in 12 files. The final message correction also
  passed all 66 tests in the consumption and existing editor suites.
- Accounting OpenAPI check, generated SDK check, SDK TypeScript, Console
  TypeScript, Ruff and mypy for all three affected task modules passed. SDK is
  0.2.27. Database models and migrations are unchanged: this work consumes
  existing company settings and adds read-contract hints only.
- Browser review uses 16 forms captured from the native API in an isolated
  database and the real shared controls/layout. Desktop 1440 and mobile 390,
  light/dark/ledger themes; 127 checks passed, no browser errors and no live or
  fixture business writes. Screenshots inspected after the final message fixes.
- Review 1 corrected disabled-feature directory actions, tax scheme/component
  dependencies and immediate company-switch data masking.
- Review 2 corrected the return from Company Config to its originating accounting
  page. Protected/conditional fields, historical values, exact decimal strings,
  tenant/company scoping and existing command versions/idempotency were reviewed.
- `/simplify` and `/security-review` are unavailable in this environment; their
  checks were performed manually. No additional authority, money movement or
  audit changes were introduced.

Final production Console build passed and the managed Console is UP on port 4320.
Managed Accounting API was reloaded and `/health/ready` returns
`{"status":"ready"}` on port 8011. Review preview was stopped after verification.
Existing staged and unrelated working changes were preserved; no commit or
publication was performed for this request.

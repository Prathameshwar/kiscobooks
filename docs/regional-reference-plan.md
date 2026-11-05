# Database-backed regional defaults

1. Materialize Identity language and timezone reference tables with one DDL per
   revision, re-runnable installation seeds and active-reference validation.
   Extend the existing bounded tenant/setup choice contracts; preserve access gates.
2. Bind country, currency, timezone and language selectors in tenant creation/editing,
   self-service onboarding and first-run setup. Keep existing shared controls and styles,
   handle unavailable choices and retain selected codes in requests.
3. Run regression suites, regenerate OpenAPI/client contracts, exercise native migration
   downgrade/upgrade and live API/UI checks, apply local installation defaults, then review.

Scope: regional defaults only. Existing companies and posted records keep their values;
credentials, grants, money and unrelated concurrent edits are outside this change.

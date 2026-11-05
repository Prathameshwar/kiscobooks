# Global reference shortcuts in Company settings

1. Reuse existing ActionCard styling and the five protected platform reference
   destinations. Add regression tests for platform, company and absent access.
2. Enable shortcuts only with current global platform configuration authority.
   Everyone else sees no section: no disabled or explanatory cards for company
   readers (amended 2026-10-29, below). Shared references are independent of
   company feature flags and company selection.
3. Run settings/reference UI tests and TypeScript checks; review link destinations,
   expiry/scope checks, responsive cards and unchanged API authorization.

Decision 2026-10-27: Company settings may explain shared references and provide
platform-manager shortcuts. This does not delegate global reference administration
or add company-specific copies, configuration switches or endpoints.

Decision amendment 2026-10-29: the section is shown only to a user who can
manage global references. A tenant administrator or company user with only
company authority no longer sees the five cards as disabled "Platform managed"
placeholders — a control they can never use, on a screen about their own company,
is noise rather than explanation. This supersedes the "disabled cards for company
readers" rule of 2026-10-27. Authority checks are unchanged (effective permission
plus a current tenant/platform grant); no API, permission or backend rule changed.

Implemented and verified: all five cards reuse the shared responsive grid and
existing platform destinations. Active platform configuration authority must be
present in effective permissions and a current tenant/platform grant. Company and
department grants cannot unlock global management. Company readers, and absent,
expired, future or other-company access, do not see the section. Platform
shortcuts work without a company. Timezones correctly offers browsing rather than
an unsupported editor.

Verification: 50 settings/reference tests passed and Console TypeScript checking
passed. The live platform administrator saw all five correct links; Countries and
Timezones opened successfully. Desktop/mobile card layouts passed overflow checks
and the mobile screenshot was inspected. No business writes were made.

Manual simplification/security review found no remaining issue. No backend access
rule, API, company feature configuration, dependency or shared style changed.
Existing unrelated workspace changes were preserved. The named simplify/security
review commands are unavailable in this session; review was performed manually.

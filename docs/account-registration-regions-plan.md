# Account registration regions and tenant details

Requested 2026-10-21: initial Create account must use database-backed regional
selections, default to India, and keep Country and State together. The pending
View tenant request still calls for a full page instead of the directory drawer.

1. Add a deliberately public, bounded Identity country/state reference endpoint
   reusing the active reference-table queries. Connect registration availability
   and server-side selection validation to it. Extend the fixed enrollment fields
   and Authentik blueprint to save country/state as account profile metadata,
   without changing account activation, verification, groups or permissions.
   Add and run API, validation and provider integration regressions.
2. Add Country and State in one shared form row on Create account. Select India
   only when it is active, filter states by country, clear stale selections,
   validate and focus field errors, and provide loading/unavailable/retry states.
   Carry the saved selections through the provider's mapped profile and private
   Auth session into workspace setup as editable defaults; Identity remains the
   authority for validating the actual tenant defaults. Regenerate contracts,
   update documentation and verify unit tests, types, builds and the live flow.
3. Complete the separately requested full tenant details page according to
   tenant-view-page-plan.md, connect directory navigation and review both flows
   across permissions, desktop/mobile layouts, shared CSS and failure states.

No email server is required for this change. Existing manual account approval
and email verification remain in force. No new datastore or Identity account
table is introduced: credentials and unlinked account profile metadata belong
to Authentik; the final workspace region is persisted by Identity as before.

The user's 2026-10-21 instruction to review and ensure the complete account
creation flow is good authorizes completion and verification of registration
phases 1 and 2. The independent tenant view page remains a subsequent task.
Do not publish or alter unrelated local work.

Preparation evidence: the existing 47 Auth UI/session tests, 29 Auth registration
and onboarding server tests, and 12 Identity regional/onboarding API tests passed.
Five prepared UI regressions fail because Country/State controls and choices retry
are absent; two prepared API regressions fail because the public choices endpoint
does not exist (404). Prepared regression sources are kept outside active suites in
the ignored `.tools/local-login/signup-regions-prepared/` folder during preparation.

Registration phases 1 and 2 are complete. See account-registration-verification.md
for unit, provider, browser and independent native MySQL evidence, review findings
and cleanup. The full tenant view page remains governed by tenant-view-page-plan.md.

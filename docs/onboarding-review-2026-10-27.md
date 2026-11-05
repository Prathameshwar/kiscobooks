# Signup, approval and tenant creation review

## Review phases

1. Trace public registration, provider review and platform tenant provisioning;
   run the affected UI and API tests, including retries and denied access.
2. Correct demonstrated defects with regression tests and keep the documented
   experience consistent with optional email and permanent manual sharing.
3. Exercise the running signup → approval → first-login flow and platform tenant
   wizard → administrator-login flow using clearly labeled disposable test accounts.
   Check responsive layout and record verified results and any limitations here.

Existing local changes are preserved. This review does not publish changes.

## Completed review

All three controlled journeys passed against the running Auth, Console, Identity,
MySQL and Authentik installation:

| Journey | Confirmed result |
|---|---|
| Login → Create account → platform approval → sign-in | Signup has no workspace-name input. The new inactive registration appears automatically in Account approvals. Approval completes with Authentik active and email verified, one tenant and its first administrator. The original signup password signs in without another setup or invitation step. |
| Platform tenant wizard → new administrator → sign-in | Three steps create an active tenant and immediately usable administrator. The generated password and copyable access details are available. Replaying the identical command returns the same tenant and does not reveal the password again. |
| Platform tenant wizard → existing administrator → sign-in | An active, verified account with no tenant can be found and explicitly selected. Creation preserves its original password, which successfully signs in. Accounts already linked to a tenant are unavailable. |

The pending-signup Yes/No confirmation was exercised: No retains the entered draft;
Yes opens the matching registration for review instead of creating another tenant.
Both newly approved and platform-created tenant administrators were denied platform
account/tenant directory API access. Copy access link and sign-in details were checked
against the browser clipboard.

## Corrections

- Approval confirmation now describes optional account-ready email and permanent
  manual sharing; it no longer incorrectly promises that no email will be sent.
- Invitation signup explains joining the invited tenant instead of promising a new
  workspace. Ordinary signup still explains automatic workspace creation on approval.
- The tenant wizard uses the standalone shared layout, matching company creation.
  It has one masthead and one viewport scroller; edit and permission-denied pages
  retain the Console shell. Platform breadcrumbs and return links remain available.
- Updated the workspace plan and onboarding status documentation to reflect the
  applied migrations, derived workspace name and immediate provisioning behavior.

Each behavior correction has a regression assertion confirmed failing before the
fix and passing afterward. Manual sharing is tested with both `manual` and `queued`
notification statuses for approval and tenant creation.

## Verification

- 80 Identity tests passed: review domain/API/worker/provider, onboarding,
  registration choices, platform access, administrator provider and notification contract.
- 154 Auth/Console tests passed: 38 Auth UI, 49 Auth server, and 67 Console tests.
- Auth and Console TypeScript checks passed; changed-file whitespace checks passed.
- Browser layout checked in Light, Dark and Ledger themes. The standalone wizard
  fits 1440, 1024, 390 and 320 pixel widths; Next remains visible at both ends of
  the form's scroll range. Desktop/mobile screenshots were inspected.
- One initial UI run hit a five-second timeout under concurrent local load; the
  affected suites passed with bounded workers and a 15-second test timeout.

Local browser scripts and masked screenshots are under the ignored
`.tools/local-login/onboarding-review-current/` directory. `results.json` and
`final-results.json` contain only verification details and test tenant references.
Test passwords were generated in memory and were not saved to those artifacts.

## Security and remaining limits

Manual simplification and CLAUDE.md §§5–6 review found no remaining blocking issue.
The `/simplify` and `/security-review` commands are unavailable in this session;
their checks were performed manually. No API contract, schema, dependency or
permission catalogue changed. Backend authorization, exact provider identity
readback, tenant scoping, idempotency and password-free audit/outbox behavior remain
in place.

A diagnostic request's error output included the dedicated provisioning service
token. That token was rotated in Authentik and the private Identity environment,
Identity was restarted and reached ready, and the replacement credential successfully
provisioned the controlled existing-account fixture. Browser harness errors now omit
request call logs; the configured CA bundle is explicitly trusted. TLS verification
remained enabled. Ordinary user passwords and the platform administrator password
were not changed.

Outbound email is not configured on this installation. Actual mail delivery and
receipt were therefore not exercised; the configured-mail queue path passed automated
tests and manual copying passed against the running UI. Provider-outage recovery and
concurrent decisions were checked by automated tests rather than interrupting the
running provider.

Three clearly labeled review tenants are retained for inspection, with no companies
or financial records created:

- `Review Signup 8c8bf9a346 Workspace` — `01a17c85-2cb1-75fe-b310-84ba31de2a02`.
- `Review platform tenant 8c8bf9a346` — `01a17c85-b969-702e-9eae-9b060cbbeb7f`.
- `Review existing account tenant c11050e7ca` — `01a17c88-a222-70ba-a64b-1e4dd76c9556`.

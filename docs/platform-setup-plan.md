# First-run platform setup

## Agreed delivery scope

1. Identity: add one installation-state table and installation seed; protect setup with an environment-held random key, rate limits and fresh verified OIDC authentication. Provision the operating tenant, first platform administrator, role and audit events atomically. Persist completion and allow safe replay by that administrator only. Existing tenants disable uncompleted bootstrap.
2. Web: implement seven wizard steps in Auth using `@janso/ui`, with server-side connection checks, encrypted HttpOnly setup access, origin checks and no credentials in browser storage. Add shared step navigation and a platform landing page showing the existing tenant-management API. Existing server-side email configuration is optional; configuring email delivery through the browser is deferred until Notification exposes an appropriate secure settings contract.
3. Verification: regression tests for authorization, replay, failures, accessibility and UI transitions; apply the migration locally without resetting data; regenerate Identity OpenAPI/client types; run affected checks, production builds and local browser verification. Review security and correctness after implementation. Never claim the real administrator or complete the real installation using a test identity.

## Wizard steps

Unlock setup → connection checks → platform details → administration workspace →
fresh Authentik sign-in → optional email readiness → review and complete.

The wizard tests configured connections rather than accepting database passwords,
OIDC client secrets or SMTP passwords into browser fields. Country/currency/timezone
are validated by Identity. The administrator email comes from verified provider claims.
The first operator's identity is persisted in installation state and still needs its
live platform permission grant, so restarting Identity requires no operator-env rewrite.

## Completion and recovery

Completion, tenant, user, grant and audit outbox records commit together. Repeating the
same request by its verified original subject returns the original result; another
subject or changed request cannot re-bootstrap. A persistent completion record disables
setup regardless of future user counts. There is no public reset endpoint.

# Company creator access

Extension approved 2026-10-28: company creation now also grants the original
creator the installation-owned Stock Operator role at the exact new company's
scope. This supplies the voucher creation and native stock/accounting recording
dependencies that were absent from the setup-only Company Administrator role.
Approval and period closing remain separate. Both fixed role sets are checked
before either grant, both assignments/security events commit with creation, and
legacy correction preserves revoked/expired/scheduled grants. The existing
ordinary role-assignment escalation guards remain unchanged. Earlier verification
counts below describe the earlier single-role bootstrap, not this extension.

Update 2026-11-01 (Purchase roles, [roles-permissions](roles-permissions.md) decision log): the
creator's Stock Operator role gains `accounting.party.read`, `accounting.tax.read`, `vouchers.artifact.create` and
`vouchers.artifact.read`, so the creator can post an account Purchase (previewing reads tax defaults even
for an untaxed bill), see a supplier's name and print what they record. It
gains no `accounting.credit.read` and no approval key: approving a voucher and closing a period stay
separate, and the creator is **not** given the new `purchase_clerk` role at creation (an administrator
assigns it through the ordinary guards). A poster without `accounting.credit.read` cannot post a bill
against a supplier that has a credit policy, by design: the policy cannot be evaluated without reading
credit data, so the posting fails closed. `purchase_clerk` holds the credit and policy reads. Because
creation compares the installed Company Administrator and Stock Operator grants with the code
catalogue, **apply the role seed (`seeds.roles`) before using company creation again**; until the
installed Stock Operator carries the three new grants, creation answers 409 and rolls back.

Further confirmed 2026-10-28: the Company Administrator role includes the narrow
`opening_balance.initialize_zero` capability. Company readiness offers explicit
zero confirmation only after a native eligibility review. This is first-time
setup only; historical/valued opening entry and correction remain controlled by
the existing financial-controller workflows. It does not widen tenant scope.

Approved decision, 2026-10-27: creating a company grants its creator the fixed
system Company Administrator role at that company's scope. Repair the reported
tenant3/KHE ownership gap with that same bounded role. Tenant-wide business grants
and ordinary role-assignment escalation guards remain unchanged.

1. Add regression coverage for atomic company creation plus fixed company-owner
   assignment/security audit, wrong-tenant rejection, missing system role and
   idempotent repair. Record the bounded bootstrap exception in permission docs.
2. Implement the grant in Identity's company-creation transaction. Fail closed when
   required role setup is unavailable. Keep existing database/API contracts.
3. Apply the approved repair to the exact existing company/creator, with an audit
   record, then reload the service and verify tenant3's live master/report access.
   Check affected tests, API generation, types and schema parity.

## Root cause and permanent changes

Company data was intact. Company creation emitted the company event but did not
create an owner role assignment. A newly provisioned tenant administrator therefore
kept administrative setup authority, including the finance read used by Exchange
rates, while lacking the company business role. The missing step was in the
creation transaction, not a damaged company or a stale database migration.

Identity now grants the fixed active installation-owned `company_admin` role to
the creator, scoped to the exact new company, in the creation transaction. The
grant emits a security outbox record and schedules permission-cache invalidation
only after commit. Missing/inactive system roles fail closed and roll back the
company. The internal helper requires active company ownership and tenant-level
creation authority; repeated corrections reuse the assignment and never restore
revoked, expired or scheduled assignments. No public repair/self-assignment route
was added. Ordinary role creation/assignment guards remain intact.

The wizard plans the new owner's default chart/books, warehouses, price levels,
General product group and optional feature configuration without borrowing another
company's grants. The new owner grant exists before these requests; every service
continues to resolve live authority. Existing retry keys and completed-step reuse
are preserved.

The live check also exposed six omitted Company Administrator seed grants:
read/manage for identifier types, identifier namespaces and sales channels. Their
permission keys and models already existed. The corrected seed adds these to the
same system role; no other role gains write authority. Charge policy operations
remain restricted to the existing accounting roles.

## Existing account correction and verification

For the exact reported account/company, verified active user/company status,
matching tenant and `company.created_by` before applying the approved company-scoped
grant. The same assignment ID was returned on replay, with no extra security event;
the affected user's permission cache was invalidated. The role-seed preview showed
exactly six inserts, no updates/revocations/deactivations, with all 12 roles and
551 existing grants preserved. After apply, all 557 grants are current and the
next dry run is unchanged.

- 130 company creation/configuration tests passed. Nine earlier failures were
  test installations missing seeded system roles; successful creation fixtures now
  install the role catalogue, matching real installation. Missing-role cases
  explicitly verify rollback.
- 32 role-assignment/cache/Catalog/Reports authorization tests passed.
- 37 role catalogue/seed/API/owner tests passed, including nine owner cases also
  present in the 130-test group. Scope isolation, ownership, atomic auditing,
  idempotence, revoked access and ordinary role guards are covered.
- 101 Console bootstrap/wizard/page/Masters/Reports tests passed. Console
  TypeScript, affected Ruff and strict mypy checks passed.
- Native MySQL rehearsal created a company and company-scoped owner assignment,
  observed both audit records, then rolled back and verified all three were absent.
  No test company was retained. Initial rehearsal fixture issues (an overlong test
  code and a count before explicit flush) were corrected before the passing run.
- Identity remains at migration `0087` with 55 model tables and zero schema drift.
  OpenAPI `--check` and generated-client checks passed; no API/schema change or
  migration was required. The managed Identity API was restarted and all twelve
  backend component health checks passed.

An additional seed-integrity regression now verifies both missing and unexpected
Company Administrator permissions abort company creation. The helper compares the
installed role's exact permissions with the fixed code catalogue. All eleven owner
tests passed after this addition; Ruff, strict mypy and OpenAPI checks passed again.

Live sign-in confirmed 42 master cards and the Reports menu/page with 38 cards.
Charge policies remain absent by the accounting role boundary. This verifies
permission visibility, not successful data access for every master: the subsequent
click/API check found a separate deployment blocker. Catalog returns 503
`verified current Identity context is required`. Identity has zero configured
Catalog source credentials; Catalog has no Identity source configuration or company
subscriptions. No current signed source lease can therefore be established.

Manual simplification and security/correctness review found no remaining issue in
the completed owner/seed changes. Full company onboarding remains incomplete until
the Catalog source deployment/enrollment gap is resolved.
The named simplify/security-review commands are unavailable in this session.
Local evidence is under ignored `.tools/company-owner-access/`. Changes are local
and unrelated work is preserved.

## Additional source setup scope: decision requested

The existing source operations contract requires explicit company allowlists and
managed signed snapshot/event delivery. Never replace this with a wildcard scope,
disable the source lease, or treat a user role as service credentials.

Requested decision: implement automatic, company-scoped enrollment and managed
source workers, or retain explicit deployment-managed source setup. Automatic setup
needs an Identity-owned enrollment record committed with company creation, bounded
signed service discovery for enrolled companies, matching Catalog worker support,
private service credential preparation and launcher lifecycle support. Verify queue
capture, snapshot activation/renewal, scope/revocation and a full new-company flow
before claiming onboarding complete. No automatic enrollment changes have been
made while this decision is pending.

## Fresh tenant3 company verification (2026-10-27)

The Business overview notice is the page's explicit missing-report.read branch.
A fresh tenant3 OIDC login could not reproduce that denial on KHE: Identity
returned company-scoped report.read and the overview rendered. The page now keeps
its title, names the open company and explains how to request the missing access;
it no longer tells a user with a company already open to choose a workspace.
Authorization remains unchanged.

Created one real test company through all six wizard steps as tenant3:
`TENANT3-U8ZS`, ID `01a17cd2-a307-7222-91f0-b060cdc97c88`, display name
`Tenant3 verification 2026-10-27T10-05-40-580Z`. Company creation returned 201;
feature enablement, default chart, financial setup, year generation and opening
the books-begin period returned 200. Warehouse bootstrap then returned 503,
`verified current Identity context is required`. Pricing, General product group
and the wizard's final automatic company opening therefore remain pending.
This is the previously recorded Catalog source deployment gap, not a missing
creator role. No second company was created by the test.

A second clean tenant3 OIDC login verified the new company has company-scoped
report.read, one financial year and a successful company-context switch (200).
Its Business overview opens without the access notice; Masters shows 42 cards,
Reports shows 38 and the browser recorded no runtime errors. KHE retained its
company-scoped report access. The test company remains available for inspection.

The overview data loader still returns demonstration values rather than calling
Reports. A visible sample-data notice now states this, preventing a new company's
preview totals from being mistaken for transactions. Live overview integration
and the Catalog source configuration remain incomplete; this verification does
not claim full company setup success.

Also reproduced and fixed a wizard regression: reselecting the already selected
country cleared the state choices, but its unchanged effect dependency prevented
a reload. Selecting the same country is now a no-op and preserves the chosen
state. Both regressions were tested failing before their fixes. All 73 affected
wizard/page/dashboard tests and Console TypeScript passed. The final browser
check passed same-country selection, new-company overview access, visible sample
labelling and no overflow at 1440/390 px. Evidence is in ignored
`.tools/business-overview-review/`.

Manual simplification and CLAUDE sections 5/6 review found no new issues: no
authority expansion, service credential changes, transaction or money changes.
The named simplify/security-review commands are unavailable in this session.

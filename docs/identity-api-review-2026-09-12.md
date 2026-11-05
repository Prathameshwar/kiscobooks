# Identity API review — 2026-09-12

**Follow-up:** The authorized bug fixes and subsequent review are tracked in
[the implementation results](identity-bug-fix-results-2026-09-12.md). The findings below
remain the preserved pre-fix review.

The Identity API is not ready for production use without closing the authorization,
relationship-isolation and audit findings below. This review found **15 bug findings,
8 implementation gaps and 2 additional concurrency concerns**. Several related
reproductions are grouped under one finding rather than counted separately.

The proposed follow-up work is split into the [bug-fix plan](identity-bug-fix-plan.md)
and the [implementation-gap plan](identity-gap-completion-plan.md). Their creation
does not change the findings or mark any implementation complete.

## Scope and evidence

Reviewed the 56 OpenAPI operations (28 GET, 22 POST, 6 PATCH), their request and
response schemas, authorization, organization and user lifecycle code, relevant
models/migrations, audit emission, Catalog source integration, and the governing
organization, company, field-policy and API-convention documents. Four operations
are internal Catalog snapshot/authorization operations. Health endpoints are outside
the OpenAPI count.

Verification performed:

| Check | Result |
| --- | --- |
| Identity suite, excluding MySQL-marked tests | **931 passed, 5 deselected**, 297.45 seconds |
| Statement/branch coverage | **91.76%**, above the configured 90% package gate |
| Ruff, `src tests` | Passed |
| Strict mypy, `src` | Passed, 79 source files |
| `tools/export_openapi.py --check` | Passed |
| Targeted reproduction harness | **28/28 observed behaviors reproduced** |

The reproduction harness uses an isolated in-memory SQLite database with foreign
keys enabled, the actual FastAPI routes and test-signed actor contexts. These
contexts represent the stated granted permissions; the review does not claim HMAC
forgery. The group escalation check also calls Identity's actual Catalog permission
resolver before and after the HTTP request.

The harness asserts the current undesired behavior to preserve evidence. Its passing
result does **not** mean those behaviors are correct. Convert the checks into
regression tests asserting the corrected behavior when fixing them.

Evidence: [reproduction script](../.test_artifacts/identity-review-20260912/reproduce.py),
[observations](../.test_artifacts/identity-review-20260912/reproduction-results.json),
[coverage](../.test_artifacts/identity-review-20260912/coverage.json).

No production code, live application data or migrations were changed. MySQL,
RabbitMQ and Authentik were not exercised against live services during this review.

## Confirmed bugs

### B01 — P1: Group membership bypasses the privilege-escalation guards

**Source:** `apis/identity/src/identity/api/org.py:296`; compare
`apis/identity/src/identity/domain/authorization.py:125` and
`apis/identity/src/identity/tasks/catalog_authorizations.py:71`.

`POST /v1/user-groups/{group_id}/members` only requires `group.manage` at tenant
scope. It neither prevents adding oneself nor checks the permissions the target
group conveys. With an existing privileged group assignment, an actor who only has
`group.manage` can add themselves to that group.

**Reproduced:** membership creation returned 201, and the actual permission resolver
changed the actor's effective permissions from empty to `unit.manage`. No
`role.assign` or `unit.manage` grant was supplied to the mutation.

**Impact:** a group administrator can acquire privileges they cannot directly assign,
or grant them to another user. The prerequisite is an existing group role assignment;
the public API currently refuses new group assignments, but the model and resolver
already support and honor existing ones.

**Fix direction:** treat access-bearing membership changes as authorization changes.
Resolve the group's active assignments and enforce permission, scope and
self-modification rules transactionally before adding/removing membership.

### B02 — P1: Related IDs can cross tenant/company boundaries

**Sources:** `api/users.py:173`, `api/org.py:169`,
`api/company_statutory.py:131` and `:218`, `api/roles.py:88`, all under
`apis/identity/src/identity/`.

The session filter protects fetched rows; it does not validate foreign-key values
copied from a request. Several paths omit the necessary ownership lookup:

| Request | Reproduced result |
| --- | --- |
| PATCH a user with another tenant's `default_company_id` and `default_department_id` | 200; both foreign IDs persisted and returned |
| PATCH a department with another tenant's `head_user_id` | 200; foreign user ID persisted and returned |
| POST a tax registration with another tenant's `registered_address_id` | 201; foreign address ID persisted and returned |
| POST a company-scoped role assignment naming another tenant's company | 201 |

The registration amendment path also assigns `registered_address_id` without
ownership validation. Default departments additionally need to belong to the
selected default company. Company-scope assignment targets are not loaded at all,
so nonexistent company IDs also lack an existence check.

**Impact:** inconsistent cross-tenant relationships and downstream scope confusion.
This is demonstrated relationship corruption; it is not a claim that a normal
company GET bypasses its tenant filter.

**Fix direction:** resolve every referenced object under the current tenant, check
the required company relationship and lifecycle, and add composite constraints
where feasible as a second line of protection.

### B03 — P1: Role endpoints omit scope/validity authorization

**Sources:** `api/roles.py:207`, `:484`, `:538`; `api/auth.py:66`.

`update_role` invokes the tenant-scope composition guard only when `permissions` is
present. Name/description/scope-hint updates use only `current.require`, whose
permission union checks `is_active` but not the grant's validity dates.

**Reproduced:** a company-scoped `role.manage` grant edited a tenant role with 200;
a grant that expired in 2000 also edited it with 200. A company-scoped `role.read`
grant listed tenant-wide assignments. Repeating revoke on an already inactive
tenant assignment returned its details with 200 to an actor holding `role.assign`
only for one company because the early return precedes scope validation.

**Impact:** unauthorized role metadata changes and disclosure of assignments outside
the actor's scope; expired grants remain effective on these routes.

**Fix direction:** apply scope and validity checks on every branch, including no-op
and replay branches; scope-filter assignment lists. Keep the endpoint permission
union temporally valid as well.

### B04 — P1: Stored field policies do not restrict reads or writes

**Sources:** `api/companies.py:277`, `api/users.py:160`,
`api/companies.py:413`; `apis/identity/BUILD_TODO.md:30`.

The field-policy mechanism exists, but Identity's routes do not resolve or apply it.
This is acknowledged as deferred in the build tracker.

**Reproduced:** an explicit user-specific write deny on
`identity.company.display_name` did not prevent PATCH; an explicit read deny on
`signatory_name` did not remove the value from GET. Both returned 200.

**Impact:** endpoint access grants access to fields that configured policy denies.
The same missing integration leaves read-sensitive search/sort/projection checks
unprotected.

**Fix direction:** resolve policies for the actor and object; apply write policies to
the changed-field set and read policies before serialization and query construction.
Do not present stored policies as effective until that integration exists.

### B05 — P1: Required audit records are absent

**Sources:** `api/org.py:169`, `:254`, `:368`; `api/users.py:296`;
`api/company_statutory.py:163`.

Department updates, group creation, membership creation and external-identity linking
write data without staging an audit event. Catalog source-change events generated by
flush hooks are replication facts, not replacement audit records.

**Reproduced:** all four mutations succeeded (200/201), with zero additional audit
payloads in the outbox. Reading tax registrations also emitted no audit record,
despite the explicit sensitive-read requirement in `docs/audit.md` section 5.3.

**Impact:** organizational changes and login-identity binding changes cannot be
reconstructed from the required audit trail.

**Fix direction:** add transactional audit emission to each missing mutation;
classify identity binding as a security event and sensitive reads as access events.

### B06 — P1: User audit payloads persist personal data

**Source:** `api/users.py:179`; also review `api/tenants.py:71`.

`update_user` copies every changed field's old and new value into the audit payload,
including names and phone numbers. The tenant update path similarly includes
`primary_contact_email` in unrestricted changes.

**Reproduced:** changing a user's first name and phone stored the full submitted
values in `user.updated` outbox payloads.

**Impact:** anonymizing the user row does not remove their personal data from audit
history. This contradicts the repository's explicit PII-free audit design.

**Fix direction:** use an allowlist of audit-safe business values; record identifiers
and changed-field names or redacted markers for personal fields. Review existing
stored events before enabling delivery to the immutable audit store.

### B07 — P2: Company audit events lack company scope

**Sources:** `api/companies.py:326`, `api/company_statutory.py:147`;
`apis/audit/src/audit/domain/ingest.py:81`, `apis/audit/src/audit/api/routes.py:85`.

Identity's company audit payload calls omit the supported `company_id` argument.
The Audit consumer takes company scope from that payload; it does not infer it from
the aggregate or entity ID.

**Reproduced:** every company audit event produced by the harness lacked
`company_id`. Code tracing shows these become null company scope at ingestion.

**Impact:** company-filtered audit/activity queries miss the events; company-scoped
readers cannot access them through the intended scope.

**Fix direction:** include authoritative company scope in every company-owned event,
and department scope where supported. Verify ingestion and scoped listing together.

### B08 — P2: A revoked role assignment cannot be granted again

**Sources:** `api/roles.py:414`, `:484`;
`models/role_assignment.py:72`.

Revocation preserves the row and marks it inactive. Creation always inserts another
row, while the unique key covers subject, role and scope regardless of activity.
There is no reactivation endpoint.

**Reproduced:** grant → revoke → grant the same role/scope returned 201 → 200 → 409.

**Impact:** normal access restoration is impossible through the API.

**Fix direction:** implement an explicitly authorized and audited re-grant transition,
or a history model whose uniqueness permits distinct grant periods.

### B09 — P2: Assignment validity windows are not validated

**Sources:** `schemas/role.py:80`, `api/roles.py:456`.

`valid_from` and `valid_to` are copied without an ordering check.

**Reproduced:** `valid_from=2026-09-12`, `valid_to=2026-01-01` returned 201.

**Impact:** the API reports successful access assignment for a grant that can never
be in force.

**Fix direction:** validate the merged/defaulted window before inserting. Include
null/default start dates and boundary-date cases in regression coverage.

### B10 — P2: Duplicate memberships and multiple primary affiliations are accepted

**Sources:** `api/org.py:368`, `models/membership.py:30` and `:50`.

Company-level membership uses null `department_id` in a unique constraint. There is
no application duplicate check, and the documented one-primary-per-user rule is
not enforced.

**Reproduced:** two identical company-level memberships plus a membership in another
company were all created with 201; the user had three active primary memberships.

**Impact:** ambiguous default company selection, duplicate affiliation records and
no API transition to cleanly end an affiliation.

**Fix direction:** serialize membership changes per user, enforce uniqueness for
the company-level null case and maintain a single primary explicitly.

### B11 — P2: Cursors are not bound to their query or authority

**Source:** `api/listing.py:28` and `:64`.

The shared codec supports secure context binding, but Identity passes only a static
resource string such as `companies`. Sort, filters, tenant, company and actor scope
are omitted. The decoded dictionary is then indexed using the new request's sort.

**Reproduced:** a cursor created with `sort=code` caused 500 when reused with
`sort=display_name`. Changing search or tenant while retaining the cursor returned
200 instead of the required 422.

**Impact:** client-triggered server errors and invalid page boundaries. Tenant
filtering still applies; cross-tenant cursor acceptance is not evidence of foreign
row disclosure.

**Fix direction:** bind normalized query and current authority to the cursor context;
validate the decoded sort/value schema before applying it.

### B12 — P2: Department-scoped managers cannot manage their own department

**Source:** `api/org.py:169`; related scope construction in `api/roles.py:113` and
`libs/platform/src/billing_platform/authz.py:108`.

Department updates authorize against `ScopePath(company_id=...)` without the target
department. A grant scoped to that department therefore cannot match.

**Reproduced:** a manager with `department.manage` for the exact target department
received 403 on a simple name change.

**Impact:** department-level delegation is unusable for its own management routes.
The general `ScopePath` also represents only one department, so parent-department
inheritance needs explicit integration with the materialized ancestor path.

**Fix direction:** authorize the actual target department and its ancestry; scope
department listings and distinguish parent-authorized creation/reparent operations.

### B13 — P2: Growing lists are unbounded and load full entities

**Sources:** `api/org.py:282`, `:347`, `:405`; list implementations in
`api/company_statutory.py`; `api/users.py:208` and `api/companies.py:351`.

Groups, group members, memberships and statutory child lists return `.all()` without
bounded pagination. Other paginated lists select full ORM entities before reducing
them to list schemas, loading detail-only data unnecessarily.

**Reproduced:** `GET /v1/user-groups?limit=1` returned all 203 groups.

**Impact:** growing tenant datasets can create large database reads, memory use and
responses. This violates the agreed maximum-page and lean-projection rules.

**Fix direction:** use bounded keyset lists and explicit list columns; document real
bounds for any collection intentionally returned whole.

### B14 — P2: Query and validation behavior violates the common API contract

**Sources:** `api/companies.py:341`, `schemas/user.py:53`, `main.py:73`.

Unknown query fields are ignored. Required-but-omittable PATCH fields also accept
explicit null. Only PlatformError and IntegrityError get the shared envelope;
FastAPI request validation retains its default response shape.

**Reproduced:** `?statuz=inactive` returned an unfiltered 200 response;
`PATCH user {"first_name":null}` returned a misleading 409 database conflict;
`?limit=201` returned `{"detail":...}` instead of the common error envelope.

**Impact:** filter typos silently change results and clients cannot handle errors
uniformly.

**Fix direction:** forbid unknown query parameters, distinguish omitted fields from
explicit null and normalize request-validation errors to the shared envelope.

### B15 — P2: Saved user preferences cannot be read back

**Sources:** `schemas/user.py:72`, `:90`; `api/companies.py:401`.

`UserUpdate` accepts theme, date/datetime formats, digit grouping, currency display
and landing page. `UserDetail` omits them, and the company display-config endpoint
returns only company configuration.

**Reproduced:** setting theme to `dark`, date format and landing page returned 200;
the database stored the theme, but GET user omitted all three fields.

**Impact:** a real client cannot restore persisted preferences on reload using the
documented read API.

**Fix direction:** expose authorized preference reads or a resolved current-user
session/preferences endpoint, and apply the documented company/user merge.

## Implementation gaps

These are incomplete capabilities, not claims that an existing implementation was
exploited. Some are explicitly deferred in the build tracker.

| ID | Gap and consequence | Evidence / completion needed |
| --- | --- | --- |
| G01 | Production authentication and invitation lifecycle are incomplete. Invite creates an `invited` database row, but no invitation delivery/acceptance, Authentik subject binding, user activation, general session resolver or gateway JWT-to-actor flow was found in the repository. | `api/auth.py`, `api/users.py:58`, `mfes/apps/auth/app/lib/demo-auth.ts:1`, `mfes/apps/console/app/session.ts:1`. The UI still uses demo/fixture identity. Verify provider ownership before enabling `link_identity`, which currently accepts caller-supplied provider subjects under `user.update`; account takeover through a real login was not tested. |
| G02 | Organization lifecycle management is incomplete. New group role assignments are still explicitly rejected; group member removal, affiliation end/primary change, and company/department/group/role deactivation are absent from the route inventory. | `api/roles.py:417`, `api/org.py`, `main.py:63`. The existing group-assignment request returned 422 even though groups and the resolver exist. Add authorized, audited lifecycle actions. |
| G03 | Company contacts, bank accounts, documents, user notification preferences and API tokens have models/migrations but no corresponding HTTP management routes. | `apis/identity/BUILD_TODO.md:28` and `:42`, confirmed against registered routers. Complete their contracts, sensitive reads, token hashing/revocation and document access flows. |
| G04 | Custom-field definitions, values/index maintenance, field configuration and field-policy administration are not exposed through Identity's API. Field-set returns the native company registry only. | `api/companies.py:413`, `BUILD_TODO.md:30`. Runtime tenant customization and policy management cannot be completed through the API. B04 separately covers enforcement of policies already stored. |
| G05 | Step-up and impersonation are not connected to request authorization. Identity exposes `requires_step_up` but has no fresh-authentication claim checks, and impersonation has no start/end routes or actor-context propagation. | `api/companies.py:604`, `api/auth.py:54`, `domain/impersonation.py`, `BUILD_TODO.md:29`. Reproduced 200 on normal company GET after setting `requires_step_up=true`. No deployed external gateway was available to establish an upstream control. |
| G06 | First-posting and feature-use locks have no production event integration. The guards work when fields are populated, but no producer/consumer path sets `first_posted_at` or applies `plan_lock` on dependent activity. | `api/companies.py:237`, `domain/company_features.py:131`; production-source search. Billing is not implemented yet, so treat this as a required integration gate before posted data exists. Define the race-safe cross-service ownership protocol. |
| G07 | Identity audit delivery is incomplete. Audit records are staged, but the only Identity publisher entry point publishes `identity.catalog_context.changed` to Catalog. | `tasks/catalog_publisher.py:15`. No Identity audit publisher wiring or live delivery verification was found. Add the audit event allowlist, signing/routing, retries and delivery monitoring; staging alone does not prove an Audit row exists. |
| G08 | Production-database and integration release evidence remains incomplete in this review. Existing tests pass, but they miss the reproduced authorization and contract cases. | Five MySQL-marked tests were excluded; live migration roundtrip, collation/constraint behavior, concurrency and broker/IdP integration were not run here. Add the regression cases and execute production-equivalent integration gates. |

## Additional concurrency concerns requiring MySQL verification

These are supported by code inspection and a concrete interleaving, but were not
reproduced against concurrent production-database transactions. They are not included
in the 15 confirmed bug count.

1. **Feature dependency race.** `api/companies.py:485` and `:556` read company/features
   without locking before planning. Starting with inventory enabled and batch
   tracking disabled, one request can validate disabling inventory while another
   validates enabling batch tracking using the old inventory state. Both can commit,
   leaving batch tracking on and inventory off. The Catalog generation lock is taken
   in `events/catalog_source.py:196` at flush time, after those policy reads, and does
   not revalidate the plan. Lock before reading the feature state and recheck under
   that lock.
2. **Department reparent race.** `api/org.py:191` validates ancestry and rewrites
   subtrees without locking the tree or requiring a version. Concurrent requests
   moving A under B and B under A can both validate against the original roots and
   persist a cyclic/inconsistent structure. Serialize tree changes per company or
   use a proven ordered-lock/version protocol and test the conflicting interleaving.

## Recommended repair order

1. Close B01–B04 first: authorization, ownership validation and field-policy
   enforcement. Fix the group-assignment lifecycle alongside its escalation guards.
2. Repair B05–B07 and connect audit delivery before relying on the audit trail.
3. Repair access restoration, memberships, department scope, pagination, validation
   and preferences (B08–B15); add regression tests for each reproduced case.
4. Complete production authentication/lifecycle and explicitly deferred APIs; verify
   MySQL concurrency, migrations, event delivery and first-posting locks before release.

The existing test suite provides useful coverage of ordinary tenant-filtered reads,
system-role immutability, company posting guards, jurisdiction validation and the
internal Catalog signature/scope contract. Its green result should be preserved,
with the missing adversarial cases added.

The build tracker is stale in places: it reports approximately 76% coverage and a
missing generated client, whereas this review measured 91.76%, found
`clients/api-client/src/identity.d.ts`, and passed the OpenAPI freshness check.
Those stale statements were not used as current findings.

## Reproduction commands

Run from `apis/identity`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not mysql" --cov=identity --cov-report=term --cov-report=json:../../.test_artifacts/identity-review-20260912/coverage.json
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe tools\export_openapi.py --check
.\.venv\Scripts\python.exe -u ..\..\.test_artifacts\identity-review-20260912\reproduce.py
```

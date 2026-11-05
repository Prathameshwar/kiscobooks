# Company-only Product configuration review

Decision and implementation: 2026-10-30. The requested owner is Company only.
The flow is company overview → create/edit configuration → save → review → publish.
Scope creation and type/group/family/SKU selectors have been removed from the
console. The existing form, shared styles, field controls and publication review
are reused. Company product structure remains an independent company setting.

## Implementation and cleanup

- `POST /product-configurations/company` accepts configuration values without an
  owner selector. It creates/reuses the unique company scope and saves the draft
  atomically, with native field authorization, audit and idempotent retry.
- New scope input accepts COMPANY only. Retired ownership fields/filters and
  unrevisioned type/group/family option endpoints are removed. The compatibility
  company-scope draft route rejects all retired scope IDs.
- Draft updates, preview and publication reject retired owners. The console
  presents retired detail/history as read-only and hides mutation controls.
- Current/default inspection and proposed adoption use Company revisions only.
  Optional type profile defaults are fallbacks to explicit company choices.
  Native product context still validates goods/service, type, units and groups;
  the context IDs are product inputs, not configuration ownership selectors.
- Previously published configuration and existing product adoption sources retain
  their immutable history. Only internal historical pin resolution reads retired
  layers, with the original profile ordering. No active product is rewritten.
- Generated Catalog OpenAPI/client and governing guides describe the new route
  and retired authoring contract. The subsequent consumer review adds migration
  0214 and an adoption resolution version; apply it before the matching API.

## Review findings and fixes

| Finding | Resolution |
|---|---|
| Five levels and a separate owner-creation step complicated configuration | Company overview and direct native company-draft command |
| Legacy scope writes/current inheritance remained available | Server rejection, company-only listing/current resolution and read-only history |
| Optional type profile defaults could replace company choices | Native baseline precedes Company choices for current/new settings; historical pin ordering retained |
| Lean list responses omit `company_id`, so a detail validator would reject valid summaries | Validate native list IDs/owner or parent scope; verify company on detail responses |
| Identifier-profile lookup was intercepted by the units namespace rule | Evaluate the closed configuration policy before resource-name policies; cover all nine supported option sources |
| Retired owner filters persisted in return navigation | Remove those parameters while retaining safe settings/master destinations |
| Existing test seeded a Company revision at the same publication date | Exercise a later date and preserve the native monotonic-date constraint |
| Full source typecheck found an existing `Any` return in the shared definition entity name | Format the native table name as a string; wrap its existing overlong authorization call |

Manual simplification and security review covered CLAUDE.md sections 5 and 6;
`/simplify` and `/security-review` are not available as tools in this session.
Reviewed company/tenant object admission, strict inputs, closed proxy routing,
field-deny ordering, rollback/audit, source/version guards and exact decimal
behavior. Configuration publication does not post money or mutate tax, stock,
prices, grants, company capabilities or historical product definitions.

The initial review found no remaining issue in the covered authoring flow.
The subsequent end-to-end consumer review identified and corrected adoption
precedence, configured-type publication validation and preview-version
verification gaps; see the [latest report](company-product-configuration-consumer-review.md).
The browser preview initially lacked the document's `janso-root` reset;
it was corrected to match the console body and stylesheet imports. This was a fixture setup
issue and did not require an application CSS change.

## Verification and reuse

Fail-first artifacts reproduce the missing company route, four valid old scope
inputs, three simplified UI expectations and the optional type precedence bug.
Tests cover first/repeated company drafts, publication, retired scopes/pins,
defaults, adoption, native restrictions, imports, authorization and rollback.
The dedicated MySQL schema verifies concurrent first drafts create one scope.

Final counts and cases are recorded in
[the reusable CSV](company-only-product-configuration-results-2026-10-30.csv).
75 distinct native cases and one MySQL concurrency case passed; 228 UI cases and
42 browser checks passed. The initial native batch passed 73/74; the reviewed
18-case batch fixed the remaining date fixture and added field-deny/replay checks.
The initial UI batch passed 161/162; the final suite includes the corrected return
link and proxy routing plus additional company, consumer and policy coverage.
Ruff, strict mypy on 354 Catalog source files, console TypeScript and generated
Catalog OpenAPI/client freshness checks passed.
Evidence is under `.test_artifacts/company-product-configuration-*`, including
native pytest logs, Vitest JSON, static/contract results and browser screenshots.

Browser checks run the actual changed React components and shared CSS at 1440px
and 390px in light, dark and ledger themes, with fixture BFF responses. Native
API tests separately use signed policy sources and isolated databases. The
browser exercise makes no application database writes and is not a live tenant
login test. Live login/publication against the combined VM is not run because
the user shut down the VM; deployment and that live check remain separate.

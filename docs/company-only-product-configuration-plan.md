# Company-only Product configuration

Decision 2026-10-30: the user requested company-level Product configuration only,
permanent retirement of other configuration scopes, a direct create/publish flow,
cleanup and final review. This supersedes the configuration inheritance hierarchy
in catalog-product-configuration.md; it does not remove product masters or the
independent tax, price, operational and native type/unit requirements.

## Delivery phases

1. Add fail-first checks for company-only scope authoring and current resolution.
   Add a native company-draft command that binds the company internally, creates
   its singleton scope when needed and retains ordinary validation, permissions,
   atomic audit and idempotent replay. Reject non-company draft editing/publication;
   keep retired sources out of proposed adoption and list only company configuration.
2. Replace the scope directory/picker with the company configuration page. Create
   and resume drafts directly, reuse the existing configuration form and reviewed
   publication, remove scope/owner selectors and obsolete create UI. Inspect and
   adopt current company settings without manually selecting scope revisions.
3. Update native consumers, field controls, proxy policy, OpenAPI/client, fixtures
   and governing decisions. Preserve historical pinned revisions and structural
   product obligations; no active product is silently rewritten or weakened.
4. Run affected native and UI regression suites, type/static checks, review
   simplification and CLAUDE.md sections 5/6, fix findings and record reusable CSV.

## Todo

- [x] Trace the current five-level authoring/resolution flow and publication guards.
- [x] Company-only native command, rejection rules and regression tests.
- [x] Company configuration UI, direct create/edit/review/publish and cleanup.
- [x] Historical pins, adoption/authoring consumers and generated contracts.
- [x] Verification, final review/fixes and CSV.

Results: 75 distinct native regression cases, one dedicated MySQL concurrency
case, 228 UI cases and 42 browser checks passed after review fixes. Ruff, strict
mypy across 354 Catalog source files, console TypeScript and OpenAPI/client
freshness checks passed. The reusable CSV and [review](company-only-product-configuration-review.md)
record the separate live-VM check as not run.

Retired scope records may remain solely as immutable provenance referenced by
saved product adoptions and published history. Public current-default resolution
must not inherit them. Historical resolution is internal and must not authorize a
new adoption of retired configuration. No direct application-table manipulation
or silent republishing is part of the rollout.

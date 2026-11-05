# Platform administration and tenant form pages

User request: replace the tenant create/edit drawers with proper pages, retaining
shared CSS, clear messages and validation. Additional request: add Edit platform
details and a disabled Fees and pricing card to `/platform`, with reusable shared
gradient card styling and appropriate icons. All three phases agreed by the user.

1. Add guarded platform-detail read/update endpoints using existing installation
   name/public URL columns, live platform authority and fresh authentication for
   changes. Validate metadata, keep bootstrap/operator fields immutable, lock the
   control row and emit transactional audit records. Synchronize the audit contract
   and generated OpenAPI/client types. Add a protected platform-details editor and
   a shared action-card component with token-based gradients, icons, accessible
   navigation and disabled presentation. Compose tenant/details/pricing cards on
   `/platform`; pricing remains a UI-only disabled card. Run affected tests.
2. Add protected `/platform/tenants/new` and `/platform/tenants/{id}/edit` pages
   with one tenant form. Reuse PageHeader, SectionHeader, Card, CardBody, CardFooter,
   TextField, Select, Notice and the shared responsive form grid. Group workspace,
   administrator/contact and regional defaults. Preserve editable suggested IDs,
   immutable IDs after creation, database/API choices, and native/server validation.
   Include loading, missing/closed tenant, permission, pending and retry states.
   Keep idempotency stable for unchanged creation retries. Show saved confirmation
   and administrator invitation handoff without treating invitation lookup failure
   as failed creation. Preserve the draft during explicit fresh authentication.
   Complete form/route regression tests before connecting the directory.
3. Make New tenant and Edit details navigate to their dedicated pages. Retain
   read-only details/invitation drawers and lifecycle confirmation. Preserve list
   search/filter/cursor state when returning. Remove obsolete drawer form logic.
   Verify component, route and BFF regression tests, TypeScript, production build,
   desktop/mobile browser flows and native API/database integration where available.
   Finish manual simplification/security review and update the implementation guide
   and verification record with exact coverage and limitations.

Existing Identity endpoints already provide tenant provisioning, detail/update,
regional choices, lifecycle and invitation handoff. Platform metadata has existing
database columns but needs read/update endpoints. This task does not require a new
database schema, permission catalogue, migration, or provider credential flow.

Completed all phases. See [verification](platform-pages-verification.md) for checks,
review findings corrected, local database/browser evidence and deployment limits.

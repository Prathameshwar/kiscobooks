# Tenant details page

Request: replace View tenant's drawer with a properly designed page using shared
components and CSS. User reiterated the request on 2026-10-21; phase agreement pending.

1. Add a protected `/platform/tenants/{tenantId}` view using the existing detail
   API. Present workspace name/status, contact, regional defaults, dates and
   suspension information in shared cards and a reusable detail layout. Handle
   loading, missing tenant, denied access, session recovery and retry states.
   Resolve regional labels from existing choices while retaining stored codes if
   choices are unavailable. Gate the Edit details action by existing authority and
   closed status. Complete component/route regression checks.
2. Connect directory View details to the page, preserving validated list state on
   return. Retain the separate administrator-invitation and lifecycle actions.
   Verify affected tests, TypeScript, build, desktop/mobile layouts and all three
   themes. Review authorization, safe destinations and shared styling; update the
   guide and verification record.

No API, database schema, permission or migration changes are needed. Existing
platform detail reads already enforce the configured operator and live grants.
The generated workspace identifier stays hidden, following the user's latest
requirement. The optional saved state is resolved against the selected country.

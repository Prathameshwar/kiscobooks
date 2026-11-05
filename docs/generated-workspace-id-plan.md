# Backend-generated workspace identifiers

User requirement: generate the tenant workspace identifier in the backend and
remove it from create/edit forms. Keep existing tenants and URLs unchanged.

1. Use the tenant's backend UUIDv7 to derive a unique, time-ordered ASCII workspace
   identifier. Update platform and self-service request contracts, preserving
   authorization, atomic provisioning, database uniqueness and replay safety.
2. Remove identifier inputs from both tenant creation paths and tenant editing;
   reuse existing form styles and retain validation, recovery and invitation UI.
3. Regenerate OpenAPI/client contracts, run API/UI regression checks and a local
   database/browser check, review security and update operating documentation.

The identifier uses existing tenant columns; no new table or sequence is needed.

Agreed scope extension: creation asks only Country and State for regional choices,
in one responsive row. Persist an optional default state on tenants with a
country/state composite foreign key and index, each DDL in its own reversible
migration. Existing tenants keep NULL. Resolve currency from the country table,
language to English and timezone to Asia/Kolkata for India, UTC otherwise. Reject
inactive states or states from another country; don't invent a state for tenants
created by older integrations that omit it. Editing retains its existing regional
controls, adds state, and does not expose a workspace-ID input.

Completed all three phases. See [verification](generated-workspace-id-verification.md).

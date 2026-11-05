# API contracts and typed clients

Identity, Catalog, Accounting and Audit clients are generated from each service's exported
OpenAPI. This package supplies typed transport to authorized server and browser adapters.

Run `npm ci`, `npm run generate`, `npm run check:generated`, `npm run typecheck`,
and `npm test` in this directory. Export Python contracts first with each service's
`python tools/export_openapi.py`; `--check` verifies committed contract drift.

Use `createCatalogClient({ baseUrl, fetch })` against the authenticated gateway.
Caller authentication stays with the gateway. Never put actor/source HMAC signing
keys in web/mobile clients. Internal Identity source paths are backend contracts only.
Use decimal strings and keep the same Idempotency-Key when retrying a command.
Read-denied response fields are optional and must not be assumed present.

Pinned openapi-typescript handles schema generation and openapi-fetch provides typed
transport; TypeScript checks contract compatibility. Generation disables requiredness
inference from default values so protected omitted fields remain optional.

Use `createAuditClient({ baseUrl, fetch })` for `/v1/audit-events`, on-demand detail and
bounded export. Detail requests include `occurred_at` for partition lookup and `company_id`
for the gateway's scoped authentication. Preserve opaque cursors and exact decimal strings.
The console uses its same-origin BFF; only the server holds the user's access token. Audit
field evidence can be omitted by current policy and older events can contain changed markers.

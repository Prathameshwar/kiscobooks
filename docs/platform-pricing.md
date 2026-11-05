# Platform fees and pricing

Authorized delivery phases (2026-10-23): (1) Identity models, migrations, exact-decimal
pricing, deployment seed and protected APIs; (2) generated client and Console management
using shared UI; (3) native database, API/UI tests and manual simplification/security review
with fixes. The user requested the plan and execution together.

## Commercial decisions

Platform subscriptions are billed upfront for 12 or 36 months. Monthly equivalents are
INR 449 and 389: net term totals 5,388 and 14,004; 18% tax is extra. Add-ons are optional,
monthly, with no included usage. Usage prices are per 1,000 units, prorated to actual
billable units, not rounded to whole packs. SMS counts billable segments, email counts
recipient deliveries, WhatsApp counts outbound template messages, AI counts input and
output tokens separately, documents count pages (up to 4,096 input/1,024 output tokens
per page; larger pages need a separately priced tier). Document processing does not
also charge token usage. Paid LLM and document execution are future integrations;
this delivery manages their commercial catalog and does not enable providers or billing.

| Default | Monthly INR | INR / 1,000 units | Output INR / 1,000 tokens |
|---|---:|---:|---:|
| Platform, 12 months | 449 | — | — |
| Platform, 36 months | 389 | — | — |
| WhatsApp utility (India) | 149 | 900 | — |
| WhatsApp marketing (India) | 149 | 1,500 | — |
| SMS (India domestic DLT route) | 99 | 450 | — |
| Email | 49 | 99 | — |
| Gemini 3.6 Flash | 199 | 0.1500 | 0.7500 |
| Claude Haiku 4.5 | 199 | 0.2000 | 1.0000 |
| GenAI document processing | 199 | 3,000 | — |

Each model/channel is an independent optional offering; subscribing to one does not
include another. These are proposed retail prices, not provider quotations. India
messaging prices must not be reused for international delivery. Carrier/DLT registration,
sender rental, special authentication, attachments, tool/search charges and high-context
model surcharges are excluded. Review provider costs before enabling an execution route.

FX snapshot: ECB 2026-10-22, EUR/USD 1.1205 and EUR/INR 106.2490, yielding
INR 94.8228 per USD (stored to four decimals). USD = INR / rate × 1.20, rounded
up to cents for monthly fees and four decimals for usage. This is a fixed editable
catalog conversion basis, not a live FX service. Editing INR or FX derives USD on the
server, so the premium cannot drift. Tax previews use each row's configured rate
(default 18%) and are catalog illustrations, not a jurisdictional tax determination.

Benchmarks checked 2026-10-23:
[ECB](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html),
[MSG91 India SMS](https://msg91.com/in/pricing/sms),
[Twilio WhatsApp](https://www.twilio.com/en-us/whatsapp/pricing),
[Amazon SES](https://aws.amazon.com/ses/pricing/),
[Gemini](https://ai.google.dev/gemini-api/docs/pricing),
[Claude](https://platform.claude.com/docs/en/about-claude/pricing).

## Ownership and lifecycle

Identity owns global `platform_price` and append-only `platform_price_revision`.
`platform_price` has UUIDv7 `id`; `code` VARCHAR(40) unique, `name` VARCHAR(100),
`category`/`unit` VARCHAR(20), `description` VARCHAR(1000), integer `term_months` and
`version`, `currency_code` VARCHAR(3) (INR), `monthly_fee`, `unit_price`,
`output_unit_price`, `tax_percent`, `fx_inr_per_usd` DECIMAL(19,4), `provider`
VARCHAR(60), `model` VARCHAR(100), nullable `deleted_at` DATETIME(6), and the shared
Audit/Deactivable columns. All listed business fields are NOT NULL. Currency values
and tax/term previews are derived by the API and retained in the revision JSON.
`platform_price_revision` has UUIDv7 `id`, `price_id` FK, integer `version`, unique
(price_id, version), typed `snapshot` JSON, UTC `created_at` and nullable `created_by`.
Tenant billing, payments, entitlement enforcement and `tenant.plan_id` assignment remain
separate. Only a configured platform operator with current `platform.config.manage`
authority can access these routes; mutations also require fresh authentication.
Writes lock the installation and require the current row version. All mutations save an
immutable commercial snapshot and transactional audit event. Code is immutable and
unique. Delete retains a tombstone and history; restore returns an inactive offering.
Existing references must always resolve historical snapshots, not mutable current prices.

Deployment seeds insert absent codes only, preserving administrator edits, deactivation
and deletion. No API-startup seeding. Default changes on upgrades require deliberate
administrative edits; deployments never silently change commercial prices.

## Decision log

- 2026-10-23: User authorized built-in 1/3-year subscriptions, INR/USD (+20%) pricing,
  optional communications and future multimodel/document add-ons, full platform-admin
  lifecycle management and fresh-deployment defaults. Reuse existing Identity installation,
  operator authorization, transactional audit, proxy, pagination and shared UI.

## Verification

Identity/API/schema/installation/regression suites: 728 passed, 5 container-only tests
skipped in that run. A separate disposable local MySQL 9.6 run passed the native
installation test, fresh installation and repeat installation (nine prices and nine
initial snapshots), schema comparison and 0085→0083→0085 round-trip. The local Identity
database was backed up, upgraded to 0085, seeded and compared successfully; existing
tenant/user/company counts were preserved. Private logs/backups are under ignored
`.tools/schema-sync-audit/pricing-*` and `identity-before-pricing-*.sql`.

Console pricing, platform page, proxy/client and protected route tests: 49 passed.
Audit pricing/history permission tests: 35 passed. Identity OpenAPI and generated
TypeScript checks, strict mypy on the five new Python modules, and auth/Console
typechecks pass. Shared table regression checks and final static checks are recorded
with the completion evidence below.

Completion evidence: 106 shared DataTable tests and 8 generated API transport tests
pass, as do shared UI and API-client typechecks and the targeted Ruff checks. Browser
multiline-bound checks reproduced the mobile overlap before the shared `height: auto`
fix and passed afterwards. Live Identity exposes the four pricing route patterns and
returns 401 for an unauthenticated catalog request. Identity was restarted with the
new routes; workers that were stopped were left stopped. No commits or publication
were requested. Shared UI/API-client patch versions are 0.1.16/0.2.7, with lockfiles
updated or checked using offline lockfile-only installation.

Browser component fixtures render the real pricing components and centralized CSS with
mocked API data generated by Identity's price serializers. Desktop/mobile screenshots
in Light, Dark and Ledger, editor layout, overflow and multiline cell-bound checks pass
under `.tools/pricing-ui/`. This is component browser evidence, not a completed
Authentik sign-in or real checkout. The user disabled Bill-HostLink after reporting
internet/Teams problems; it remains disabled, and the live sign-in flow was not rerun.

Manual simplification and security reviews replaced the unavailable `/simplify` and
`/security-review` commands. Findings fixed: original-version retention for recovered
drafts, stale-edit reload action, transactional grant-refresh locking, mobile table
height/description overlap, and URL-escaped connection strings in the migration test
helper. Audit routing is explicitly allowlisted for all four price event types and
its platform-only permission boundary is tested. No remaining findings were identified
within this delivery's catalog scope. Provider execution, usage collection, charging,
tenant subscription contracts and jurisdiction-specific tax decisions are separate.

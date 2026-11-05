# Managing notifications

Open **Platform administration > Platform notifications** for messages owned by the
platform, including staff and pre-tenant recipients. Open **Settings > Notifications**
for the current tenant. The card and each area use that realm's specific grants.
Platform configuration never inherits the currently selected business company.

Both workspaces use the existing Console shell, cards, tables, forms, confirmation
dialogs and light/dark/ledger themes. Each area has a direct URL; provider, sender,
template, variant, version, route, request, delivery and receipt details can be opened
independently. Filters and opaque page cursors remain in the URL without destinations
or message variables. Lists report the server's page, not an invented total.

## Configuration order

1. **Providers and senders:** register SES email, Twilio SMS or Meta WhatsApp accounts
   using an approved credential binding. Secrets are configured by the deployment;
   the browser selects references. Validate the account, create its sender, then
   verify or sync that sender. Jobs show their status and can be refreshed. Account
   edits carry a revision so concurrent updates fail visibly instead of overwriting.
2. **Channels:** inspect readiness reasons and enable the configured channel. Provider
   readiness is distinct from a delivered message. Existing tenant compatibility
   starts channels enabled; platform channels require deliberate enablement.
3. **Templates:** choose a registered purpose, company scope where applicable, typed
   variables and default language. Add each channel/language variant and an immutable
   content version. Email supports text and optional HTML; previews show HTML as inert
   source. SMS uses text. WhatsApp supports positional text parameters for header,
   body and a dynamic URL button at its provider index; media parameters are outside
   the supported API contract.
4. **Activation and approval:** preview with sample variables. For WhatsApp, connect the
   provider template and sync its authoritative approval. Activate immediately or
   schedule a version using local date/time. Historical sends retain their frozen
   content. Inspect activation history and set an end when required.
5. **Purpose assignments:** assign the template to its registered purpose, trigger,
   channel and validity window. Tenant assignments can target the selected company
   or all companies, subject to the API's authority and overlap checks.
6. **Routing:** choose a matching active account and verified sender; configure
   priority, weight, attempts, timeouts and backoff. **Check policy** asks the API
   whether the selected purpose/channel/company currently resolves. It sends no
   message. Source systems continue to request messages through their established
   authenticated workflow.

## Recipient policy and operations

**Recipients** accepts a known subject reference or follows a delivery's masked
endpoint link. The API has no global recipient directory. **Consent** records actual
evidence, occurrence time, purpose, state and optional expiry. **Suppressions** accepts
a destination for server-side hashing and a dated scope; the destination stays out of
navigation and stored browser state. Expiring a suppression requires confirmation.
These areas can be granted independently of provider management.

**Requests** explains source references, planning completion and each channel's outcome.
Follow a request into **Deliveries** to inspect lineage, attempts, provider acceptance
and timestamped status events. A tenant source-workspace link appears only with the
source grant and matching selected company. **Receipts** exposes safe receipt metadata;
signed evidence still has to match the delivery identity. **Recovery** distinguishes
unresolved sends from retryable failures. Retry and reconciliation require separate
authority and confirmation. Unchanged replayable commands retain their body/key after
a lost response; a server conflict preserves the form for correction.

Administrative history uses existing platform history or tenant Audit, loaded on
demand under its separate permission. All-company tenant records use tenant-wide
history rather than a synthetic business company. Configuration history and delivery
status history serve different purposes.

## Local verification

The repeatable browser fixture runs the production components, Next notification proxy,
FastAPI management routes, signed actor guards, planner, dispatcher and native signed
callback verification with disposable SQLite. Identity authentication, provider account
inspections and external submission are fixtures. It does not replace a real IdP,
RabbitMQ source integration, Audit service journey, production MySQL deployment or
live provider/HTTPS certification. The backend suite separately exercises native MySQL.

From the repository root, with the Notification virtualenv, existing frontend packages
and Chrome installed:

```powershell
uv run --no-project --with playwright==1.56.0 python mfes/apps/console/tests/notification-e2e/run.py
```

The pinned Playwright installation is isolated from application dependencies. The runner
uses loopback ports and test-only fixture modules, creates data/screenshots under ignored
`.tools/notification-ui-browser-*`, and terminates its own child services. Test source
staging is never mounted in production. See [review evidence](notification-ui-reviews.md)
and [execution TODO](notification-ui-todo.md). Live activation follows
[Notification operations](notification-operations.md).

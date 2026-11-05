# Master audit, activity and logging review

Reviewed 2026-10-29. Findings only; no application, worker, credential or database changes were made.

The subsequent authorised fixes and final verification are recorded in
[master-audit-implementation.md](master-audit-implementation.md). The findings below
preserve the pre-fix snapshot.

Scope: Identity organisation/reference/customisation masters; Catalog product, classification, unit, warehouse, pricing, tax and configuration masters; Accounting accounts, parties, openings, bank and tracking masters; Vouchers definitions/configuration/counters; Design templates/assets; Notification management masters; Reports audit delivery. Traced command evidence, outboxes, publisher contracts, authenticated ingestion, activity/history reads, Console adapters and Windows startup/logging.

## Confirmed findings

### 1. High: central audit delivery is unconfigured for six producers locally

The configured Audit database contains 4,317 events, all from Identity. The private local configuration has no audit broker settings for Catalog, Accounting, Vouchers, Reports, Notification or Design, and Audit has no source credentials admitting these issuers. This is a local deployment finding, not proof about another environment.

Read-only database snapshot:

| Producer | Declared audit routes | Pending registered audit events | Delivery attempts |
| --- | ---: | ---: | ---: |
| Catalog | 441 | 1,931 | 0 |
| Accounting | 372 | 647 | 0 |
| Vouchers | 57 | 43,186 | 0 |
| Reports | 16 | 0 | — |
| Notification | 84 | 0 | — |
| Design | 18 | 0 | — |

The Vouchers backlog includes 43,166 source-projection events, so it must not be described as 43,186 master edits. Accounting includes 96 account-create events and 196 account-group-create events. Local outbox durability exists, but those facts cannot appear in central audit or activity yet.

References: producer `tasks/audit_publisher.py` configurations; `apis/audit/src/audit/config.py`; `apis/audit/src/audit/tasks/consume.py:163`.

### 2. High: bank master and reconciliation events are excluded by the source publisher

`accounting.tasks.bank_reconciliation.audit()` constructs event names directly rather than validating them through `audit_event()`. The corresponding actions are absent from `accounting.events.audit_contract.AUDIT_EVENTS`; the publisher selects only that set. These events remain in the outbox indefinitely even after broker configuration is supplied.

Reproduced by invoking the actual emitter with a recording session, without a database write:

- `accounting.bank_reconciliation_policy.publish`
- `accounting.bank_statement_mapping.publish`
- `accounting.bank_opening_item.review`
- `accounting.bank_statement_import.commit`
- `accounting.bank_reconciliation_session.finalize`

All five emitted successfully and all five failed membership in the publisher's allowed set. The same helper is used by preview, duplicate decisions, reject, match/unmatch, adjustment proposals and session amendment; those actions need a complete contract inventory too.

References: `apis/accounting/src/accounting/tasks/bank_reconciliation.py:73`, `:264`, `:307`; `apis/accounting/src/accounting/events/audit_contract.py:112`; `apis/accounting/src/accounting/tasks/audit_publisher.py:42`; `libs/platform/src/billing_platform/delivery.py:75`.

### 3. High: Identity's consumer credential omits a currently emitted route

The Identity source declares 111 audit routes; local Audit credentials admit 110. The missing route is `voucher_source.discovery_read`. There are 516 pending events for this route, of which 445 have exhausted the 12-attempt limit. Updating the allowlist alone will not release exhausted rows.

There are also 14 exhausted platform events on routes that are now admitted. They need reviewed recovery; the counts alone do not establish their original failure cause. Another 37 pending Identity events precede the configured historical cutoff and are deliberately held, not a new delivery bug.

References: `apis/identity/src/identity/events/audit_contract.py:7`; `apis/identity/src/identity/api/voucher_enrollments.py:87`; `apis/audit/src/audit/tasks/consume.py:166`; `apis/identity/src/identity/tasks/audit_outbox.py:24`.

### 4. High: master lookup values can enter infrastructure access logs

The Windows nginx access format logs `$request`, including the query string, and the raw Referer. Identity's tax-registration lookup accepts `q` and searches the registration number. Supplying a full tax identifier as a supported search term therefore puts that identifier into the access log. Sanitising audit evidence does not sanitise this separate logging path. Notification callback logging is explicitly disabled, but equivalent treatment is absent for sensitive master lookups.

References: `start/win/conf/nginx.conf:16`; `apis/identity/src/identity/api/company_statutory.py:202`, `:230`; `start/win/conf/bill.conf:142`.

### 5. Medium: normal startup does not start the complete audit pipeline

`start-services.ps1` starts Identity's audit publisher and the Audit consumer only when Identity's broker setting exists. It does not start the Catalog, Accounting, Vouchers, Reports, Notification or Audit-export publishers. Its delivery-worker helper starts execution/source workers, not these audit publishers. Consequently, adding missing configuration still leaves delivery dependent on separate manual commands.

Design has an audit publisher module but is absent from both the worker selector and worker definitions in `audit-workers.ps1`, so the managed launcher cannot start it at all.

References: `start/win/start-services.ps1:55`, `:70`; `start/win/lib/delivery-workers.ps1:9`; `start/win/audit-workers.ps1:4`, `:23`.

### 6. Medium: audit-to-log request correlation is absent in the normal request path

Console's service proxy neither creates nor forwards trace/request identifiers. The shared nginx proxy include does not generate them either. Most service authentication adapters only copy incoming correlation headers, so missing input produces null correlation. Identity establishes request correlation only for platform/setup routes; Notification's authentication adapter establishes actor attribution but no audit request context.

Database evidence: all 1,931 Catalog events and all 647 Accounting events lack both trace and request IDs. All 4,884 registered Identity outbox events lack trace IDs; 4,813 lack request IDs. Unit tests prove correlation when headers are supplied manually, which does not exercise this normal Console path.

References: `mfes/apps/console/app/lib/service-proxy.ts:140`; `start/win/conf/proxy.include:1`; `apis/catalog/src/catalog/api/auth.py:47`; `apis/identity/src/identity/main.py:98`; `apis/identity/src/identity/api/dependencies.py:26`; `apis/notification/src/notification/api/auth.py:90`.

### 7. Medium: financial-opening evidence does not explain what was entered or linked

The financial-opening helper emits reference/action/company/actor identifiers but supplies no `changes` and no `actor_type`. Its entry-create events omit safe account references, currency, side and exact amounts; its chunk update omits the newly assigned journal reference. Detailed owner records exist, but the central trail cannot explain these actions from its own evidence.

Reproduced an actual `accounting.financial_opening_entry.create` emission: `changes={}`, `actor_type=null`. Revision creation and import updates use the same helper. Safe scalar evidence should be explicit; arbitrary declaration/document payloads must remain excluded.

References: `apis/accounting/src/accounting/tasks/financial_opening.py:150`, `:670`, `:699`, `:876`; `apis/accounting/src/accounting/tasks/financial_opening_import.py:125`, `:271`.

### 8. Medium: the central audit subject filter is incomplete

Catalog's entity vocabulary is generated, but Accounting and other producers are maintained in a partial static list. Missing examples include stock batches/serials (`accounting.stock_lot`, `accounting.stock_unit`), financial-opening revision/entry/chunk/import entities, party drug licences, withholding masters, and Vouchers/Design/Notification entities. Events can appear under All subjects, but users cannot select these subjects from the central filter. Legacy invoice/payment subjects remain offered.

References: `mfes/apps/console/app/lib/audit-events.ts:48`; `mfes/apps/console/app/components/AuditEvents.tsx:427`.

### 9. Medium: activity and master history are not consistently exposed in the Console

Audit implements the authenticated `/v1/activity` projection, but the Console has no caller or activity-feed UI. Product and generic Catalog details do not provide a central subject-history entry point. Accounting configuration history uses the owner's `MasterRevision` endpoint and displays action/version/time/field names, omitting the available `created_by` actor and offering no central evidence detail. Notification and platform screens already embed the central history component, so the user experience differs by master family.

These are UI coverage gaps. They do not establish missing backend mutation events by themselves.

References: `apis/audit/src/audit/api/routes.py:230`; `mfes/apps/console/app/components/AccountingConfigurationDetail.tsx:720`; `mfes/apps/console/app/components/ProductCatalogDetail.tsx`; `mfes/apps/console/app/components/CatalogMasterDetail.tsx`; `mfes/apps/console/app/components/notifications/History.tsx`.

### 10. Medium: delivery failures lack sufficient operational visibility

Audit ingestion permanently rejects authentication/contract/payload failures without a diagnostic record identifying the safe event/message reference and rejection class. Reconnect logs contain only an exception class. Readiness checks test the database, and Windows health reports API readiness without audit-worker/backlog coverage. A functioning read API can therefore report ready while whole master families are absent from the trail.

Manual outbox inventory and dead-letter tools do exist; the gap is continuous visibility and actionable failure correlation, not the total absence of recovery tooling.

References: `apis/audit/src/audit/tasks/consume.py:152`, `:193`; `apis/audit/src/audit/main.py:73`; `start/win/lib/health-check.ps1:45`; `libs/platform/src/billing_platform/outbox_ops.py:14`.

### 11. Medium: Notification evidence shape does not match the history renderer

Notification's mutation hook writes `changes={fields: [...], values: {...}}`. Console's normalizer expects each changed field to contain `{from,to}` or a change marker. It turns both Notification entries into generic changed markers, losing the actual field list and lifecycle values in the rendered detail. This affects Notification management master history once delivery is configured.

References: `apis/notification/src/notification/audit.py:70`; `mfes/apps/console/app/lib/audit-api.ts:25`.

## Verification and limits

- Read-only aggregates from all eight configured local service databases; no payloads containing personal data or credentials were exported.
- Compared every producer's declared audit route set with configured Audit source credentials. No declared action exceeded Audit's 60-character action limit.
- Static inspection of literal `emit(..., payload=audit_payload(...))` routes found no additional undeclared literal routes. This does not prove every dynamically assembled route or every mutation is covered; the banking defect demonstrates why dynamic emitters need coverage checks.
- Existing focused tests: Audit ingest/chain/dedupe/source contract 28 passed; authenticated delivery/read boundaries/routes/field-policy projection 48 passed; Accounting evidence/access 4 passed and 1 skipped; Catalog evidence 5 passed. Total: 85 passed, 1 skipped.
- Reproduced five excluded banking routes and empty opening-entry evidence through actual emit helpers without committing data.
- No broker replay, worker restart, credential update or destructive test against configured databases was performed. Broker end-to-end delivery for unconfigured producers remains unverified.
- Sample audit data is used by tests; the live audit page uses the real Audit client. It is not a confirmed production fallback bug.
- Application logs are intentionally infrastructure logs, not writes to Audit. Integration-log and OTel/Grafana delivery remain documented follow-ups, rather than undocumented missing master audit events.

The next implementation should prioritise event-contract completeness, sensitive access-log handling, producer onboarding/startup, reviewed backlog recovery, correlation and operational visibility, then evidence/UI consistency.

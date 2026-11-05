# Notification settings review and fixes

Scope: `/settings/notifications`, its thirteen areas and nested records. Shared
components also serve `/platform/notifications`; verify both ownership boundaries.
Authorized 2026-11-02: inventory, review, fix bugs/gaps sequentially, repeat reviews
until the covered flows pass, and report findings/fixes. Preserve concurrent work.

## Execution plan

1. Inventory routes, governing contracts, existing tests and runtime prerequisites.
2. Review the areas below in order. For each: inspect UI/API behavior, record a
   finding, reproduce it with a failing regression, fix it, run affected checks,
   and review the result before proceeding. Reuse existing architecture and APIs.
3. Review shared navigation, request proxy, permissions, tenant/company isolation,
   command replay, sensitive content, date formatting and accessibility.
4. Run the Notification UI/API suites and browser journeys where available;
   distinguish isolated fixtures from live provider delivery certification.
5. Repeat the security and workflow review, resolve discovered findings, and record
   final evidence and any remaining product/deployment prerequisites.

| Order | Area | Review coverage | Status |
|---|---|---|---|
| 01 | Overview | Channel readiness, limited permissions, useful next actions | Reviewed; N01 verified |
| 02 | Channels | Prerequisites, enable/disable, confirmations and pending state | Reviewed; no area-specific bug found |
| 03 | Providers and senders | Creation/edit, credential refs, verification jobs, callbacks | Reviewed; N02/N03 verified |
| 04 | Templates | Purpose/schema, variants, immutable versions, safe previews | Reviewed; N04 verified |
| 05 | Purpose assignments | Company scope, effective dates, activation and end history | Reviewed; N05 verified |
| 06 | Routing | Provider/sender dependencies, policy controls, effective-policy check | Reviewed; N06 verified |
| 07 | Recipients | Required source references, masked endpoints, paging | Reviewed; no additional local bug found |
| 08 | Consent | Endpoint/purpose scope, immutable evidence, allowed transitions | Reviewed; no additional local bug found |
| 09 | Suppressions | Destination handling, scope, expiry, confirmations | Reviewed; no additional local bug found |
| 10 | Requests | Filters/cursors, detail/planning outcomes, permitted links | Reviewed; N09 verified |
| 11 | Deliveries | Status meaning, frozen lineage, attempts, manual retry | Reviewed; N09 verified |
| 12 | Receipt inbox | Safe callback evidence, filters, owner scope | Reviewed; N07 verified |
| 13 | Recovery | Ambiguous submissions, proven reconciliation, duplicate-send prevention | Reviewed; N08/N09 verified |

## Findings and fixes

| ID | Finding / impact | Fix / regression | Status |
|---|---|---|---|
| N01 | A successful non-JSON upstream response was forwarded as HTTP 200. A channel/list screen could treat an error envelope as its DTO and crash. | Shared proxy returns safe 502 for malformed successful JSON responses and preserves real upstream error statuses. Notification proxy regression reproduced 200 instead of 502. | Verified |
| N02 | Callback copy success/failure appeared in the provider card, away from the URL/control. | Independent copy action with feedback and pending state inside the callback card. Regression failed to find the error beside the copy control. | Verified |
| N03 | Active but unverified senders were described as available to routes. | Readiness text checks sender verification and active provider as well as sender activation. Regression reproduced misleading admission text. | Verified |
| N04 | Preview required every declared variable, including optional variables unused by the content, and defaulted optional booleans to true. | Respect schema-required fields; allow optional booleans to remain unset and omit blank optional values instead of inventing zero/true. Regression reproduced a required optional integer. | Verified |
| N05 | Assignment selectors offered templates belonging to a different company; changing company scope retained an incompatible choice. | Match template scope to selected company or all-company template scope, and clear selection on scope change. Regression reproduced the other-company option. | Verified |
| N06 | Route directory had no filter controls and ignored supported purpose/sort query values. | Expose the existing API's channel, purpose and created/priority sorts; retain them through cursor paging. Regression reproduced absent filter controls. | Verified |
| N07 | Receipt details claimed every signature used a provider secret, although SES uses asymmetric SNS certificate verification. | Describe registered provider trust configuration without misrepresenting the verification mechanism. Updated receipt regression failed on the old claim. | Verified |
| N08 | Empty recovery queue claimed every delivery had a settled provider outcome, which cannot be inferred from an absence of unresolved sending cases. | State only that no sending delivery requires reconciliation and direct readers to delivery history. Regression reproduced the unsupported claim. | Verified |
| N09 | Opening a record discarded list filters/cursor; recovery records returned to the ordinary delivery directory. | Shared table links retain only supported parent-list state. Back navigation validates the exact parent/owner and rejects unsafe, unrelated, duplicate or sensitive query fields. Regression reproduced missing return state; recovery return regression added. | Verified |

## Verification and final review

Baseline: 114 Notification UI/proxy tests passed before the new regressions. Each
reported bug was reproduced with a failing regression before its fix; corrected a
query-order-sensitive new assertion to compare parsed parameters rather than order.

After the fixes, 285 tests passed across 22 Notification/shared-proxy suites. The final
security pass added an invalid-URL return destination; it reproduced a render crash
and was fixed with guarded URL parsing. The affected navigation/chrome suites then
passed all 38 cases. Console TypeScript passed after that final fix. Task-file
whitespace checks passed with Windows CRLF handling; unrelated work was preserved.

Full Notification API suite: **222 passed, 3 skipped**, domain coverage **99%**.
Skipped cases are the native MySQL integration tests: no reachable container runtime.
This run used the service's isolated SQLite fixtures, not the user's business database.

Manual simplification/security pass covered section grants, exact proxy methods and
queries, session credentials, tenant/platform/company boundaries, signed outbox/receipt
contracts, sensitive content, preview escaping, command replay and bounded paging.
No remaining blocking finding in the reviewed changes. `/simplify` and
`/security-review` commands are unavailable here; equivalent manual reviews were done.

Browser verification passed. Its fixture uses the production UI, proxy,
Notification API/planner/dispatcher and signature verification with disposable SQLite
data and simulated external Identity/provider services. It sends no real messages.
All thirteen areas passed for both owners (26 area checks). Complete platform email,
platform SMS, platform WhatsApp and tenant SMS journeys passed through configuration,
dispatch and signed receipt/history checks. Read-only mutation denial returned 403.
Overview layouts passed at 390px in light, dark and ledger themes without horizontal
document overflow. The existing harness's stale Save label, duplicate-badge/modal
selectors and document-load wait were corrected.

Final browser evidence: `.tools/notification-ui-browser-c9ac0bc8db044d3b82350894b8e467fc`
(33 screenshots, fixture database and API/web logs). Fixture processes were stopped
after verification. The sequential review/fix/review loop is complete for this scope.

## Remaining product and deployment prerequisites

- Actual provider/recipient receipt and public HTTPS callback certification require
  controlled credentials/recipients and are not established by these fixtures.
- Global recipient discovery, arbitrary test sends/campaigns and external attachment
  authoring remain the documented API/product boundaries, not implemented capabilities.
- No production dependency, schema, permission catalogue, credentials or live provider
  configuration was changed. No commit or publication was requested or performed.

# Company foundation: priorities 1-4

Authorized 2026-10-23: implement sequentially, maintain this TODO and complete two
review/fix passes. Business transaction pages remain a later workstream. Reuse existing
Console/shared styles and APIs; preserve concurrent inventory/reporting changes.

- [x] Read repository rules and inspect company/session/navigation/setup contracts.
- [x] CF01: harden company/year switching, isolate workspace state and handle stale context.
- [x] CF02: separate company settings, organisation administration and platform settings.
- [x] CF03: share scoped permission navigation across sidebar, search and direct pages.
- [x] CF04: show company setup/readiness from authoritative existing APIs, with explicit unknowns.
- [x] Review 1: authority, company isolation, privacy and setup boundaries; fix and verify.
- [x] Review 2: navigation, error/switch recovery, accessibility and integration; fix and verify.
- [x] Final validation and usage/review evidence.
- [x] FR01: final company/context review, outage recovery and unsaved-editor switching.
- [x] FR02: final company/organisation/platform authority review.
- [x] FR03: final sidebar, command search and direct-route permission review.
- [x] FR04: final readiness evidence, denied/unknown states and browser validation.

Plan: CF01 verifies server selections before cookies, refreshes resolved authority on
context changes and prevents stale client state. CF02 gives company and organisation
configuration separate surfaces and keeps global reference/provider controls in their
proper realm. CF03 filters available destinations using effective scoped grants, hides
empty sections and keeps the command palette identical. CF04 reads existing Identity
setup and Accounting financial/calendar facts; no invented readiness, automatic posting,
tax certification or new business lifecycle is introduced. Missing checks stay explicit.

Each phase will record regression checks here. No commit/publication is implied by this
implementation request. Dedicated review commands will be used only if available;
otherwise both reviews are manual and that limitation is recorded.

CF01: verified exact Identity company and Accounting year before writing cookies; added
workspace remounts on authority/company changes, strict fiscal cookie parsing, switch
submission locking and stale-search cancellation. Five failing regressions reproduced
the prior behavior; all 66 affected context/switch tests passed after the fixes.

CF02: Company settings now contains only selected-company controls. Organisation
administration owns tenant-wide notification transport and delegated organisation access;
global reference cards moved to Platform administration. Direct notification pages now
require active tenant-scope grants, matching the API. Scope/page tests passed after
correcting a test mock call-counter reset. UI uses existing components.

CF03: one navigation resolver now serves both rail and command palette, removes empty
sections and hides unavailable transaction destinations even with broad grants. Company
business links require a selected company; organisation links require actual tenant-scope
grants. Existing scoped access-review remains delegated, with APIs enforcing each object.
Thirty-one affected navigation/settings/page tests and Console TypeScript passed.

CF04: added a read-only Company readiness screen with Identity profile/features/locks,
Accounting books and selected-year posting prerequisites. Denied/redacted/unavailable
checks remain explicit; no global green status or client-side posting decision exists.
Chart/mapping/tax/numbering responsibilities are explained without claiming certification.
The new exact proxy read remains method/query constrained. All 66 focused readiness/
page/proxy-policy checks passed. No backend contract/model/migration changed.

Both manual reviews completed with fixes verified: strict response IDs, mismatched-owner
read rejection, Audit company/read gates, useful organisation entries, direct business
page guards, shared switch serialization, revoked-calendar hiding, correct realm links
and narrow card controls. Dedicated review tools were unavailable and were not claimed.

Final evidence: 905 full Console tests passed against frozen application source; all
12 final readiness checks and 38 affected creation/calendar checks passed. Console
TypeScript passed. Existing affected
Identity tests passed 21 and Accounting tests passed 11. Chrome switch/permission/year/
denial/read-only journeys and 390px light/dark/ledger content overflow checks passed;
screenshots were inspected. Fixture processes terminated. No blocking local findings.

Usage, scope decisions, exact findings and validation limits:
[company-foundation-review.md](company-foundation-review.md).

Final sequential review: FR01 fixed optional context-read failures and pre-cookie unsaved
editor protection, preserving Next authentication/step-up redirects. FR02 confirmed active
tenant-only authority for organisation controls and company creation. FR03 fixed a Platform
history link exposed without its page permission and shared the platform entry permission
list. FR04 rechecked read-only evidence, sparse fields and mismatched financial years.
All 84 focused checks and all 917 Console tests passed (zero failures/skips); TypeScript
passed. Identity owner checks passed 21 and Accounting fiscal/readiness checks passed 11.
Chrome passed the updated blocked-editor switch
journey as well as company/year/permission/denial journeys and all three mobile themes.
Full results: `.tools/company-foundation-final-review-tests.json`.
All four final-review items are complete; no blocking findings remain within the implemented
scope. Future business pages and fixture-loader replacement remain deferred as agreed.

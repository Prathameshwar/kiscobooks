# Reports card hub

## Books submenu addition (2026-10-27)

Books and Reports now contains sibling Books and Reports parent menus. Books lists ten native
books, ledgers and transaction registers: Day book, Cash book, Bank book, Sales book, Purchase book,
Payment book, Receipt book, Account ledger, Party ledger and Stock ledger. Each `/books/{key}`
opens its own disabled card landing page; `/books` searches all ten. Native report definitions are
reused without inventing execution routes. Books pages require the selected company's current
`report.read` grant. The Reports categories and their 38 cards retain the same permissions and
availability policy. Books and Reports reuse one catalogue renderer, shared CSS and components.

Search gives direct title/code/description matches priority, with section-name search as a fallback.
This keeps a partial name such as cash bo focused on Cash book while still allowing section search.
No database, API, report-run or voucher behavior changes. Verification: 69 book/report/sidebar tests and Console TypeScript passed. A fresh tenant3 login verified all ten submenu destinations and active states, partial-name search, disabled cards and six theme/viewport combinations without overflow or browser errors. Screenshots were reviewed.

## Current navigation change (2026-10-27)

User-directed phases: (1) rename Books to Books and Reports and add four children
under Reports; (2) provide Inventory reports, Finance reports, Tax reports and
Analytics landing pages using the existing report catalogue and shared styles;
(3) verify category isolation, search, disabled cards and scoped navigation.
Masters remains a single link inside Administer. Report cards are disabled in
these landing pages for now, independently of backend execution availability.
No report code, owner model, database schema or execution contract changes.

The current menu uses these company-scoped `report.read` landing pages:

| Submenu | URL | Report cards |
|---|---|---:|
| Inventory reports | `/reports/inventory` | 10 |
| Finance reports | `/reports/finance` | 22 |
| Tax reports | `/reports/tax` | 3 |
| Analytics | `/reports/analytics` | 3 |

Each native report belongs to exactly one category. Tax-to-ledger reconciliation
is grouped with Tax; the other source/balance reconciliation controls are under
Analytics. `/reports` retains search across all 38 cards. Category search stays
within the selected category. All report cards have no destination and remain
disabled, including when the Reports API advertises a runnable definition. The
landing pages perform no discovery or execution request. Existing bookmarked
workspace behavior is retained without a landing-page shortcut.

Current verification: 110 affected navigation/report/administration tests passed;
the notification-heading/workspace run passed 48 tests (overlapping navigation
coverage), and Console TypeScript passed. A real tenant3 browser session checked
all four category destinations/counts, disabled cards, active submenu, all-report
search and recovery, Administration and Notifications headings, and six viewport/
theme combinations (1440/390 px, Light/Dark/Ledger) without overflow or page errors.
Desktop/mobile screenshots were reviewed. The headless review blocked external
Google font requests after they delayed page-load completion; application data,
authentication, routes and shared CSS were live. No report runs or exports were
created. Manual scope, disabled-link and input review found no remaining issue in
this navigation slice; named simplify/security-review commands are unavailable.

## Previous implementation (superseded by the change above)

1. Move the single Reports menu below Masters, without children. Replace `/reports`
   with grouped report cards and a full/partial-name search using shared components.
2. Preserve the existing report workspace at `/reports/workspace`. Discover native
   permitted definitions; only reports advertised as runnable get working links.
   Known unavailable reports remain disabled, with no guessed report pages. A report
   link preselects its native definition without automatically creating a run.
3. Verify company scope, permissions, availability failures/retry, searching,
   workspace continuity, safe URLs and desktop/mobile themes. Preserve existing
   generation, financial-year, export and idempotency behavior.

Decision 2026-10-27: Reports remains in Books; Masters is inside Administer. The card hub is the discovery
entry point; the existing execution workspace remains available. No report engine,
financial calculation, API, migration or financial permissions are added.

## Implemented behavior

Reports remains in Books with no submenu. `/reports` contains 38 native
report cards across eight sections: financial statements, books/ledgers,
receivables/payables, banking/payments, sales/purchases, tax/credits,
inventory/warehouses, and controls/reconciliation. The fixed card codes were checked
against the current Reports service registry; no speculative report URL is offered.

The shared FilterBar/TableSearch supports case-insensitive full or partial names,
descriptions and native codes. Underscores, hyphens and ampersands are normalised
for matching. Empty sections disappear during search; clearing restores the list.
Shared ActionCard, SectionHeader and responsive grid styles remain the layout.

Existing company-scoped discovery controls availability: only an advertised
definition with `run_enabled=true` gets a card link. Others are disabled and have
no href. An outage or malformed catalogue leaves cards disabled with a retry action.
Report discovery is read-only; it does not create a source snapshot or report run.

The existing execution workspace is preserved at `/reports/workspace`, with a
header shortcut for classic reports, banking and retained report history even
when framework cards are unavailable. A card passes a bounded native report code;
loading the workspace preselects the permitted definition and its parameter
defaults. A stale/unavailable code is not selected. Reports are created only by
the existing explicit create action. Date/year behavior, frozen results, paging,
drilldown, idempotent retries and exports remain in the original components.

Both routes and the menu check active tenant/company `report.read` authority for
the selected company. Company/department mismatch, expired grants and role labels
cannot unlock reports. The workspace filters action permissions to the same scope.
Invalid code query values are rejected before loading the page.

## Verification and limits

- 107 affected Console tests passed across nine suites. These include hub search,
  disabled availability, retry, malformed discovery, scoped access, URL checks,
  menu order, report preselection and the existing classic/framework/date/export
  tests. The hub suite was rechecked after adding the workspace shortcut.
- Console TypeScript and changed-file whitespace checks passed.
- A browser harness used the actual shell, providers, shared CSS and hub with
  fixed catalogue responses. It checked 38 cards, menu order, working card URLs,
  disabled/unavailable and outage states, search and 12 width/theme combinations:
  1440, 1024, 390 and 320 px in Light, Dark and Ledger. No page errors or overflow;
  the mobile screenshot was inspected. No live report jobs or exports were created.
- Manual simplification and CLAUDE.md §§5–6 security review found no remaining
  issue. The named simplify/security-review commands are unavailable in this session.
  Backend discovery, job execution and financial authorization are unchanged.

Unrelated workspace edits were preserved. This task does not commit or publish them.

## Landing-page review, 2026-10-27

Reviewed together with Masters: 157 tests across 11 affected Console suites and
Console TypeScript passed. Repeated browser checks covered all 38 cards, sidebar
order/current state, search, disabled/outage states and the workspace link, plus
320, 390, 1024 and 1440 px in Light, Dark and Ledger. The final workspace header
shortcut was included in these checks. Desktop/mobile screenshots showed proper
spacing and alignment; no overflow or browser errors remained. No additional
application changes were required. Service responses were fixtures; no live report
runs or exports were created. Manual security and correctness review found no new
blocking issue.

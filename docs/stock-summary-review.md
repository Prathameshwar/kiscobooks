# Stock Summary final review — 2026-11-01

Reviewed the approved initial As-of delivery, its source producer, calculations,
workspace, access, navigation and actual private files against CLAUDE.md §§5–6.
The `/simplify` and `/security-review` commands are not available in this runtime;
their simplification and security checks were performed directly on the changed code.

## Findings fixed

- Preserve the explicit previous 0.8.0 inventory schema hash and additive native
  cuts. The first live preparation exposed rejection of the retained owner feed
  head; compatibility now accepts only known validated schemas, without rewriting it.
- Native stock mutations invalidate coverage in their own transaction. Fresh
  publication reconciles and restores it; old immutable cuts remain usable.
- The console proxy now permits only the scoped, bounded frozen selector GET.
  Private Catalog source authoring is not exposed through that proxy.
- Stock refresh handles the actual initial PENDING state and waits for READY.
- Full-result quantities stay separate by unit/owner/custody; excluding zero rows
  marks the output filtered. Unknown reservations never become zero availability.
- Held serials reduce eligibility, retain physical stock, and carry native serial
  identifiers. Bin identities prevent valid distinct positions collapsing into a
  duplicate grain. Unallocated residual costs are explicitly unavailable.
- Unit codes support Catalog's 30-character limit.
- Row details use a drawer and actions a kebab menu. Essential columns are the
  default, refresh buttons share the export toolbar, and As-of uses a calendar.
- An existing simulated-clock lease test signalled renewal before its enclosing
  heartbeat transaction committed. It now advances time after durable renewal;
  the previously failing case passes. No production lease rules were relaxed.

## Simplification and security result

Reuse the existing owner feed, Catalog definition fence, immutable source cuts,
report registry/jobs, frozen references, exports/downloads, Day Book workspace and
shared UI menu/drawer. No new datastore, table, bespoke stylesheet or public stock
authoring endpoint is introduced. Reporting-contract is 0.9.0 and consumer locks
are synchronized; the generated API client is 0.2.49.

Signed Catalog transport verifies responses and exact tenant/company, page count,
hashes, policy and lease continuity. Database tenant guards remain enabled. Reads
have row/byte bounds; queries use typed limits, fixed kinds and escaped searches.
Network acquisition happens before the Accounting publication transaction.
Publication, coverage and the feed commit together; reporting does not post money.

Full-input, item and warehouse authority is checked server-side. Denied fields
cannot be bypassed through source choices, filters, search, sorting, saved views,
history, totals, signed drilldowns or private exports. Actor ownership and current
authority are rechecked during calculation and download. Tests cover missing
permissions, wrong tenant/company/actor, field denial and signed navigation.
Source incompleteness and unsupported dates fail explicitly. Secrets and QA
sessions are retained only in ignored private configuration/artifacts.

No unresolved security or calculation finding remains within the delivered scope.
Arbitrary From/To reconstruction and quantity-only/restricted-warehouse authority
remain separate extensions from the approved plan. Initial native evidence covers
company-owned warehouse/transit stock; unsupported ownership/custody fails closed.
Source limits include 10,000 Catalog records, 100,000 native rows per grain, explicit
byte bounds, and 200 serial identities per position. Reservations without a complete
owner contract and ambiguous residual bin costs remain visibly unavailable.

See [delivery evidence](stock-summary-delivery.md). The live company had three
catalog items and zero stock; positive committed stock was verified in a disposable
native schema. Publishing and posting activation were not part of this delivery.

## Follow-up final review

The requested follow-up review found and corrected six workspace issues:

- A QUARANTINED source refresh now stops with recovery guidance and retains the
  completed report, rather than continuing to poll a terminal source.
- Discovery, Refresh and retained-date loading share bounded source selection.
  Newer financial-only cuts and known stale stock cuts are skipped; permission
  failures still propagate. Refresh preserves the previous usable result.
- Returning from a warehouse or ledger drill restores the parent's page, cursor
  and authorized column choices. The bounded navigation context contains UI
  selections only; rows are reread under current server authority.
- Drilldowns preserve the selected Stock Summary view. Applying filters from a
  child prepares the parent report in that view, without a false changed-view notice.
- The details drawer reuses the table's configured quantity, money and date
  formatters, column labels and ownership/custody descriptions. Changing runs
  resets the drawer so a previous row's detail cannot remain attached to a new run.
- Editing a stock view's filters, columns or report view clears its selected saved
  view identity. The same saved view can then be selected and restored again.

Each recovery/navigation/formatting fix has a regression test observed failing
before the correction. A separate calculation check verifies opening 100 plus
receipts 40 less issues 25 equals closing 115; available stock is 110 after a
reservation of 5, recorded value is 1,437.50, and the item ledger agrees.

Follow-up verification covers 100 reporting checks and 139 frontend checks across
the affected suites. Actual fresh source preparation, four private export formats,
PDF preview and desktop/mobile theme checks pass. The console application and
Stock Summary/Native Book/reference tests pass a separate TypeScript check.
The full console check reports six unrelated errors in the concurrently edited
purchase quick-create tests (missing policy arguments); those files were preserved.

The final live user journey also passes: unsupported-date guards, item search,
warehouse navigation and parent columns, private saved-view restore/deletion,
retained snapshot discovery and completed history restoration. It reports no
browser page errors; evidence is in the ignored `journey-review.json` artifact.

The follow-up security and simplification pass retains the same tenant/company,
actor, field authority and immutable-source boundaries. No calculation or access
rule was relaxed to make the UI recovery checks pass.

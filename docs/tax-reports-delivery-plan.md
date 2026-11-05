# Tax reports: sequential delivery

Authorized 2026-11-01: complete the same five-step loop as Inventory, one report
at a time, without intermediate approval pauses. Scope is the three reports
currently exposed at `/reports/tax`.

| Order | Report | Plan and acceptance |
|---:|---|---|
| 1 | Invoice Tax Register | Dedicated period/date-basis/party/registration filters, complete-result search, essential business columns, tax component detail and currency-separated totals. Count each supply's taxable value once across CGST/SGST/cess components; credit/debit notes reduce the corresponding direction. Preserve recorded rates and legal tax dates. |
| 2 | Input Tax Credit Register | Separate as-of component positions from period events. Show pending, eligible unclaimed, claimed, suspended, blocked and RCM discharge with purchase/return signs and currency-separated summaries. Event totals never inflate closing positions; late posted evidence cannot backdate a claim. |
| 3 | Tax to Ledger Reconciliation | Show verified invoice/credit-event tax lineage to posted GL lines with ledger/date/purpose filters, debit/credit/net amounts and explicit source verification. Tax-account net is not a mismatch merely because it is nonzero. Preserve journal drill date and scope; never present missing tax evidence as a statutory return. |

Each report follows: (1) concrete plan; (2) implementation and affected tests;
(3) correctness/security review and fixes; (4) UI/style/UX review and fixes;
(5) native and live end-to-end review of card, filters, columns, kebab/detail,
drill/return, private saved views/history and actual CSV/Excel/HTML/PDF/preview.
Complete one report before moving to the next. Finish with shared regression checks.

Reuse the shared Day Book/Inventory workspace, centralized styles and components,
immutable verified company sources, signed navigation and private exports. Refresh
and source refresh share the print/export row. Default columns emphasize business
facts; reference IDs and technical evidence remain optional. Review Light, Dark
and Ledger at desktop/mobile widths. Keep exact Decimal arithmetic and never add
incompatible currencies. Search/filter before paging, summaries and export.

The existing Accounting tax plan and voucher tax recording design govern semantics.
TallyPrime's tax register, ITC and tax-analysis concepts inform presentation only.
These are recorded-tax reports; GSTR filing, government reconciliation, new legal
profiles and operational tax/stock postings are outside this reporting scope.
No new service, table or live synthetic posting is planned.

| Report | Plan | Implementation | Correctness | UI/UX | End to end |
|---|---|---|---|---|---|
| Invoice Tax Register | Done | Done | Done | Done | Done |
| Input Tax Credit Register | Done | Done | Done | Done | Done |
| Tax to Ledger Reconciliation | Done | Done | Done | Done | Done |

## Decision log

- 2026-11-01: user explicitly authorized planning and implementation plus all
  three review/fix passes. Existing repository boundaries and permission checks
  remain enforced. Publication was not requested.
- 2026-11-01: discovery confirms three tax cards and existing verified native
  calculations, but generic workspaces and no dedicated full-result tax summaries.
  Preserve posting/document/tax-point date distinctions and native ITC authority.
- 2026-11-02: default file views emphasize business columns; explicit source-detail
  views retain audit references. A period column distinguishes comparative rows,
  while summaries identify current-period totals. Tax-ledger selection waits for
  scoped reference verification before Apply. Existing retained runs are immutable.
- 2026-11-02: workspace discovery depends on fiscal-year date values so a theme
  refresh with the same year preserves applied filters, view and print readiness.
- 2026-11-02: the requested final audit keeps retained tax columns unchanged until
  a new view succeeds, including failures and retries. Saved views restore columns
  against their own registered view; saving an unapplied selection uses that
  selection's column defaults. Comparative credit-event totals explicitly identify
  the current period, and recognized tax acronyms retain their casing.

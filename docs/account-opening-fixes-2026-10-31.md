# Account opening UI fixes - 2026-10-31

AO-B01 and AO-B02 from [the opening/ledger review](account-opening-ledger-review-2026-10-31.md)
are implemented. The four account-ledger gaps AL-G01 through AL-G04 remain in the
separate ledger backlog. The [todo list](account-opening-fixes-todo.md) tracks this
delivery; [findings.csv](testing/account-ledger-review/findings.csv) records current
finding status and [cases.csv](testing/account-ledger-review/cases.csv) remains the
reusable checklist.

## Result

Opening document/due dates, retained batch dates, captured revision timestamps,
finalization timestamps, captured revision/import coverage, native journal dates,
books-begin and worksheet review dates now use `useFormatters` from the resolved
company display configuration. Business dates remain calendar dates; UTC timestamps
display in the configured company timezone. Native date inputs, exact declaration
values and posted evidence retain their original values.

Unknown document dates remain "Unknown". Field-denied opening dates remain
"Date restricted". A missing/field-denied finalization timestamp now says
"Finalization date restricted"; an explicitly null timestamp remains "Not finalized".
That distinction was caught and reproduced during the implementation review.

Posting-link reads now distinguish loading, unavailable, an explicitly confirmed
`NOT_PREPARED` result and an actual native journal/status/line. A failed or malformed
journal-less response never claims an unprepared draft. Displayed posting metadata
must match the selected entry ID. Existing owner error handling, reauthentication,
field denial and read retry remain in place; a 503 retry can recover the posted
journal without issuing a financial command.

## Verification

Failing regressions were confirmed before changes for configured date display,
lookup failure/pending labels, field-denied finalization and the remaining raw
date surfaces in imports, journal review and the books-begin summary.

- Final affected opening lifecycle/UI suites: **137 passed**, 10 test files.
- Reusable opening acceptance replay: **2 passed**. The saved UI probes now assert
  corrected behavior; the Reports probes still reproduce the separate open gaps.
- Current full Console TypeScript check: **one unrelated existing error** at
  `mfes/apps/console/app/vouchers/new/[kind]/page.tsx:61`, where `PHYSICAL_STOCK`
  does not fit an existing kind prop. That route was already modified before this
  task and was preserved. No account-opening type errors were reported.
- Python replay-helper lint/format and scoped whitespace checks pass.

The unit suite covers both configured date patterns, non-English locale,
company timezone conversion, business-date stability, unknown/restricted values,
pending reads, 401/403/422/503 responses, exact unprepared status, unexpected
metadata, selected-entry identity, draft/posted/void journals and read retry.

No native model, migration, API contract, permissions, financial calculations or
posting rules changed. Earlier review MySQL results are retained as earlier
evidence; no new native financial or authenticated browser journey is claimed for
these UI-only fixes. Application/review changes remain local and uncommitted.

## Final review

Reviewed CLAUDE.md correctness/security rules and the shared formatting contract.
No new financial writes, float conversions, field-policy bypass, owner-boundary
change or new CSS/dependency was introduced. Read-only error/pending states derive
from native evidence. The existing private owner routes, company/tenant checks,
immutable revisions, confirmation and correction flows are preserved.

The `/simplify` and `/security-review` slash commands are unavailable in this
session; their relevant review areas were checked manually. The follow-up
restricted-finalization label was fixed and tested. No remaining issue was found
in the account-opening changes, subject to the TypeScript limitation above.

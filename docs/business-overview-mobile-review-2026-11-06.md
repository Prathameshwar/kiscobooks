# Business overview alignment review — 2026-11-06

Status: reviewed and fixed in the local workspace; not deployed.

The user reported excessive wrapping in **Bills by age** and **Who owes you**.
The review used the real OverviewView and ConsoleShell markup, shared styles,
and test-only financial fixtures in Chromium.

## Findings and fixes

| Finding | Fix |
| --- | --- |
| Card headers kept their heading and fixed-width segmented controls on one row. At 390px inside the console shell, Bills by age had about 61px for its heading and Who owes you about 67px. At 320px, both heading columns collapsed to zero width. | Cards at most 28rem wide give the heading a full row and put controls underneath, using the card's width rather than the viewport. At 390px, both headings now have 276px; at 320px, 206px. |
| The desktop sidebar also made cards narrow: at 1152px, Bills by age was about 275px wide despite the desktop viewport. | The same container query handles narrow desktop cards without changing the page grid. |
| Names and ageing labels competed with amounts on narrow list rows. | Labels have room to wrap, and amounts can move to a separate line while retaining their right alignment. Long names remain fully available. |
| Who owes you's footer floated above the bottom of its stretched desktop card. Narrow footer links could also run out of room. | Overview cards use a column layout with the footer at the bottom; footer items and links can wrap. |
| Very large KPI amounts overflowed a 320px page without making their element boxes wider. | KPI text can wrap, preserving the full formatted amount without horizontal page overflow. |

The implementation is scoped to `.janso-overview` in the shared `data.css`.
Shared UI is version 0.1.69. Workspace link resolutions require no lockfile change.
The design system records the behavior and decision 90.

## Verification

- **126 Chromium scenarios passed:** widths 320, 390, 414, 768, 1024, 1152 and
  1440px; populated, empty and long-name/large-amount fixtures; standalone overview
  and actual ConsoleShell; light, dark and ledger themes. Checks covered heading
  space, control placement, footer alignment, content bounds and document overflow.
- The same heading assertion failed against saved markup/styles from before the
  fix at 320px: `Income and expenses: squeezed heading 79.515625`. Before-fix
  measurements also confirmed the reported Bills by age and Who owes you problem.
- **165 unit tests passed:** 46 Company overview, 36 overview period calculations,
  40 ListRow, 23 StatTile and 20 state-component tests.
- Shared UI and Console TypeScript checks passed; task-file `git diff --check`
  passed.
- The existing opt-in overview browser regression suite now covers 320px and
  1152px, long names/large amounts, heading/control separation and footer alignment.
  Its Windows Edge entry point was not executed here; the Chromium checks above
  used rendered local components on the VM with no live application writes.

The local Vitest runner used TypeScript transpilation because this workstation
blocks the normal esbuild subprocess (`spawn EPERM`). Screenshots and browser
measurements are in the ignored `.tools/business-overview-review/` directory.

## Final review

Manual simplification and repository security/correctness review found no further
issues in this scoped change. `/simplify` and `/security-review` commands were not
available. No financial calculation, date formatting, permission check, API,
tenant boundary or posting behavior changed. Browser evidence uses static component
markup; authenticated live-app interaction and Safari were not part of this review.

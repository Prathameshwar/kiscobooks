# Trial Balance workspace UI review — 2026-11-02

Reviewed `/reports/workspace?report=TRIAL_BALANCE` and refined its existing shared styles in one focused change.

- Closing balances show debit and credit together at 320px and 390px for ordinary account names and amounts; larger content retains the bounded table scroll.
- Numeric column headings align with their figures. Account codes align beneath account names, and grand totals have a stronger separating rule.
- Layout choices, reporting period and the balanced status share a clear surface. Colours, spacing and dimensions use the existing design tokens.
- The toolbar wraps on narrow screens and preserves the complete export-scope label at 320px; the detailed layout offers a horizontal-scroll hint on phones and tablets.
- Touch devices get 44px-high hierarchy actions. Escape closes the filter panel, returns focus to its trigger and preserves edited dates.

Validation: 99 console tests and 331 shared UI token, contrast and class-coverage tests passed. `pnpm.cmd exec tsc --noEmit` and the scoped `git diff --check` passed. The new Escape regression was confirmed failing before the fix; the browser alignment regression was also confirmed failing before the CSS change.

Browser review uses the rendered component with mocked report responses, the console's actual stylesheet import order and its self-hosted font. Both layouts, filters open/closed, all three themes, 1440/768/390/320px, long unbroken account names, keyboard focus, 200% zoom and touch sizing passed. Screenshots are in `.tools/trial-balance-review/`, including `trial-balance-toolbar-1440.png`, `trial-balance-toolbar-390.png` and `trial-balance-toolbar-320.png`.

Manual simplification, security and correctness review found no new issues in scope: permissions, company/actor ownership, financial calculations, display formatting, signed drilldowns and exports retain their existing behavior. The `/simplify` and `/security-review` commands are unavailable in this environment, so their review checks were performed manually. Existing React `act(...)` warnings appeared in the unrelated ReportSources tests; those tests passed.

No new dependencies or shared tokens were introduced. Existing unrelated workspace changes were preserved. No commit or publication was requested.

# Advanced product guidance and progress

Local changes only; no VM update.

Quick findings: Profile/SKU terminology needs a concrete explanation; progress is a plain text list; status and waiting messages expose implementation terms and command keys; readiness errors expose raw paths; SKU opening states need readable labels; completion needs clear confirmation and focus.

- [x] Clarify step guidance, variant examples and opening-stock instructions.
- [x] Add styled, server-confirmed milestones and individual SKU status with understandable waiting/retry messages.
- [x] Test pending, resumed, failed and completed creation; review accessibility, responsive CSS and unchanged save/posting contracts.

## Fixes

- Explain shared Profile details and SKU versions with concrete size/pack examples. Each step states what to enter and what happens next.
- Clarify opening stock as stock held when books begin, with a separate quantity and valuation cost for each SKU.
- Explain that published settings come from the company and Product Type. Simplify creation and correction instructions.
- Show a prominent animated progress panel with confirmed Profile/SKU, setup, price, activation, opening and readiness stages. No simulated percentages. Missing or mismatched SKU receipts do not count as completed setup.
- Show a responsive card for every SKU with readable setup, selling-price, activation and opening status. Skipped openings explicitly say no opening stock was requested.
- Explain automatic waiting, keep internal command keys out of messages, and describe readiness blockers using the appropriate wizard step and SKU name.
- Keep draft save/open and pre-creation checking messages distinct. Completion receives a success panel and focus; stale failure messages disappear after confirmed completion.
- Reuse the shared progress component and theme tokens. Shared UI version is 0.1.74; workspace link dependencies need no lockfile version change.

## Verification

- Initial regression run: two expected failures for missing Profile/SKU guidance and missing styled pending progress; six existing tests passed.
- Final Advanced suites: **59 passed, 4 browser tests skipped** across 14 files. Final wizard rerun after copy correction: **5 passed**.
- Shared progress and layout suites: **10 passed**.
- Console TypeScript and changed-file whitespace checks: **passed**.
- Regression coverage includes partial/missing SKU receipts, every progress phase, unknown readiness codes, readable stock states, same-key automatic waiting and explicit retry, editable-step recovery, draft saving and focused completion.
- Manual simplification and security/invariant review: no new findings. Save, company validation, command keys, native activation, opening posting, recovery locks and decimal calculations remain unchanged. Only presentation and busy-operation labels changed.
- Browser geometry and live visual verification remain open because of this workstation's browser process restrictions. CSS contracts check wrapping and responsive sizing; they do not constitute visual sign-off.

Local fixes and executable checks are complete. No VM access/update, deployment, commit or publication performed.

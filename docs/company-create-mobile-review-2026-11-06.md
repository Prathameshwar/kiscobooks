# Company creation mobile review — 6 November 2026

**Status:** fixes implemented locally and verified. The findings below describe the
original behavior; the implementation and results are recorded at the end.

The reported layout problems are confirmed. Presentation can hide Next horizontally;
the final Create action can be clipped with enlarged text; short viewports also expose
limits in the sticky footer.

## Scope and evidence

Reviewed the current working-tree `CompanyWizard`, shared `WizardLayout`, and all CSS
loaded by the console layout. Rendered all six real step components with the existing
India/company test fixtures, then measured the resulting HTML in headless Chromium.
Application code, company records, and the deployed application were not changed.

Tested 320×568, 360×640, 390×844, 414×896, 390×390, 768×1024, and 1440×900.
Measured at the top, after focusing the step heading, and at the bottom of the wizard's
scroll container. Also tested 320×568 with the root font increased from 16px to 20px.
The short-height case represents reduced available space; it is not a physical-device
keyboard test. These are browser layout checks of rendered components, not a live
authenticated end-to-end creation run.

## Confirmed findings

### 1. High: Presentation expands beyond the phone and clips Next

On step 5, `.janso-preview__grid` requires a minimum track width of `20rem` (320px)
inside a padded preview and card. Its minimum content width expands the containing
form. `.janso-setup` hides horizontal overflow, so the expanded content is clipped.

At all four tested portrait phone widths, Next occupies x=356–420px. It is entirely
outside a 320px viewport and partially outside 360px, 390px, and 414px viewports.
Scrolling to the bottom does not recover it. Several field edges are clipped too.

Source: `mfes/packages/ui/src/styles/janso-ui.css:940`;
`mfes/packages/ui/src/styles/setup.css:22`;
`mfes/apps/console/app/components/CompanyWizard.tsx:1127`.

Diagnostic verification: changing only the preview track minimum in the browser to
`min(100%, 20rem)` restored all checked controls and Next within each phone width.
No application CSS was edited.

Evidence: [390px Presentation screenshot](../.tools/company-mobile-review/step-5-390x844-bottom.png).

### 2. Medium: Create and longer setup actions cannot fit on narrow screens

The action bar is a flex row without wrapping, and shared buttons use
`white-space: nowrap`. At 320px with a 20px root font, the step 6 Create button ends
at x=339.66px, clipping its right edge. It fits at the default font size in the normal
six-step fixtures; the Create problem is conditional, not universal.

The existing post-creation action combinations have the same limitation. With their
real labels placed in the shared footer at 320px and the default font size:

| Action combination | Last button's right edge |
| --- | ---: |
| Leave for now + Retry the remaining steps | 380.34px |
| Leave for now + Open while setup continues | 392.34px |
| Edit company details + Leave for now + Retry the remaining steps | 574.45px |

Those combinations were checked as footer layout scenarios, without submitting a
creation request or simulating backend failures.

Source: `mfes/packages/ui/src/styles/setup.css:35`;
`mfes/packages/ui/src/styles/janso-ui.css:531`;
`mfes/apps/console/app/components/CompanyWizard.tsx:723`.

Diagnostic verification: allowing the footer to wrap in the browser restored the
enlarged-text Create button. The header still overflowed at that font size, so footer
wrapping alone would not resolve every enlarged-text layout issue.

Evidence: [Create with enlarged text](../.tools/company-mobile-review/step-6-320x568-font20-bottom.png).

### 3. Medium: Sticky actions can begin below the visible screen

The mobile layout puts the full six-step navigation, heading, description, and
breadcrumbs before the form. The sticky action bar is inside that form and cannot
move above its containing block.

At 320×568 and scroll position zero, steps 2, 3, 4, and 6 have actions extending below
the viewport. On step 6, Create spans y=565.19–601.19px, leaving only about 3px visible.
At 390×390, all six steps begin with actions below the viewport.

Vertical scrolling restores these actions on steps other than Presentation, whose
horizontal clipping is independent. Heading focus alone does not restore the actions
on the affected 320×568 steps. The existing sticky rule therefore does not guarantee
that Next/Create remain visible throughout the mobile flow.

Source: `mfes/packages/ui/src/components/WizardLayout.tsx:145` and `:161`;
`mfes/packages/ui/src/styles/setup.css:53` and `:102`.

## Recommended correction scope

Make the preview respect its available width, make the form and footer tolerate
narrow widths and enlarged text, and adjust the mobile progress/header arrangement
and footer containment so the actions remain reachable on short screens. Verify
all six steps, registration branches, enlarged text, and preparation/retry states.

Raw browser measurements, screenshots, and reproduction helpers are under
`.tools/company-mobile-review/`. The standard Vitest command was attempted but could
not start because esbuild's subprocess returned `spawn EPERM` in this environment.
The browser measurements above completed through the saved VM SSH profile after
confirming host `srv2111154` and user `root`.

## Fix implementation and verification

`WizardLayout` now uses one viewport-sized form with a scrolling content row and a
separate footer row. Next/Create and preparation/retry actions retain their actual
height, wrap within the available width, and include bottom safe-area padding.
The masthead can wrap, narrow-screen cards have smaller token-based padding, and
feature text can wrap without widening the form.

The preview grid's minimum is capped to its available width. Preview values can wrap
inside their rows. The former sticky-footer rules and guessed clearance were removed.
The shared UI package is version 0.1.68; its consumers use workspace links, so this
version change does not alter their lockfile dependency resolutions. The design-system
contract and decision 89 document the viewport/footer structure.

Verification:

- **227 browser scenarios passed:** all six steps, India and UK registration entry,
  and creation failure/retry across eight viewport sizes and all three themes; also
  narrow short screens with enlarged text and the longer preparation action labels.
- Primary actions remain within the viewport and pass hit testing before heading
  focus and after scrolling. Controls remain inside the available width; the footer
  does not move while the fields scroll. Browser checks also confirm both a footer
  click and Enter in a field submit the same form.
- **76 unit tests passed:** 43 company creation tests and 33 shared wizard, layout,
  and field tests. A local Vitest runner used TypeScript transformation and worker
  threads to avoid the restricted esbuild subprocess, with jsdom browser storage and
  cleanup restored for this workstation's Node version.
- Added `wizard-layout.browser.test.tsx`, gated by `QA_WIZARD_BROWSER=1` for machines
  with Playwright installed. The default unit run skips that optional browser test;
  the actual company browser assertions above ran through the confirmed VM profile.
- Shared UI and console TypeScript checking passed. Simplification review removed the unused
  sticky selectors. Security and audit review found no changed authorization, tenant,
  financial, or audit behavior; company creation requests/defaults remain covered by
  the existing tests. No deployed application or company records were changed.

After-fix evidence: [Presentation at 390px](../.tools/company-mobile-review/fixed-step-5-390x844-light-bottom.png)
and [Create at 320px with enlarged text](../.tools/company-mobile-review/fixed-step-6-320x390-font20-bottom.png).
Raw results are in `.tools/company-mobile-review/fixed-results.json`.

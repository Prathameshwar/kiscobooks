# Sidebar company overflow review

The company switcher could grow to 509.23px inside the 248px rail when its company
name was long. The browser regression reproduced this before the fix.

Nested switcher grids now use `minmax(0, 1fr)`, and the trigger can shrink below
its content width. The text column fills the remaining space while preserving
the avatar and chevron. Both company names and codes truncate with ellipses;
their full text remains in the DOM and is available on hover, including in the
company picker. The collapsed trigger also has a full company tooltip.

The compact rail width is now `4rem` (still 64px at the default font size). It
scales with enlarged text so initials and padding remain inside the rail.
`@janso/ui` is bumped to 0.1.57; both application lock entries continue to use
the workspace link, which pnpm verified without a lockfile change.

Validation: 52 shared shell/switcher tests, 40 Console shell/context tests, and a
browser regression covering 216 combinations: spaced and unbroken long names,
long codes, six viewport widths (1440, 1024, 961, 960, 390, 320), three themes,
16px/32px root font sizes, and expanded/collapsed state. The browser uses the
actual Console CSS import order and self-hosted Inter font. Six desktop/mobile
screenshots are saved in `.tools/sidebar-company-ui-review`; representative
screenshots were visually inspected.

Manual simplification and security/invariant review found no remaining issues:
the changes are presentation only, names remain React-escaped, and company
selection, permissions, tenant scoping and financial operations are unchanged.
The slash review commands are not exposed in this session, so this records the
manual equivalent. Shared UI and Console TypeScript checks passed.

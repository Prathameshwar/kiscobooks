# Platform console UI consistency — todo

Scope: make back navigation identical at every depth under platform administration, and make
every create/edit surface share one layout. UI only; no API, permission or money behaviour
changes.

## Phase 1 — shared primitives in `@janso/ui`

- [x] `PageNavigation` accepts `onNavigate`, applied to the back link **and** every breadcrumb
      link, so a page with an unsaved draft confirms once however the reader leaves.
- [x] New `FormLayout` — the split form/aside grid, so the "form card plus context card" shape
      is a mechanism rather than four hand-copied grids.
- [x] New `FormActions` — the card footer with a cancel link on the left and the committing
      action on the right; refuses an unsafe cancel destination rather than rendering a dead
      link.
- [x] `FieldGrid` renders a `<fieldset>` when given `disabled`, which is what let the platform
      pages stop hand-writing the stacked-field class.
- [x] `.janso-form-layout` and `.janso-form-actions` styled in `janso-ui.css`.
- [x] Exported from `src/index.ts`; `tests/form-layout.test.tsx`, plus new cases in
      `page-navigation.test.tsx` and `wizard-layout.test.tsx`.

## Phase 2 — back navigation parity

- [x] `TenantForm` (`/platform/tenants/new`, `/platform/tenants/[id]/edit`) replaced its bare
      text link with `PageNavigation`; editing carries the four-level trail
      `Platform administration / Tenants / {tenant} / Edit tenant`.
- [x] `PlatformDetailsForm` (`/platform/details`) the same.
- [x] `TenantForm` history link moved above the header, where the directories put theirs.
- [x] `ReferenceRecord` back chevron and crumbs now confirm a discard too.

## Phase 3 — create/edit layout parity

- [x] `TenantForm` and `PlatformDetailsForm` on `FormLayout` / `FormActions`.
- [x] `ReferenceRecord` on the same split layout, with the context card it lacked.
- [x] `AccountDetail` off `janso-setup__fields` / `janso-setup__actions` onto `FieldGrid` and
      `FormActions`, which also puts Cancel before the committing action instead of after it.
- [x] `TenantDirectory`'s drawer uses `ReviewList` rather than its own definition list.

## Phase 4 — reference catalogs move under platform

- [x] `/settings/[catalog]` → `/platform/references/[catalog]` (plus `new`, `[code]`,
      `[code]/edit`), so the breadcrumb trail and the URL agree. These pages always declared
      `activeHref="/platform"`; the old path also put a dynamic segment beside the real
      company-settings children, where a future `/settings/<word>` page would have collided.
- [x] `catalogReturnTo`, the platform landing cards and the three reference test files
      updated.

## Phase 5 — notification editor chrome

- [x] The modal editor in `components/notifications/common.tsx` disables its fields as a group,
      orders Cancel before Save, and uses the routed editors' wording and shared action class.

## Deferred, with reason

- Converting the notification modal editors into routed create/edit pages. It needs roughly
  fifteen new routes and a rewrite of `notification-navigation`'s route validation — a change
  of its own size and risk rather than part of this consistency pass. The chrome inside the
  modal now matches the routed forms, so the remaining difference is the modal itself.

## Also fixed along the way

- `ReferenceRecord` showed a mojibake loading message (`Loading reference detailsâ€¦`) and a
  literal `?` where an em dash had been lost. Both were user-visible.

## Closing

- [x] `pnpm --filter @janso/ui test`, `pnpm --filter console test`, typecheck and lint.
      Note: the console suite times out under full file parallelism on this machine; run it
      with `--no-file-parallelism --testTimeout=20000` for a trustworthy result.

---

## Dark-mode structural visibility — Tier 1 (2026-10-23)

Separate concern, same work stream: the landing and administration pages read as one
undivided surface in dark mode. Full reasoning and measurements are in
[design-system.md](design-system.md)'s decision log.

- [x] Dark `--janso-line` `#25272e` → `#43474f`. Was 1.23:1 on a card, under light's own
      hairline, with the card shadow at 1.03:1 against the page behind it. Now 1.97:1 on
      `surface`, 2.09:1 on `paper`, 1.87:1 on `surface-2` — the rail, which is the binding
      surface.
- [x] `.janso-action-card` and `.janso-page-navigation__back` draw with
      `--janso-control-line`. Both are links drawn as outline controls, so WCAG 1.4.11 owes
      their edge 3:1; both had used the decorative rule.
- [x] Dark `--janso-grad-panel` lifts (`#1b1d23 → #15171c`) instead of descending toward the
      page, where it had ended at 1.01:1 — the lower edge of every ActionCard.
- [x] Three tests in `contrast.test.ts`: the 1.8 floor on all three dark surfaces, the
      gradient's direction against `paper`, and a CSS-text assertion naming
      `--janso-control-line` on those two edges. The first caught an intermediate value
      (`#3d4149`) landing at 1.70:1 on the rail.

## Tier 2 (2026-10-23)

- [x] Dark `--janso-shadow-card` gains `inset 0 1px 0 rgba(255, 255, 255, 0.08)` — a lit top
      edge at 1.23:1 inside the 1.97:1 border, because the cast half measures 1.03:1 against
      the page. The alpha stays under `--janso-shadow-action`'s 0.12 so
      `.janso-btn--primary:active`, which swaps one token for the other, still reads as
      pressed.
- [x] Two tests in `contrast.test.ts`: the lit edge exists and clears 1.2:1 while the cast half
      is confirmed useless (the premise), and the card's inset alpha stays below the button's in
      every palette that lights both. Both were mutation-checked — deleting the inset fails the
      first, raising it to 0.12 fails the second.
- [ ] ~~Lifting dark `--janso-surface` clear of `--janso-paper`~~ — **dropped, not deferred.**
      `--janso-line-strong` has 0.01 of slack against its 3:1 gate on that surface, so a lift
      needs it re-tinted; and the payoff is 1.06:1 → 1.09:1 (1.12:1 if the page is darkened
      too). Light mode's own card is 1.07:1 against its page, so fill is not what separates a
      surface in this system in any palette — the line and the elevation cue are, and both are
      now fixed. Reasoning is in the design-system decision log so it is not re-proposed from
      scratch.

### Left alone, with reason

The rail's active item is a weak cue by fill — the selected pill is 1.06:1 against the rail and
actually recedes in dark — but a 2px brand marker bar, a brand-coloured icon and full-strength
ink carry it. It only looked broken next to the invisible cards.

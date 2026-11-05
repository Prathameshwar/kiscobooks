# Design system — tokens, themes, components

Governs everything visual in `mfes/`. **This doc is the contract**: a token name, a component
name or a prop that isn't here doesn't exist. Code contradicting this doc is the thing that's
wrong ([CLAUDE.md](../CLAUDE.md) §1).

Scope: `mfes/packages/ui` (`@janso/ui`) — the shared design system — and the rules every MFE
in `mfes/apps/` follows when consuming it.

The displayed product is **KiscoBooks**, published by **Khushiyan Enterprise**.
`Wordmark` renders adjacent Kisco and Books text, with no intervening space or wrap:
Kisco uses `--janso-brand-ink` (indigo), Books uses `--janso-wordmark-books` (green,
balanced books). Both inks meet the 4.5:1 text gate on the auth panel gradient and
shared surfaces in all three themes, including the strongest auth-panel glow.
The Books token is a brand colour and leaves existing success/status colours intact.
`JansoMark` and the existing SVG filenames
remain internal implementation names; their accessible default label is KiscoBooks.
Branding does not replace the signed-in tenant's organisation or company name.

---

## 1. Where things live

```
mfes/packages/ui/src/
  styles/
    tokens.css          non-colour tokens only — type, space, radius, motion, z-index, layout dims
    theme-light.css     [data-theme="light"]  { … }   the default
    theme-dark.css      [data-theme="dark"]   { … }
    theme-ledger.css    [data-theme="ledger"] { … }   warm paper
    janso-ui.css        base + form/button/text primitives, including select, phone and strength
    theme.css           the theme switcher
    shell.css           app shell — rail, top bar, footer, chips, avatars, menus
    data.css            cards, stat tiles, list rows, badges, meters, tabs, toolbars, states
    search-select.css   the entity-lookup field and its portalled list
    file-upload.css     the drop zone, its rejection notice and the attachment list
    chart.css           chart chrome — frame, gridlines, axis, annotations, legend
    overlay.css         portalled layers — menus, the confirm dialog, their scrim
    table.css           the list surface — table, sort headers, chips, pager, bulk bar, detail rows
    controls.css        the segmented choice, shared by the designer inspector and form pages
                        (`SegmentedControl showLabel` prints its question at form scale)
    entry.css           the document entry surface — bar, line grid with pinned columns, totals
                        rail, action bar; loaded by the voucher entry routes only
  components/           React primitives
  lib/                  format, theme resolution, no-DOM helpers
```

**The rule that makes three themes tractable: every stylesheet except `theme-*.css` — and every
app stylesheet — contains zero colour values.** No hex, no `rgb()`, no `hsl()`, no named colour —
every colour reads a `--janso-*` token. The only exceptions, and the reason for each:

| Exception | Why |
|---|---|
| `theme-*.css` | These *are* the colour values |
| `JansoMark.tsx` | The logomark is a self-contained SVG that carries its own gradient, so it needs no context and two instances can't cross-paint. The white-stroked indigo tile reads on all three surfaces — the brand is deliberately theme-invariant |
| `icons.tsx` Google / Facebook glyphs | Mandated third-party brand colours |
| `currentColor` | Not a colour value — the correct way for icons to inherit |

A test enforces this (§8).

---

## 2. Themes

### 2.1 The four preferences, the three palettes

The user preference is one of **four** values; the *resolved* palette is one of **three**.

| Preference | Resolves to | Switcher icon |
|---|---|---|
| `light` | `light` | sun |
| `dark` | `dark` | moon |
| `ledger` | `ledger` | contrast |
| `system` | `dark` when `prefers-color-scheme: dark`, else `light` | monitor |

`system` is the default when no preference is stored. `ledger` is warm paper with a warm
near-black ink — the ruled-account-book vernacular, for people who read figures all day. It is
a distinct palette, not a variant of `light`.

The resolved palette is applied as `data-theme` on `<html>`, alongside a matching
`color-scheme` so native form controls, scrollbars and the browser's own chrome follow:

```html
<html data-theme="dark" style="color-scheme: dark">
```

**The preference is stored; the resolved value never is.** Storing `dark` for a user who chose
`system` would freeze them out of the OS following them to a different machine.

### 2.2 Resolution and persistence

Precedence, highest first:

1. `user.theme` from the session ([identity-schema](identity-schema.md) §*Preferences*) — the
   durable, cross-device preference
2. `janso-theme` cookie — what makes server-rendered HTML correct on the first paint
3. `janso-theme` in `localStorage` — survives when cookies are cleared per-session
4. `system`

Writing a preference updates the DOM attribute, the cookie, `localStorage`, and — when
authenticated — the user record. `system` additionally subscribes to
`matchMedia('(prefers-color-scheme: dark)')` so an OS switch repaints live, with no reload.

**No flash of the wrong theme.** A synchronous inline script in each app's root layout sets
`data-theme` and `color-scheme` before first paint, reading the cookie then `localStorage`.
`ThemeProvider` hydrates from the same sources, so server and client agree. The script is
exported as a string from `@janso/ui` (`themeScript`) so it can't drift from the provider.

### 2.3 Allowed values are a shared catalogue

`user.theme` is `VARCHAR(20)` + app validation ([CLAUDE.md](../CLAUDE.md) §4 — never a MySQL
`ENUM`). The accepted set is **`light` · `dark` · `ledger` · `system`**, and both the web and
`identity` validate that same list. `@janso/ui` exports it as `THEME_PREFERENCES` so the web
side has one source; the API-side catalogue must match.

Theme is **presentation only**. It is user-overridable, never company-level, and never
immutable — unlike `amount_precision` / `rounding_mode`, it cannot change a computed total
([identity-schema](identity-schema.md) §*Preferences*).

### 2.4 What each palette must satisfy

- **Body text ≥ 4.5:1** against the surface it actually sits on. This includes small text that
  is easy to wave through as decoration — placeholders, hints, footnotes, rank numbers, the
  letterspaced overlines, chart tick and annotation labels. If it carries meaning, it is text.
- **Large text ≥ 3:1** — that is ≥ 24px, or ≥ 18.66px bold. On this type scale only
  `--janso-figure-lg` and `--janso-figure-sm` qualify; `--janso-text-sm`, `-xs` and
  `--janso-text-overline` do **not**.
- **The boundary of an interactive control ≥ 3:1** — an empty input, an unchecked checkbox and
  an outline button are defined entirely by their edge, so they read `--janso-control-line`,
  not the decorative `--janso-line`. **What makes this apply is being interactive, not being
  small**: an `ActionCard` is an `<a>` and the `PageNavigation` back chip is a link drawn as an
  outline control, so both take `--janso-control-line` too, however card-shaped they look. This
  is still narrower than "every boundary": a list separator, a card footer's rule and a header
  divider are container decoration, are not gated by WCAG 1.4.11, and stay quiet hairlines —
  ~1.2:1 in light and ledger, where a shadow does the lifting, and ~1.9:1 in dark, where it
  cannot.
- **The focus indicator ≥ 3:1** against every surface it can land on. A translucent halo alone
  does not reach it, which is why `--janso-focus-ring` is a solid 2px ring in `--janso-focus`
  plus a halo — `outline: none` is only allowed with a replacement that is genuinely visible.
- **Meaningful graphics ≥ 3:1** — a chart's zero line and its series colours carry data. Its
  gridlines do not, and stay recessive on purpose.
- Every signal reads without colour alone — always paired with an icon or a label.
- All three palettes define the **identical token key set** (§3). A missing key is a test
  failure, not a silent fallback to an inherited light value.
- Elevation is a light-theme idiom: a drop shadow on near-black is invisible. So `dark` raises
  `--janso-line` relative to its own surface, lifts `--janso-overlay` clear of `--janso-surface`,
  and gives popovers a real edge at 3:1 against `--janso-overlay` (`--janso-overlay-line`) —
  rather than reaching for a bigger shadow that would not render. In light and ledger the same
  token is a quiet hairline, because there the shadow does lift the surface.
- **In dark, `--janso-line` carries a floor of 1.8:1 against `--janso-paper`, `--janso-surface`
  and `--janso-surface-2`.** The bullet above was true as intent and false as a number for a
  long while — the token shipped at 1.23:1, under light's own hairline, with
  `--janso-shadow-card` measuring 1.03:1 against the page behind it, so a card had no
  perceptible boundary at all. The gate is 1.8 and not 3 because this token is also every table
  row divider; 3:1 belongs to `--janso-line-strong` and `--janso-control-line`.
- **A dark fill never descends toward `--janso-paper`.** `--janso-grad-panel` once ran
  `#14151a → #0e0f12` on a `#0c0d10` page, so an `ActionCard` faded to 1.01:1 at its lower edge,
  where its call to action sits. Fill cannot carry separation on near-black — the line does
  that — but a surface reaching for the page colour cancels the line's work.
- **A dark elevation cue is an inset lit edge, never a drop shadow.** `--janso-shadow-card`'s
  cast half measures 1.03:1 against the page in `dark`, so the token also carries
  `inset 0 1px 0 rgba(255, 255, 255, 0.08)` — 1px of light along the top, inside the border,
  reading with the line rather than instead of it. The alpha stays **below**
  `--janso-shadow-action`'s, because `.janso-btn--primary:active` swaps one token for the other
  and a pressed button has to stay lit less than a resting one. Both halves and that ordering
  are tests.
- **Fill is not how a surface separates, in any palette.** A card is `1.07:1` against the page
  in light and `1.06:1` in dark; what separates it is the border and the elevation cue. Dark's
  ceiling here is `1.12:1` even after re-tinting, so "lift the dark surface" is not a fix for a
  card that cannot be seen — a visible line and a lit edge are.

Each of these is a test (§8), not an assertion. The first version of this section claimed
ratios the palettes did not meet.

---

## 3. Token contract

**The typeface is loaded, not just named.** `@janso/ui/styles/fonts.css` declares a
self-hosted Inter Variable and every app imports it before `tokens.css`. The tokens named
Inter from the day they were written and nothing ever fetched it, so the console rendered in
whatever came next in the stack — Segoe UI on Windows, `system-ui` elsewhere — while
`janso-ui.css` applied letter-spacing and `font-feature-settings` calibrated for a face that
was not present. Self-hosted rather than a CDN: this is on-premise software, an installation
with no route to a font host must not fall back, and a third-party request per page load is a
privacy detail nobody asked for. One variable file covers the 100–900 range; the italics are
a second file and nothing here uses them.



### 3.1 `tokens.css` — non-colour, theme-invariant

| Group | Tokens |
|---|---|
| Font | `--janso-font-display` · `--janso-font-body` · `--janso-font-mono` |
| Type | `--janso-text-overline` `-xs` `-sm` `-base` `-md` `-lg` `-xl` `-2xl` · `--janso-figure-sm` `--janso-figure-lg` |
| Space | `--janso-space-1` … `--janso-space-8` |
| Radius | `--janso-radius-sm` (6px, controls) · `-md` (10px, cards, menus, dialogs) · `-pill` |
| Motion | `--janso-dur-fast` · `--janso-dur` · `--janso-ease` |
| Layout | `--janso-rail-w` · `--janso-rail-w-collapsed` · `--janso-topbar-h` (rem — a px band clips its own text when the default font size is raised) · `--janso-page-gutter` · `--janso-page-max` |
| Z-index | `--janso-z-topbar` · `-rail` · `-scrim` · `-drawer` · `-popover` · `-tooltip` |

`--janso-font-mono` is a **system** stack — no second webfont for the sake of a `USD` badge.
Display and body share one family, **Inter** (variable, `opsz` 14–32): its optical-size axis
gives headings the tighter display cut without a second face. Body copy is 14px
(`--janso-text-base`) with `-0.006em` tracking; figures are tabular everywhere.

Cards, menus and dialogs use `--janso-radius-md` (10px); controls use `--janso-radius-sm`
(6px). Auth and console share both, so they still read as one product (decision 70).

**Labels are sentence case.** Overlines, rail group names, stat-tile labels and table headers
are set at `--janso-text-xs` / `-sm`, weight 500, untracked — never uppercase-and-letterspaced.
The selected rail item is a raised neutral surface with the brand on its icon and leading marker;
the selected tab is full ink over a brand underline. Brand colour is spent on the primary action,
links, focus and selection markers — not on large fills.

### 3.2 Colour — every key below exists in all three theme files

**Surfaces**

`--janso-paper` page · `--janso-surface` card · `--janso-surface-2` tile nested inside a card ·
`--janso-overlay` menu/popover/drawer · `--janso-panel` `--janso-panel-2` brand panel ·
`--janso-hover` `--janso-active` `--janso-selected` interaction states ·
`--janso-disabled-surface` `--janso-disabled-ink` · `--janso-scrim` drawer backdrop

**Ink**

`--janso-ink` · `--janso-ink-soft` · `--janso-ink-faint` · `--janso-ink-invert` (text and glyphs
on a brand fill — replaces every hardcoded `#fff`)

**Brand**

`--janso-brand` · `--janso-brand-strong` · `--janso-brand-bright` · `--janso-brand-ink` (ink on
a brand tint) · `--janso-brand-tint` · `--janso-brand-line` · `--janso-brand-glow` (the one
translucent value, for radial depth washes)

**Lines**

`--janso-line` (the decorative rule: cards, separators, dividers) ·
`--janso-line-strong` (a firmer rule — totals, a dashed empty state) ·
`--janso-overlay-line` (the edge of every popover, menu, dialog, drawer and toast: a hairline in
light and ledger, ≥ 3:1 on `--janso-overlay` and `--janso-paper` in dark — decision 72) ·
`--janso-control-line` (the edge of an interactive control — inputs, checkboxes, outline
buttons, the theme-switcher group; ≥ 3:1 against every surface, per §2.4)

**Signals — each is a triplet, and they are always used as a triplet**

`--janso-success-{ink,tint,line}` · `--janso-warn-{ink,tint,line}` ·
`--janso-danger-{ink,tint,line}` · `--janso-info-{ink,tint,line}` ·
`--janso-neutral-{ink,tint,line}`

> This triplet *is* the reference's grammar: a tinted surface with a matching border and
> coloured ink. Coloured text on a plain surface is not a status — the emphasized KPI tile, the
> amber count badge and the warning list rows are all one primitive with a different triplet.

**Gradients** — slight, single-hue, only on brand surfaces and the primary action

`--janso-grad-mark` · `--janso-grad-action` · `--janso-grad-action-press` · `--janso-grad-panel`

**Focus**

`--janso-focus` · `--janso-focus-ring` · `--janso-focus-ring-danger`

**Elevation**

`--janso-shadow-action` · `--janso-shadow-card` · `--janso-shadow-popover` ·
`--janso-shadow-inset-mark`

**Components with no other home**

`--janso-meter-track` · `--janso-meter-fill` · `--janso-spinner-track` · `--janso-spinner-head`

**Charts**

`--janso-chart-1` … `--janso-chart-8` (ordered categorical — series 1 is the primary) ·
`--janso-chart-grid` · `--janso-chart-axis`

Chart colours are a palette, not eight arbitrary hues: ordered by prominence, and
**measured** rather than asserted. Series colour is assigned by index, never by hue-picking at
the call site.

Each palette clears these gates, per theme, and the numbers are recorded in the theme file:

| Gate | Light | Dark | Ledger |
|---|---|---|---|
| Worst adjacent pair, deuteranopia/protanopia (≥ 8.0 ΔE) | 10.7 | 8.6 | 10.7 |
| Worst adjacent pair, normal vision (≥ 15 ΔE) | 18.9 | 18.9 | 18.9 |
| Every slot vs its surface (≥ 3:1) | pass | pass | pass |
| OKLCH lightness band · chroma floor | pass | pass | pass |

**Re-run the validator before changing any chart token** — colour-blind separation is
computable, so it gets computed rather than eyeballed:

```
node scripts/validate_palette.js "<the eight hexes>" --mode light --surface "#ffffff"
```

The palette is deliberately muted. One that passed by being neon would clear the gate and
still be wrong for this product.

---

## 4. Layout

### 4.1 The shell — one grid, one scroll container

The rail spans full height (the brand lockup sits in the same band as the top bar). **Only
`main` scrolls**, so the rail and top bar never move.

```
.janso-shell    display:grid; height:100dvh
                grid-template-columns: var(--janso-rail-w) 1fr
                grid-template-rows:    var(--janso-topbar-h) 1fr

.janso-rail     col 1 / rows 1–3    inner rows: auto auto 1fr auto
                                    brand · org switcher · nav (own scroll) · pinned footer
.janso-topbar   col 2 / row 1       collapse … context · role · theme · bell · user
.janso-main     col 2 / row 2       overflow-y:auto — the only scroller
```

The scroll region is a flex column containing the `main` landmark and its sibling
`AppFooter`. The content grows to fill unused space, placing the footer at the
bottom on short or empty pages. Long content retains its natural height, with the
footer following it in the same scroll region. The footer does not cover content
or reserve a permanently visible band; this behavior is shared by every AppShell page.

Product section links and related actions scroll their target within `.janso-main`
and focus it with `preventScroll`. They must not use document-wide `scrollIntoView`,
which can scroll hidden ancestors and move the entire shell above the viewport.

Collapsed rail: `data-collapsed` on the shell narrows column 1 to
`--janso-rail-w-collapsed`, hides labels, keeps icons, and exposes each label as a tooltip and
as the button's accessible name.

Under **960px** the rail leaves the grid and becomes an off-canvas drawer over a scrim; the
top bar's context and role chips fold into the user menu.

### 4.2 A page

```
PageHeader        overline · h1 · lede
Tabs              underline, role="tablist", hairline rule beneath
                  (the same strip serves routed area links — see `Tabs` in §5.3)
SectionHeader     brand overline · icon + h2 · description
Toolbar           left: labels + badge      right: range · refresh · overflow · Filters
meta line         muted, tabular
StatRow           4 × StatTile — exactly one emphasized
Grid --split      minmax(0,2fr) / minmax(0,1fr)
AppFooter         icon links · copyright
```

Content is fluid with `--janso-page-gutter`, capped at `--janso-page-max` for ultrawide.

Masters and Reports use `janso-action-card-grid--compact`: equal-height cards using
`--janso-action-card-compact-height` (17rem), with responsive columns starting at
`--janso-action-card-compact-min` (16rem). `auto-fill` preserves column widths across
short sections and search results. Smaller screens fit a single card to the available
width. The default ActionCard grid remains available for other landing pages.

Breakpoints: `--kpi` 4-up → 2-up at 1100px → 1-up at 680px. `--split` stacks at 1100px.

### 4.3 Vertical rhythm

**Spacing between page blocks is stated per relationship, not as one uniform gap.** A single
`gap` on the column puts a toolbar as far from the section heading it belongs to as from an
unrelated block, and it compounds with any margin a block already carries — which is how the
first version of this page ended up with an arbitrary-looking ladder of white space.

`.janso-page` and the `.janso-flow` utility are columns, and the spacing comes from margins on
adjacent siblings, so there is exactly one mechanism and nothing stacks:

| Adjacency | Space | Why |
|---|---|---|
| default, block to block | `space-6` | two unrelated blocks |
| anything → `SectionHeader` | `space-7` | a new section is a bigger break |
| `SectionHeader` → anything | `space-4` | a heading introduces what follows it |
| `PageHeader` → `Tabs` | `space-5` | the strip filters the header, not the content below |
| `Toolbar` → `.janso-meta` | `space-2` | the meta line captions the toolbar's selection |
| `.janso-meta` → anything | `space-5` | the header block closes, the content field begins |
| card band → card band | `space-4` | matches the grid's own gutter, so vertical equals horizontal |

Use `.janso-flow` for any nested column of blocks — the console's `role="tabpanel"` carries it
rather than restating the column, which is what let the two drift apart.

Opt in to `.janso-card--compact` through `Card.className` when guidance, actions and
history belong to one card. Its body uses `space-3` above and `space-4` below, retaining
the usual `space-5` horizontal inset. A direct body `.janso-flow` starts without a
child top margin and uses `space-3` between children. Nested forms keep their own
spacing. GST registration and outward reporting cards use this compact rhythm.

`.janso-card--wrap-header` lets a card's status/actions wrap below its title at
narrow widths. Company configuration uses it to retain readable company names.

### 4.4 The wizard — the same rule, its own frame

`WizardLayout` is a full-page route with no shell beside it, and it follows §4.1's rule rather
than the document's: **the layout is the scroll container.**

```
.janso-setup    block-size:100dvh; overflow-y:auto    — the only scroller
                scroll-padding-bottom: 7rem           — clearance for the pinned bar
.janso-setup__header            masthead, scrolls with the content
.janso-setup__layout            grid: var(--janso-rail-w) minmax(0,1fr) — Stepper · content
.janso-setup__actions--sticky   position:sticky; bottom:0
```

**It must not leave the scrolling to the document.** `apps/console` sets
`body { overflow: hidden }` so the shell's `main` is the only scrollbar on a page — right for a
shell, and inherited by every shell-less route. `overflow: hidden` on the body propagates to
the viewport, which neither clips the content nor blocks `scrollTo`: `/companies/new` rendered
at its full 1940px with everything below the fold unreachable by wheel, trackpad or scrollbar,
while Tab-into-view still worked. A host's `globals.css` is not where this layout's scrolling
is decided, for the same reason the shell does not let it be either.

`scroll-padding-bottom` belongs on whatever scrolls — it was on `html` while the document was
assumed to scroll, and `html` is not the scrollport.

---

## 5. Component catalogue

Everything here lives in `@janso/ui`. An MFE holds only its routes, screens, nav config and
data adapters — the moment a second MFE needs a piece, it moves here ([CLAUDE.md](../CLAUDE.md) §4).

### 5.1 Theme

| Component | Contract |
|---|---|
| `ThemeProvider` | `{initial?: ThemePreference, onChange?: (p) => void, children}` — owns preference + resolved value, applies `data-theme`, subscribes to `matchMedia` when `system` |
| `useTheme()` | `{preference, resolved, setPreference}` |
| `ThemeSwitcher` | Segmented 4-button `role="radiogroup"`; each button `role="radio"` + `aria-checked`; arrow keys move selection; `--janso-*` only |
| `themeScript` | Pre-paint snippet as a string, injected by each app's root layout |
| `THEME_PREFERENCES` | `['light','dark','ledger','system']` |
| `resolveTheme(pref, prefersDark)` | Pure — the single resolution rule, shared by script, provider and tests |

### 5.2 Shell

`AppShell` · `Rail` · `RailSection` · `RailItem` · `RailGroup` · `RailFooter` · `OrgSwitcher` ·
`ContextSwitcher` · `TopBar` · `ContextChip` · `RoleChip` · `NotificationBell` · `UserMenu` ·
`Avatar` · `CollapseToggle` · `AppFooter`

`UserMenu` items support `separatorBefore`; the divider is non-focusable and does
not take part in arrow-key navigation. Account actions remain ordinary menu items.
Forms may use `fieldset.janso-setup__fields` to disable related controls together;
central styles remove the browser frame while retaining the shared field spacing.

- `Avatar` renders initials; `shape="square"` for an organisation, `"round"` for a person
- `RailItem` takes `icon`, `label`, `href`, `active`. It knows nothing about permissions —
  gating happens at the call site by wrapping the item in `<Can>`, so the rail stays a
  layout component and there is exactly one place permission logic lives
- `RailGroup` keeps its parent destination as an ordinary link and uses a separate
  disclosure button with `aria-expanded` and `aria-controls`. An active child opens
  its ancestors. Nested lists reuse rail spacing and theme tokens; the collapsed
  desktop rail retains child icons, while the mobile drawer retains disclosures.
  Callers resolve permissions and the deepest active destination before rendering.
  The console command search flattens the same tree. Version 0.1.19; validation is
  recorded in [administration navigation review](administration-navigation-review.md).
- `OrgSwitcher` is a labelled button (overline + name + chevron), not a native `<select>`.
  It is the *trigger only*: `icon` replaces the avatar, `compact` gives a second stacked
  trigger its denser form, and the ref and ARIA pass-throughs let a popup anchor to it
- `ContextSwitcher` is that popup — one component for every "which of these am I working
  in" choice (company in the rail's switcher band, financial year stacked under it). It
  portals and places with `lib/placement`, because the rail is a scroll container and sits
  on its own stacking context. `role="listbox"` with roving `tabindex`; arrows cycle, Home
  and End jump, Escape and Tab close and return focus, an outside press closes without
  taking focus. An option may carry a `badge` ("Default") and a `disabledReason`; a
  `search` slot is **controlled by the caller**, because one list is searched server-side
  and another in memory, so the component assumes neither. Footer `actions` are
  permission-gated the same way `Menu` items are — absent, not disabled.
  The option list scrolls independently between the search field and footer actions;
  rows retain their height and cannot overlap those actions (version 0.1.59).

### 5.3 Content

| Component | Notes |
|---|---|
| `PageNavigation` | Explicit back destination and ordered breadcrumbs; final item has `aria-current="page"`. Place before `PageHeader`; shared styles own spacing, wrapping and keyboard focus. `onNavigate` fires for the back link **and** every breadcrumb link, which is how an editor confirms discarding a draft once instead of guarding one link and leaking from the others |
| `FormLayout` | The shape of a create/edit page: the `<form>` and its card, plus an optional `aside` wrapped in its own context card beside it, collapsing below on a narrow viewport. Without an `aside` it stays a single column rather than letting a field row stretch the page |
| `FormActions` | A form card's footer: `cancel` (`href` · `label` defaulting to `Cancel` · `onClick` for the discard guard) on the left, the committing action right-aligned in `.janso-form-actions`. An unsafe cancel `href` renders nothing rather than a dead anchor |
| `PageHeader` | `overline` · `title` · `lede` · `meta` · `actions`. `meta` is a wrapping strip of chips under the lede — the record's status, type and currency; facts about the page's subject, not things to do (those are `actions`) |
| `Tabs` | `role="tablist"`, arrow-key navigation, `aria-selected`. Takes `panelId` so every tab declares `aria-controls`, and gives each tab `id={tabButtonId(tab.id)}` so the panel can name itself with `aria-labelledby` — a `role="tab"` with no panel is an incomplete pattern and an empty promise to a screen-reader user. **The `janso-tabs` strip is also the styling for a row of routed area links**: a screen whose sections are separate URLs renders `<nav aria-label="…">` with `<a className="janso-tabs__tab" aria-current="page">` and no tab roles, because arrow-key movement between panels is a promise separate pages cannot keep (decision 83) |
| `SectionHeader` | `overline` · `icon` · `title` · `description` |
| `Toolbar` | `left` / `right` slots |
| `Card` `CardHeader` `CardBody` `CardFooter` | `CardHeader`: `title` · `subtitle` · `badge` · `action` · `icon` |
| `StatTile` | `label` · `value` · `footnote` · `icon` · `tone: 'default'\|'brand'\|'success'\|'warn'\|'danger'` · `emphasis` · `nested` · `trend` (a slot, normally a `Sparkline`, set beside the footnote so tiles with and without one stay level). A `null`/absent value renders an em-dash, never `0` |
| `Sparkline` | `values` (decimal strings, oldest first) · `label` (the sentence that is its whole accessible content) · `series` (chart slot). A word-sized trend with no scale and no rendered values; draws nothing for fewer than two points. Geometry is the only place a value becomes a number, as in `BarChart` |
| `StatRow` | `columns: 3 \| 4` |
| `Badge` | `tone` × `variant: 'tint'\|'outline'\|'mono'` |
| `ListRow` | `rank` or `icon` · `primary` · `meta` · `figure` · `share` (renders a `Meter`) · `href` |
| `Meter` | `value` 0–1, `tone`; `role="progressbar"` with aria bounds |
| `Disclosure` | Native `<details>/<summary>` — keyboard and AT support for free |
| `Select` | Fixed choices from a real `<select>`, not a div: label, hint, error, groups, loading. See §5.7 |
| `SearchSelect` | Entity lookup: type to search, single or multiple selection, remote paging, optional create-new. See §5.5 |
| `FileUpload` | Attachments: click or drop, client-side screening, per-file progress and retry. See §5.6 |
| `EmailField` | An email address: the six attributes it needs, plus a blur-time tidy-up of what was pasted. See §5.8 |
| `PhoneField` | A dial code and a national number — two values, because the schema stores two columns. See §5.9 |
| `PasswordField` | A password, `autocomplete` driven by `purpose`, a strength meter that is not confidently wrong, and a Caps Lock notice. See §5.10 |
| `IconButton` | Requires `label`; renders it as `aria-label` and as the tooltip. `size: 'md' \| 'sm'` — `sm` (28px) for dense hosts: table rows, toasts. `Menu` passes the same `size` to its icon trigger |
| `SplitButton` | A primary link or command with an adjacent `Menu` caret. Filters permissions and unsafe links, explains disabled actions, preserves ordinary links and supports `onNavigate` for draft protection. Empty alternatives omit the caret; a denied primary falls back to the authorised menu. Uses existing button tokens and the Menu keyboard/portal contract. |
| `Menu` | §5.11's kebab and overflow, and the labelled trigger. `MenuItem.separatorBefore` rules off a band of verbs, matching `UserMenu`'s flag; it is ignored on the first *surviving* item and never doubles the rule that divides off destructive verbs. `triggerVariant: 'ghost' \| 'primary'` — `primary` is the bar's or page's leading verb ("New"), carrying `--janso-grad-action` with a hairline dividing its caret from its label. It stays **one** button: both halves open the same menu. Where a default action and its variants genuinely differ, use `SplitButton`, which gives the two halves separate focus targets |
| `TextField` | `label` · `hint` · `error` · `optionalNote` · `action` · `leading` · `trailing` · `hideLabel` — clips the label from the paint, keeps it as the accessible name, never hides an `action` (same contract as `Select`'s). `TableSearch` hides its label by default (`showLabel` to show it), so a filter bar's controls share one line |
| `EmptyState` · `ErrorState` · `Skeleton` | `ErrorState` takes `status: 401\|403\|422\|500` and renders the intended copy per status — never a blank screen |
| `Modal` / `Drawer` | The overlay container for a create/edit form or focused task — `Modal` centred, `Drawer` an inline-end side sheet. `title` · `footer` · `size: sm\|md\|lg` · `busy` · `dismissible` · `onClose`. Focus trap + restore, Escape, scrim dismiss and body scroll-lock come from the shared `useDialogA11y`; below a popover on `--janso-z-drawer`. For the step before something destructive, use `ConfirmDialog`, not a bare `Modal` |
| `Notice` | An inline banner in the page's own flow: `tone: info\|success\|warning\|danger`, dismissible, `role="alert"`/`status` by tone. The tone is icon + colour, never colour alone (§2.4) |
| `ToastProvider` / `useToast()` | Transient status floated over the page: `toast.success\|warning\|error\|info(message, { title?, duration? })`. Same tone triple and icon as `Notice`. An error persists until dismissed (`duration: null` default); success/info fade at 5s, warning at 8s. Hover freezes the countdown, the stack is capped, above every layer on `--janso-z-toast`. Never the record of what happened — that is the audit log |
| `BarChart` | Token-coloured SVG. No chart dependency until one is justified (§9) |
| `GroupedBarChart` | `categories` · `series` (`key` · `label` · `slot` · `values`) · `ariaLabel` · `formatValue` · `formatScale`. One cluster per category, one bar per series, one shared scale; slot colours only. Always carries a text legend and a table twin with a column per series; every bar's hover readout names its series. Shares `barPath`/`clamp`/`coord` with `BarChart` in `lib/chart-geometry` |
| `CommandPalette` · `CommandTrigger` · `useCommandPaletteShortcut` | One keyboard path to every destination (§5.12) |
| `.janso-form-grid` | Fields side by side, `auto-fit` columns from a 16rem floor; resets the stacked-field sibling margin so neighbours stay level. `.janso-form-grid__full` spans a row |

### 5.4 Display config and permissions

| Piece | Contract |
|---|---|
| `DisplayConfigProvider` / `useDisplayConfig()` | Resolved company + user display config: `currency`, `currencySymbol`, `amountPrecision`, `quantityPrecision`, `roundingMode`, `dateFormat`, `datetimeFormat`, `digitGrouping`, `currencyDisplay`, `decimalSeparator`, `groupSeparator`, `currencySymbolPosition`, `negativeFormat`, `timezone`, `locale` — the presentation fields from [company](company.md) §4.5. `show_amount_in_words` is out of scope: it is a document concern, not a figure |
| `formatMoney` `formatQuantity` `formatCompact` `formatDate` `formatDateTime` `formatRange` | Read the resolved config. **Never `toLocaleString()` defaults, never client locale** ([CLAUDE.md](../CLAUDE.md) §4) |
| `PermissionProvider` / `useCan(key)` / `<Can permission>` | Presentation only. The server is the enforcement point; hiding a control is never the control ([field-permissions](field-permissions.md) §6) |

**Business dates are formatted from the string, never through a timezone.** A `posting_date`
bound like `'2026-07-01'` has no instant attached, so `formatDate`/`formatRange` read the
calendar fields straight off a `YYYY-MM-DD` input. Passing `'2026-07-01T00:00:00Z'` instead
re-introduces a zone conversion and renders the period a day early west of UTC. A date that
parses but is not real (`'2026-02-30'`) returns an em-dash rather than rolling into March.

**Money and quantities cross the wire as strings and are formatted as strings.** No amount ever
becomes a JS `number` — `Number('0.1') + Number('0.2')` is exactly the silent float coercion
the backend rules exist to prevent. `digit_grouping` supports `western` (1,234,567) and
`indian` (12,34,567); grouping comes from config, never from the browser.

### 5.5 `SearchSelect` — entity lookup

Picking one entity, or several, out of a set too large to scroll: customers, items, ledger
accounts, warehouses, tax rates.

**Which control to reach for**

| Situation | Control |
|---|---|
| Up to ~10 fixed choices, no searching | `Select` — a real `<select>`, and the platform gives you the keyboard, type-ahead and the mobile picker free (§5.7) |
| Entity lookup, remote data, or more rows than someone will scroll | `SearchSelect` |
| A file rather than a value | `FileUpload` (§5.6) |
| An email address, a phone number, a password | `EmailField` (§5.8) · `PhoneField` (§5.9) · `PasswordField` (§5.10) — never a bare `TextField`, which is how a screen ends up without `autocomplete` |

It is named for the job it does, but it **implements the WAI-ARIA 1.2 combobox pattern** — that
is the spec its roles, keyboard model and `aria-activedescendant` behaviour are written against,
and where to look when auditing it.

**The two things it deliberately does not do.** It never fetches, and it never formats. The
caller supplies `loadOptions`, so the library never learns about `catalog` or `identity`; and
`figure` / `meta` arrive as already-formatted strings, so no amount can reach it as a number.

```ts
type SearchSelectOption = {
  id: string;          // the entity id
  label: string;       // primary text — what the search matched
  meta?: string;       // second line: code · place · status
  figure?: string;     // right-aligned, ALREADY FORMATTED. A string, never a number
  icon?: ReactNode;
  tone?: Tone;
  disabled?: boolean;  // present but not selectable — an inactive item, say
};

type SearchSelectLoader = (args: {
  q: string;
  cursor: string | null;
  signal: AbortSignal;
}) => Promise<{ items: SearchSelectOption[]; nextCursor: string | null }>;
```

Single and multiple selection are a **discriminated union**, not a boolean beside loosely typed
props: `value` is `string | null` or `readonly string[]` and is never ambiguous.

```tsx
// Static master choices: IDs are stored; labels are displayed.
<SearchSelect label="Unit" scopeKey={companyId} required name="unit_id"
  options={unitOptions} value={unitId} onChange={setUnitId} />

// Remote listed autocomplete: the caller owns the API, paging and authorization.
<SearchSelect label="Manufacturer" scopeKey={companyId}
  loadOptions={loadManufacturers} selected={currentManufacturer}
  value={manufacturerId} onChange={setManufacturerId} />
// Multiple mode uses `multiple value={ids} onChange={(ids, options) => …}`.
```

Presentation props, added while using it for real even though the dashboard filter ended up
needing none of them — a toolbar that grew a stacked label and an unbounded chip list is the
shape they exist for, and the next call site will hit it: `hideLabel` keeps
the label as the accessible name and takes it out of the layout (a toolbar filter, where a
stacked label in a row of controls is noise); `maxChips` collapses a long selection into
"+N more" so a filter cannot push the input out of its own control; `onQueryChange` lets a
caller mirror what was typed into a heading or the URL. There is **no "Optional" marker** — on a
lookup it is noise, and `required` already carries the semantic.

`selected` carries the resolved option(s) for the current value. The control caches every option
it renders, but on a first paint — a value loaded from the server whose option was never in a
list — it has an id and nothing to label it with. Passing the entity you already have is cheaper
and more honest than having the control fetch it.

In multiple mode `onChange(ids, options)` gives **`ids` as the authority**: `options` is that same
set resolved to everything the control can label, in the order of `ids`, so an id whose option
this field has never seen is absent from `options` while still present in `ids`. The alternative
is inventing a label for an entity, which on a filter chip prints a fabricated customer name.
Pass `selected` and the two always agree.

An unresolved value remains visible as its raw ID, including a removable chip in multiple
mode. Callers must provide actual resolved `selected` labels; an invented `{id, label: id}`
overwrites the label the search already resolved. Inactive options cannot be added, but an
existing inactive selection can be removed. `required` validates committed IDs through native
form validity; typing a search does not satisfy a required selection.

`scopeKey?: string` names the lookup dataset, for example
`JSON.stringify([companyId, sourceKey, parentId])`. Change it when that dataset changes:
the control discards queries, cached labels, cursors and pending responses. The caller still
owns `value` and must clear or replace IDs as appropriate for the new scope. Loader function
identity alone does not reset searches, so inline callbacks remain supported.

**Async behaviour, and the three failure modes it is built around**

| Risk | Rule |
|---|---|
| A request per keystroke | 250ms debounce while typing; none on open |
| A stale response overwriting a fresh one | An `AbortController` per request **and** a monotonic request id. Abort alone is not enough — an aborted request can still settle first, so only the newest id is applied |
| **A cursor outliving its query** | Changing `q` resets the cursor to `null` and clears accumulated items. A cursor is bound to its query, filters and sort; reusing it across a change returns `422` ([api-conventions](api-conventions.md) §2.1) |

`q` is clamped to the API's 200-character maximum. Accumulated results cap at `maxOptions`
(default 200) and say so, rather than paging forever. Paging is triggered by a sentinel **and** a
real "Load more" button, because an intersection observer is unreachable by keyboard.

**What the input holds and what the list reflects are two different things.** In multiple
selection a commit clears the input, so the next name can be typed immediately, while the
result set stays on screen. Sharing one value forces a choice between an input you have to clear
by hand and a list that empties itself the moment you pick something — the second was the first
implementation, and it left an open, blank panel.

**"No matches" and "that request failed" are different states.** Collapsing them tells someone
their data does not exist when in fact the network did not answer. The error state names the
failure and offers retry.
Press Enter while a search failure is displayed to retry. A failed next-page request retries
that cursor and preserves previously loaded results. New queries immediately abort and hide
old results, including during the debounce and when the query falls below the minimum.

**Keyboard and focus.** Arrow keys, Home/End and Page Up/Down move the active option;
Enter selects it. Tab dismisses the popup and moves on. Escape first dismisses the popup,
then clears a retained search, then reaches a containing dialog. Modified editing keys and
IME composition remain under the text input's control; remote search waits until composition
ends. The toggle, clear, chip removal, paging and retry preserve input focus. Programmatic
focus restoration to an invalid field leaves its error visible; click or Arrow Down opens it.

In single selection, focus, click and opening the list keep the committed label visible.
The label is selected so typing starts a replacement search immediately; searching does
not change the committed ID. Dismissing an unfinished replacement search restores the
label and discards that search, including when the field is opened again. Only choosing
another option or pressing Clear changes the selection. Multiple selection keeps its
existing chips and separate search input.

**On open with an empty query**

| Mode | `minQueryLength` default | On open |
|---|---|---|
| `loadOptions` (async) | 2 | "Type to search" — no request is made |
| `options` (static) | 0 | the list shows |

A deliberate asymmetry: the reason to hold back is the cost of an unfiltered query, which a
static array does not have — and a static list that hides itself reads as broken. Overridable
either way.

**Create-new** is opt-in and permission-gated by the caller:

```ts
canCreate?: boolean;
onCreate?: (q: string) => Promise<SearchSelectOption | null> | void;
```

Resolve an option and the control selects it; return nothing and the app owns the flow — open a
form, come back, set `value`. `canCreate` is the caller's permission check, and like every other
gate in the client it is presentation only (§5.4).
Creation is offered only after a successful search establishes no exact match across all
available pages (or the entire static array, including matches beyond the display cap).
Pending creation locks edits and duplicate activation. Its result uses the latest controlled
selection and is ignored after dismissal, unmount, disabling or a `scopeKey` change. These
guards cannot cancel a server write: callers retain permission, idempotency and reload policy.

**The defects this control's own tests and reviews found, worth knowing before writing the next
one.** None was visible in a happy-path click-through, and most only misbehaved under timing:

| Defect | Why it hid |
|---|---|
| The option cache was a `useRef` filled from a `useEffect`, so nothing was labelled on first paint | Mutating a ref schedules no render; any later re-render papered over it, so it read as intermittent |
| "No debounce on open" was flagged in an effect declared *after* the search effect | Effects run in declaration order, so the flag was still false when it was read — the first character typed skipped the debounce instead |
| Walking onto the last row paged forever when the list could not grow — at `maxOptions`, or on an empty page that still carries a cursor | `loadMore`'s identity changes twice per request, re-firing the effect, and each response mints a *fresh* cursor so a cursor-identity guard is not enough. It needs the row count |
| The cursor was reset inside the debounce, so paging in the window between a keystroke and the timer sent the previous query's cursor | Self-healing — the debounced request supersedes it — so the only symptom is a 422 in someone's logs |
| `aria-describedby` listed both the hint and error ids while only one paragraph renders | A dangling idref is dropped silently by assistive technology |
| The highlight moved by `aria-activedescendant`, which moves no scroll position | On a list taller than its box, arrowing down walked the highlight out of view — the key appeared to do nothing |
| The highlighted row was tracked by ordinal, and auto-paging appends rows | The highlight slid onto a different entity and `Enter` committed one the user never saw. Tracked by row identity now |
| `justOpened` was armed on every focus and click, not on the transition | Clicking to place the caret mid-edit re-armed it, so the next keystroke skipped the debounce |
| "Create *X*" was decided from the query and the current rows, so during the debounce it was judged against the **previous** query's results | It offered to create a customer that the in-flight search was about to return — and the row vanished under the pointer when the response landed. Fixed by tracking which query the rendered results belong to (`remoteFor`) and only offering create when they match |
| A rejected `onCreate` left the panel with no create row and no explanation | The failure was swallowed to keep it from escaping as an unhandled rejection; the person saw the row disappear and concluded the entity now existed. It now names the failure and offers the retry |
| Committing a selection cleared the input without telling `onQueryChange` | The caller mirrors the query into a heading or the URL, so the two silently disagreed after every pick — visible only at a call site that used the prop |
| The "showing the first *N*" notice appeared whenever the visible rows hit `maxOptions` | A last page that lands exactly on the cap is complete, not truncated, and the notice told someone to keep typing for results that were all already there. The notice needs to know rows were **dropped**, which the row count alone cannot say |
| The portalled list re-rendered on every scroll event, moved or not | `place()` set state unconditionally; scrolling a page with the list open re-rendered it at the scroll rate. The measured rectangle is compared before committing it, and the listeners are `passive` |

**Positioning.** The list renders in a portal at `position: fixed`, placed from the field's own
rectangle and re-placed on capture-phase scroll, resize and field resize, flipping above when
there is no room below. It is **not** absolutely positioned inside its parent: any ancestor with
`overflow` would clip it, which is precisely how the top bar clipped `UserMenu` and how the tab
strip grew a scrollbar. Focus never enters the list — the highlight moves with
`aria-activedescendant` — so there is nothing to trap.

### 5.6 `FileUpload` — attachments

A signed contract on a customer, a bank statement against a payment, a scanned purchase invoice.

**The two things it deliberately does not do**, the same line `SearchSelect` draws:

- **It never uploads.** The caller gets the accepted `File`s and owns the transport, the
  idempotency key and the retry policy. An upload belongs to a service and a tenant; a component
  that posted on its own would have to know both.
- **It never decides what is allowed.** `accept`, `maxSizeBytes` and `maxFiles` exist so a person
  is told *before* waiting for a 10 MB round trip. They are presentation, and **the server
  re-validates every one of them** — a request reaches the endpoint without ever going near this
  control ([CLAUDE.md](../CLAUDE.md) §5, §6.15).

```ts
type FileUploadItem = {
  id: string;                 // upload id in flight, attachment id once stored
  name: string;
  size?: number;              // bytes; absent for a stored attachment whose size isn't held
  status: 'pending' | 'uploading' | 'done' | 'failed';
  progress?: number;          // 0–100; ABSENT means in flight with no measurement
  error?: string;             // in the service's own words
  href?: string;              // SIGNED, EXPIRING (§5.14) — never a public object-storage URL
};

type FileRejection = {
  name: string;               // already stripped of bidi overrides — safe to render
  reason: 'type' | 'size' | 'count' | 'duplicate' | 'empty';
  message: string;            // a whole sentence, ready to show
};
```

`items` is the caller's, and the control never reorders it — an edit form shows attachments
stored months ago beside one uploading right now. `onRemove` and `onRetry` render their buttons
only when supplied, so a read-only attachment list is the same component with two props left off.

**Every rejection carries a finished sentence.** "Rejected" on its own leaves someone re-dropping
the same file to find out why, so each names the file and the limit it crossed —
`huge.pdf is 4.0 KB — the limit is 1.0 KB.` A batch's rejections replace the previous batch's
rather than accumulating: a rejection belongs to the drop that produced it.

| Screened for | Rule |
|---|---|
| `empty` | Size 0 — also what a dropped **folder** looks like, so the sentence covers both without guessing |
| `type` | Native `accept` semantics: `.ext` on the name, `type/*` on the family, or an exact MIME match. An unknown MIME type (`''`, which browsers report for plenty of real files) never satisfies a MIME pattern |
| `size` | `maxSizeBytes` |
| `duplicate` | **Tidied** name and size, against `items` and against the batch — two files may legitimately share a name, and comparing a raw name against a tidied one let the file the user can see attached in a second time |
| `count` | `maxFiles` minus what is already attached, or one when not `multiple` |

**Why the validation is in JS at all: `accept` is enforced on the picker and not on a drop.** The
browser filters the file dialog and then hands a dropped `.exe` straight through. Every
validation test therefore goes through `drop`, where the platform guarantees nothing.

**The accessibility triangle, and how it is resolved.** A file input needs one tab stop, the
field's name, and a click target the size of the zone. The zone must therefore *be* the input's
`<label>` — and a second `<label>` would concatenate into the announced name, so the field label
is a `<span>` and the name comes from `aria-labelledby`. The input is `janso-visually-hidden`
(clipped, **not** `display: none`, which would take it out of the tab order), and the focus ring
is projected onto the zone with `.janso-upload__input:focus-visible + .janso-upload__zone`.

| Trap | What it does when missed |
|---|---|
| No `preventDefault` on `dragover` | `drop` never fires and the zone silently does nothing — the most common drop-zone bug there is |
| Drag state as a boolean | Crossing a child element fires `dragleave` then `dragenter`, so the zone flickers under a still pointer. A depth counter fixes it |
| Reacting to any drag | Dragging selected text lights up a zone that will refuse it. `dataTransfer.types.includes('Files')` gates it |
| Not clearing `input.value` after a change | Re-picking the same file fires no `change`, so a failed upload cannot be retried with the file already chosen |
| `required` left standing | The value *is* cleared after every selection, so `required` is applied only while `items` is empty — otherwise the field blocks a submit on a form that does hold files |
| `aria-valuenow={0}` for "no measurement" | Claims nothing has been sent. No progress number means an **indeterminate** progressbar, with `aria-valuenow` omitted |

**A file name is user data and is rendered as such.** Bidi controls and zero-width marks are
stripped before any name reaches the DOM or a rejection sentence: `invoice` + U+202E + `gnp.exe`
displays as `invoiceexe.png`, so the extension a person reads is not the one that would run.
React escapes markup; it does not undo this. Long names truncate with an ellipsis rather than
reflowing the row, and never into a `title` tooltip no touch device can open.

`aria-live` carries one sentence for the whole list — `Uploading 1 of 4`, then `1 upload failed`
— because a region that re-read every progress tick would talk over everything else on the page.

`formatBytes` is exported and is deliberately **not** routed through `useFormatters`: a byte count
is not an amount, and `company.amount_precision` would render a 1 MB file as `1,048,576.0000`.

### 5.7 `Select` — fixed choices

A real `<select>`. The platform ships the keyboard model, type-ahead and the native mobile
picker, and none of it needs maintaining. The dividing line against `SearchSelect` is in §5.5.

`label` · `value` · `options` · `onChange(value)` — the value, not the event, so no call site
reads `e.target.value` · `optionalNote` / `action` · `hint` · `error` · `placeholder` ·
`hideLabel` · `inline` · `loading` / `loadingLabel`, plus native `id`, `name`, `required`,
`disabled` and every other `<select>` attribute passed straight through.

`options` takes flat `{value, label, disabled?}` items or `{label, options}` groups, which render
as `<optgroup>`; a value is matched inside groups as well as at the top level.

**A native `<select>` whose `value` matches no option renders blank** — `selectedIndex` is `-1`,
the field looks empty and there is nothing to explain it. So an unmatched value always renders an
empty first row (`Select…` when no `placeholder` was given), and the row is `disabled` when the
field is `required` so it cannot be chosen back.

**`loading` is "busy", not "withheld".** The control is inoperable and named through a
`role="status"` line with `aria-busy`, and the caret becomes a spinner — but a value already
chosen is mirrored into a hidden input, because a `disabled` select submits nothing and a form
posted mid-refresh would silently drop the field. A genuinely `disabled` field mirrors nothing:
withholding the value is the point.

`aria-describedby` lists only ids that actually rendered. A dangling idref is dropped silently by
assistive technology, taking the description that *did* render with it.

**`hideLabel` clips the label, never the row.** `janso-visually-hidden` hides without removing, so
hiding the whole label row left a button or link passed as `action` focusable and invisible — a tab
stop a sighted keyboard user cannot see (WCAG 2.4.7, 2.4.11). The label alone carries the class, the
row renders only when something visible sits beside it, and `SearchSelect` and `FileUpload` follow
the same shape.

Its stylesheet lives in `janso-ui.css` with the other form controls, not in `data.css`: a form
field is a framework primitive, and `data.css` is not imported by every app — the auth app never
loads it, so `Select` was unstyled there.

### 5.8 `EmailField` — an email address

`label` · `value` · `onChange(value)` · `optionalNote` / `action` · `hint` · `error` ·
`normalizeOnBlur`, plus every native `<input>` attribute.

A `TextField` that has been told what it holds. The value of the component is not the markup, it is
the seven attributes below: each fixes a real failure, none is visible in review, and all seven get
retyped — differently — on every screen that asks for an address.

| Attribute | What it prevents |
|---|---|
| `type="email"` | The browser's own last-resort check, and the right mobile keyboard |
| `inputMode="email"` | `@` on the first layer of that keyboard instead of two taps in |
| `autoComplete="email"` | The password manager not offering the address it already has |
| `autoCapitalize="none"` | iOS capitalising the first letter of a case-sensitive local part |
| `autoCorrect="off"` | The platform "fixing" a domain to a dictionary word |
| `spellCheck={false}` | The address being sent to a platform spell-check service |
| `maxLength={320}` | Accepting more than `VARCHAR(320)` and failing at the `INSERT` instead |

**It reports a value, not an event**, like `Select` and `SearchSelect`: a control that rewrites what
was typed must own the value, and one that owns the value has no business handing back an event
whose `target.value` is already stale.

`normalizeEmail` runs **on blur, not per keystroke** — rewriting mid-typing fights the caret. It
handles what a paste actually contains: a mail client's `Ada Lovelace <ada@example.com>`, a copied
`mailto:` link, a spreadsheet cell's trailing space, a rich-text editor's zero-width characters and
bidi marks. It **lowercases the domain and not the local part**: domains are case-insensitive, local
parts formally are not, and rewriting one silently changes the mailbox on a server that honours the
spec. It splits on the *last* `@`, so a quoted local part survives. When there is nothing to tidy it
does not call `onChange` at all — a no-op change on every blur marks a pristine form dirty. When it
does tidy, the value is written back onto the input **before** the caller's own `onBlur` runs:
validation-on-blur reads `event.target.value`, and handing it the raw `Ada Lovelace <…>` put "not a
valid email" under a field the next render showed as valid.

`isEmailLike` is a **typo guard, not RFC 5322**: one `@`, something before it, a dotted domain,
within 320 characters. Every regex claiming to implement the full grammar rejects deliverable
addresses; being strict here means a customer who cannot be invited, while being loose means a
verification mail that bounces — which the platform already handles.

Neither function is a security control. Stripping bidi marks stops an address *displaying* as
something it is not, but a homograph domain in real Unicode letters still reads as itself — IDN
lookalikes are the server's and the verification mail's problem, and no client-side check here is
load-bearing ([CLAUDE.md](../CLAUDE.md) §5).

Verification state is **not** a prop. Only the server knows it, so "Verified" is a `Badge` the
caller passes to `action`.

### 5.9 `PhoneField` — a dial code and a national number

`label` · `value: {countryCode, number}` · `onChange(value)` · `dialCodes` · `optionalNote` /
`action` · `hint` · `error` · `codeName`, plus native `<input>` attributes.

**Two values, because [identity-schema](identity-schema.md) stores two columns** —
`phone_country_code VARCHAR(8)` and `phone VARCHAR(20)`. A control reporting one `+919876543210`
string would force every caller to split it again, and each would split it differently. `toE164()`
is exported for the transports that need one string ([notification](notification.md)); it returns
`''` rather than a partial number when either half is missing, because `+91` is not a phone number
and a caller that forgot to check would otherwise message a country code.

**`dialCodes` is a prop.** `country.phone_prefix` is the platform's one source for dial codes; a
list baked into the design system would be a second source, and the second source is always the
stale one.

| Behaviour | Why |
|---|---|
| Digits only in the number; separators stripped | `phone` stores bare digits. Grouping is per-country *and* per-length data this control does not have |
| National digits capped at `15 − dialDigits` | E.164's ceiling. Switching country re-applies the cap, so a 13-digit number does not survive a move to a 4-digit code |
| A pasted `+…` or `00…` splits itself, **longest dial code first** | `+1` and `+1242` both match a Bahamian number; shortest-first leaves `242` glued to the national part and files it under the United States |
| A **typed** `+…` splits itself too, at the digit that first names a country | The `+` was being stripped on the keystroke that carried it, so nothing downstream ever saw an international number: `+91` selected and `+919876543210` typed stored the code twice, and `isPhoneLike` accepted the 14 digits |
| While a typed `+` is still ambiguous, the field shows what was typed | Discarding it would leave nothing to say the next keystrokes belong to a country code. It is held for at most four digits — the longest code the ITU issues — after which the digits become national rather than being kept hostage |
| `00…` is honoured only once it is long enough to be a whole number | `001` is equally the third keystroke of a national number beginning `001…`, and a change event does not say which happened. Reading it as `+1` moved the typist to another country and emptied the field under them |
| A paste whose code is not offered is kept as digits, not reassigned | Guessing the country silently changes whose number it is. `isPhoneLike` and the server say it is wrong; the control does not invent an answer |
| No formatting as you type | Faking `+91 987 654 3210` for a number Indians read as `98765 43210` is confident nonsense |

**No `maxlength` attribute** — the browser applies `maxlength` to a *paste* before any handler runs,
so pasting `+91 9876543210` under a 13-digit cap arrives already truncated and the number loses its
last digit in silence. The cap is applied in JS, after the dial code has been taken off the front,
which is the only point at which the correct length is known.

**A stored code the picker was not given still shows itself.** Rendering only the known codes leaves
the `<select>` displaying its *first* option while the value says something else — the §5.7 trap,
and here it would relabel a supplier's UK number as Indian. An empty code renders a `Code`
placeholder rather than silently meaning "the first country in the list".

The visible label belongs to the **number** input and the picker names itself
(`aria-label="Country dial code"`). There is deliberately no `role="group"`: two controls sharing
one accessible name is worse than no grouping, and every query for the field would match twice. The
picker reuses `janso-select__*` — it *is* a `Select`, and a second box model would let the two drift
a pixel apart on the one screen showing both.

### 5.10 `PasswordField` — a password

`label` · `value` · `purpose: 'current' | 'new'` · `showStrength` · `avoid` · `action` · `hint` ·
`error`, plus native `<input>` attributes.

**Three things it deliberately does not do.** It never blocks paste — that defeats password
managers, trading a theoretical shoulder-surfing win for the certainty of weaker, reused, hand-typed
passwords. It never sends the password anywhere to be scored; a breach-list check belongs on the
server, over a hash prefix. And it is not the policy: the meter advises, the server decides, because
scoring in the browser is advice a hostile client can simply not run.

`purpose` drives `autocomplete` — `new-password` is what makes a password manager *offer to
generate* one instead of autofilling the old one, so getting it wrong is the difference between a
suggested strong password and a silent wrong value. It also defaults `showStrength`, since strength
advice is only useful while choosing.

`assessPassword(value, avoid, minimumLength = 8)` returns `{score, label, advice}`;
`PasswordField` passes its `minLength` to the meter. `scorePassword` is the score alone,
so a submit guard and the meter cannot disagree.

Unlike §5.8 and §5.9 this field keeps the **native `onChange` event**. The rule across the library
is that a control reporting a value is a control that *rewrites* the value; a password is never
rewritten — not trimmed, not case-folded, not stripped of the zero-width character someone's
password manager generated — so there is nothing for it to own.

| Rule | Effect |
|---|---|
| Under the supplied minimum (default 8 Unicode characters) | `0`, "Too short" — nothing else is considered |
| Accepted but under 8 Unicode characters | `1`, "Weak"; suggest a longer passphrase |
| Contains a 4+ character token from `avoid` | `0`, "Too guessable" |
| One character repeated, or one straight run | capped at `1` |
| Both cases · a digit · a symbol · 16+ characters | `+1` each, capped at `4` |

The run rule exists because `12345678` otherwise scored "Fair" for containing digits — a meter that
is confidently wrong is worse than no meter. It compares **case-sensitively**, so `Abcdefgh` is a
capital followed by a run rather than a run, and the shift key is not punished. The 16-character
bonus stops a passphrase — the strongest thing most people will type — scoring below a short
`P@ss1x!`. `avoid` catches the reuse the caller can see (the email and name on the same form); the
four-character floor keeps an initial or a `.com` from condemning every password.

**Caps Lock is announced while the field is focused and masked**, read from the key event's
`getModifierState` rather than tracked as a press, because the key may have been on before the field
had focus. Once the characters are on screen the user can see it for themselves, so the notice goes.

The meter's four bars are `aria-hidden` and the words beside them carry a single `role="status"`:
announcing four empty spans adds nothing, and putting the live region on the whole block re-reads
the meter's markup on every keystroke. The toggle's accessible name names its field
(`Show new password`) because a create-account form has two of them and "Show / Show" says nothing
about which — its visible word stays inside the name, for speech control (WCAG 2.5.3).

### 5.13 Form structure — required marks, groups and choice cards

Three primitives that exist because the company creation wizard needed them and every form
in the console benefits from them.

**`FieldLabel` and the required mark.** Every field component routes its label through
`FieldLabel`, which draws a `*` when the control is `required`. This is automatic: a caller
already passing `required` gets the mark, and no author has to remember it. Before this,
`required` reached only the native element — constraint validation worked and screen readers
announced it, and a sighted user discovered a required field by submitting and failing. On the
wizard's first step, four of six fields were required with nothing on screen saying so.

Two rules the mark must keep:

- **It sits outside the `<label>` element.** Inside it, even `aria-hidden`, it becomes part of
  the label's text content and `getByLabelText('Legal name')` stops matching — 426 such
  queries across 169 test files in the console app. `getByRole` honours `aria-hidden`;
  `getByLabelText` reads raw text. A sibling in a `janso-label-group` is correct for both, and
  the accessible name stays exactly the label.
- **It is `aria-hidden`.** `required` on the control is what assistive technology and the
  browser read. The asterisk is the visual echo of a fact already stated, not the statement.

Required is marked rather than optional, which is the opposite of GOV.UK's advice. That advice
is for a public form filled in once by someone who has never seen it; this is an operator
console whose forms are mostly required, where marking the exceptions means marking almost
everything.

**`FieldGroup` and `FieldPair`.** A step with fifteen controls in one column is a list to get
through; the same fifteen under four headings are four decisions to make. `FieldGroup` is a
`fieldset`/`legend`, so the grouping is announced when focus enters a field and is not merely
a heading above it. `FieldPair` puts two short fields on one row and collapses to one column
under 40rem — the only exception to full-width fields that this system offers, because a
one-character decimal separator in a full-width box is the thing it exists to fix. Anything
wanting three across should say why.

Both containers are grids, so **the gap owns the spacing and the stacked-field margin is
reset** (`.janso-fieldpair > .janso-field + .janso-field`, and the same inside a group), the
way `.janso-form-grid` already did. Without it `.janso-field + .janso-field`'s
`margin-top: space-4` still applies: the second field of a pair starts 16px below the first —
"Incorporation date" sat beside "Entity type" and visibly lower than it — and a group's own
16px gap became 32px. Any new grid of `.janso-field`s owes the same reset.

**`ChoiceCard`.** A checkbox whose consequence is worth reading: the whole card is the label,
so the two lines explaining a setting are part of the target that explains it rather than a
dead zone beside a 16px box. `badges` is a slot, not a boolean, because "permanent once used"
as the tail of a description is the one irreversible fact on the card formatted exactly like
the reversible ones. `depth` indents 0–2 levels so a dependency chain reads as structure
instead of as three sentences saying "also turns on".

Its accessible name is the **title alone**, via `aria-labelledby`. A label wrapping the whole
card makes every word inside it part of the name, and the checkbox announced itself as
"Expiry dates Permanent Record and report expiry against each batch" — in one breath, in a
screen reader's list of form controls. The badges and the description are `aria-describedby`.

```tsx
<FieldGroup title="Numbers">
  <FieldPair>
    <TextField label="Decimal separator" required value="." onChange={…} />
    <TextField label="Thousands separator" value="," onChange={…} />
  </FieldPair>
</FieldGroup>

<ChoiceCard
  title="Expiry dates"
  description="Record and report expiry against each batch."
  badges={<Badge tone="warn">Permanent</Badge>}
  depth={2}
  checked={on}
  onChange={setOn}
/>
```

### 5.14 `ReviewList` — a summary you can act on

The pre-commit summary in `WizardLayout`. Pass `onEdit` and each row with a `step` gets an
Edit that jumps there; omit it and the list stays read-only. A stepper can already be clicked
back to a completed step, but nothing on a review page says so, and a reader who spots a wrong
legal name should not have to work out which of six steps it came from. The button's
accessible name carries the field, because "Edit" eleven times is eleven identical names.

### 5.11 `DataTable` and the list surface

Every list in the platform is the same problem — a cursor page of rows, a typed set of predicates, a
sort the server will honour, a per-row verb set the actor may not hold, and five states before any
data arrives. It is written **once**, here, and a screen supplies only what is true of its resource.

The surface is nine pieces, composed by the screen rather than by one god component:

| Piece | What it owns |
|---|---|
| `DataTable` | The `<table>`: header, cells, sort controls, selection column, kebab column, detail rows, and the loading / error / empty / filtered-empty states |
| `useListQuery` | The query — sort, filters, `q`, limit, and the **cursor stack** — plus every rule about when a cursor dies |
| `TableSearch` | The debounced search box, and the fact that a sub-minimum term is never sent |
| `FilterBar` / `FilterChip` | The predicates in force, stated, each individually removable |
| `Pager` | The range, the two steps of the walk, and the page-size choice |
| `BulkBar` | What is selected, scoped to this page, and the verbs that act on it |
| `ColumnPicker` + `useColumnPreferences` | Which columns this reader wants, persisted per table id |
| `ExportMenu` | Asking the **server** for a file |
| `ConfirmDialog` | The step before anything destructive, or a review before a commit. `size: md\|lg` (30rem / 48rem); the body scrolls while the title and Cancel/Confirm stay pinned |

List toolbar presentation lives in shared `styles/table.css`. Within `FilterBar`,
`Select` defaults to an inline label and uses the search field's control height;
`inline={false}` explicitly keeps a stacked layout. Query field margins are reset
so the toolbar gap alone controls spacing. Search hints remain below their input,
actions sit at the far edge, and controls wrap when the available width requires it.
When a card directly contains a filter bar and pager, both use the card header's
`space-5` side gutters. The table's outside columns (or stacked rows) match those
gutters, and its nested shell leaves the outer border and corners to the card.
Page-level bars keep their existing page gutters.

Event-history lists use the shared `janso-event-log` card, toolbar and explanatory
note. Its fixed-choice controls use a bounded grid; action controls wrap within
the card at narrow widths. Long action codes wrap without changing their values.
Audit detail facts and before/after evidence styles live in shared `data.css`.
Stacked DataTable styles and card gutters target the owning table's direct rows
and cells, so nested evidence tables retain their headers and column layout.
Clipped list headings override pinned positioning on narrow screens; their
accessible column names remain in the document.

`DataTable` takes `caption` · `columns` · `rows` · `rowId` · `rowLabel` · `rowLocked` · `sort` /
`onSortChange` · `density` · `loading` / `skeletonRows` · `error` / `errorDetail` / `onRetry` ·
`filtered` / `emptyTitle` / `emptyBody` / `emptyAction` / `onClearFilters` · `selectable` /
`selected` / `onSelectionChange` / `rowSelectable` · `rowActions` / `onAction` · `renderDetail` /
`rowExpandable` · `stickyHeader` · `pinFirstColumn` · `stack`.

**A `Column` is data, not markup.** `key` · `header` · `type` · `value` · `render` · `align` ·
`sortable` / `defaultSortDirection` · `width` · `hidden` / `locked` · `permission` · `truncate` ·
`hideHeader` · `description` · `currencyKey` · `precision` · `tone` / `label` · `href` / `external` ·
`total` · `words` · `actions`. `type` is one of `text`, `code`, `money`, `quantity`, `percent`,
`date`, `datetime`, `relative`, `status`, `chips`, `meter`, `link`, `boolean`, `masked`, `custom`,
`actions` — the table renders it, so a figure is formatted through the reader's own display config
(§5.4) in one place instead of in forty `toLocaleString()` calls. `render` is the escape hatch and
receives the formatters, so even a bespoke cell cannot reach for a locale default.

**The invariants worth stating, because each of them is a defect that already happened:**

- **Sorting and searching are the server's.** A header is `sortable` only when the endpoint
  allowlists that key; anything else renders as plain text with no `aria-sort`. Sorting the page in
  hand would order 25 of 40 rows and present the result as the largest balances.
- **Any change to the query restarts the walk.** `useListQuery` owns this: a cursor is bound to the
  sort, the filters, the search *and the limit*, so a reused one is a `422`
  ([api-conventions](api-conventions.md) §2.1). Making it a rule of the hook is what stops it being
  forgotten per screen — `setSort`, `setFilter`, `setQ` and `setLimit` all drop the stack.
- **Back is a step through cursors already used, never a query.** A keyset cursor points forward
  only, so the hook keeps the stack and the first page's cursor is `null`. There is no page number
  and no total, because the endpoints do not return one.
- **`restart()` is a no-op at the head of the walk**, which is exactly where a first-load failure
  leaves the reader — so a screen's "Try again" pairs it with a nonce in the fetch effect's
  dependencies (decision 51). `restart` alone made the button dead on the one page it was needed.
- **Selection is page-scoped, and the count says so.** `"n customers selected on this page"`. There
  is no "select everything matching this query": a keyset list has no total to size such a set with,
  and a bulk change over rows nobody has seen is how one mistaken filter becomes forty wrong records.
  The selection is dropped whenever `request` changes, so a verb can never act on an id the reader
  can no longer see, and both the bar's count and the verb's payload are intersected with the rows
  actually on screen.
- **`rowSelectable` and `rowLocked` are the same fact, said twice.** A row a verb could not act on
  has no checkbox *and* carries a visible reason. Either alone leaves someone hunting.
- **Absent versus disabled is a real distinction.** A verb the actor does not hold (`permission` on a
  `MenuItem`, `Can`, `ExportMenu`'s `permission`) is **absent** — a greyed item advertises a
  capability the reader will not get. A verb they hold but cannot use *right now* is **disabled with
  the reason** (`Already deactivated`, `Reactivate the customer to edit it`) and is refused on
  activation, not merely styled. None of this is authorization: the server checks every call
  ([CLAUDE.md](../CLAUDE.md) §5.1, §5.2).
- **Five states, and they are different sentences.** Loading is a skeleton of the real column widths;
  `error` splits `422` ("we couldn't accept those details" — recoverable, retry) from `5xx`
  ("something went wrong"); an empty page under a predicate offers `Clear filters` and says the
  filter is why, while a genuinely empty resource says so and offers the create verb. "No customers"
  under a filter is how a reader concludes a record was deleted and creates it a second time.
- **A `filtered` list always states its predicates.** Including the ones the screen imposed itself:
  the audit log ships a `fixed` chip reading `Security events excluded`, because a reader looking for
  a failed sign-in needs to know why it is not there ([audit](audit.md) §5.1).
- **JSON columns stay off the list.** Wide payloads live behind `renderDetail`, which fetches on
  expand and caches per row — one request per row the reader actually opened, and none for the ones
  they did not (api-conventions §3).
- **Export is a server request.** The endpoint re-applies field policy, covers the query rather than
  the page, is itself audited and answers with a signed expiring link (§6.15, §5.14). A file
  assembled from the rows in hand would be the page, with read-denied fields in it.
- **A destructive verb goes through `ConfirmDialog`**, whether it was reached from the bulk bar or a
  row's kebab — one path, one confirmation. The dialog states what will happen, counts the batch, and
  focuses Cancel first, so a stray Enter from the keypress that opened it dismisses.
- **Column preferences are a preference, not a policy.** `useColumnPreferences` persists the hidden
  set to `localStorage` per table id; `locked` columns are offered as inert and noted `Always shown`.
  Hiding a column changes nothing about the request and nothing about what the API returns — blocking
  a field is `field_policy`'s job (§6.15).
- **`columnsFromFieldSet` builds columns from the server's field set**, so a screen never hardcodes a
  field list ([identity-schema](identity-schema.md) §6.2). Custom fields land as `custom_fields.<key>`
  and are display-only: nothing priced, taxed, posted or routed reads one (§6.14).
- **A `link` cell's href is scheme-checked.** `column.href` reads a payload, and `external` exists
  because that payload legitimately points off-site — which is exactly how `javascript:alert(1)`
  arrives in a supplier's website field. `isSafeHref` (`lib/url`) allowlists `https:`, `http:`, a
  single-slash route, `#`, `mailto:` and `tel:`; anything else renders as plain text, because an
  anchor with no destination is still a tab stop announced as a link.
- **Semantic `<table>`, no `role="grid"`.** A grid promises a spreadsheet's keyboard model — arrow
  navigation, one tab stop for the whole widget — and a table that claims it without implementing it
  is worse for a screen-reader user than an honest table. What it does carry: a real `<a>` in the
  cell that navigates, `aria-sort` on the sorted header cell rather than on the button inside it, an
  `aria-busy` table while a page is in flight, and a hidden `role="status"` row count for a reader who
  cannot see the shape of the page.
- **The horizontal scroller is a named, focusable region.** A wide table's off-screen columns may hold
  nothing focusable at all — a row of figures and a status chip — and arrow keys scroll a container
  only while focus is already inside it, so a `div` with `overflow-x: auto` and no `tabindex` is
  content a keyboard cannot reach (WCAG 2.1.1). The shell carries `role="region"`, `tabIndex={0}` and
  the caption as its accessible name, so a reader hears *which* table they have stepped into. The cost
  is one tab stop per table, which is the accepted trade of this pattern.
- **The stacked layout lifts the height cap, it does not merely restyle the rows.** With the heading
  row clipped there is no frozen header for a nested scroller to serve, and a scroller inside the
  page's own is worst exactly where the viewport is smallest — so `max-height` goes away with the
  header it existed for. `DataTable` tells the stylesheet through `data-stack`, because CSS cannot ask
  a component whether stacking is switched on.
- **One plural rule, in `lib/text`.** `pluralNoun` / `pluralOf` handle the consonant-`y` and sibilant
  endings (`company` → `companies`, `tax` → `taxes`) and are shared by the pager's range and button
  labels, the bulk bar's count and the table's row-count status — three components that each had their
  own `${noun}s`. Zero takes the plural, as English does. `Pager` and `BulkBar` accept `nounPlural`
  for a noun no rule covers: an invoice **series** pluralises to itself ([fiscal-year](fiscal-year.md)
  §7), and a dictionary of exceptions here would be a dictionary to maintain.
- **A control is hit larger than it is painted.** A chip's `×` and a table's in-cell affordances stay
  small — a chip is a label first — but each grows its target with a transparent `::after` overlay
  rather than with padding, which would push the glyph off centre. The filter bar's text `Clear all`
  carries a `min-height`, since a bare text button is only as tall as its line box.

**Not in v1, deliberately:** no virtualization (a keyset page is 25–200 rows; the ceiling is the
page size, not the table), no drag-resize columns, no footer aggregates over a page that is not the
result set, and no grouping or tree rows until a screen needs them.

`packages/ui/src/styles/table.css` holds the whole surface. It keys off `data.css`'s tokens and is
imported by the apps that show a table — the auth app never loads either. Everything directional in
it is a **logical** property (`inset-inline-start`, `margin-inline-end`), because the pinned offsets
are set inline by the component and a physical `left` in the sheet would not be the same property to
override; `--janso-table-ctrl-w` is the fixed control-column width those offsets are computed from,
which is why it is a token and not a measured value.

### 5.12 `CommandPalette` — search or jump to

A modal dialog holding a combobox and a listbox (the WAI-ARIA combobox pattern). Focus stays in the
input; the arrows, Home and End move the highlighted option, announced through
`aria-activedescendant`; Enter chooses; Escape, the scrim, or choosing closes it and returns focus to
whatever opened it. The focus trap, Escape and focus restore are `useDialogA11y`'s.

- **`items`**: `{ id, label, group?, icon?, keywords?, hint?, permission? }`. An item whose
  `permission` the actor lacks is **absent**, never greyed — the same rule as the rail, and the
  console builds its items from `navSections` with the rail's own keys so the two cannot disagree.
  Presentation only: the destination still enforces the permission.
- **Matching**: a label prefix ranks above a word prefix, which ranks above a match anywhere
  (keywords and the group included). Ranking is within a group, and groups keep the caller's order,
  so a heading never prints twice and the list does not reshuffle in ways that cannot be learned.
- **Shortcut**: `useCommandPaletteShortcut(open)` accepts ⌘K and Ctrl+K on every platform and
  ignores IME composition. `CommandTrigger` is the visible way in — a button, not an input — and
  resolves its own key cap (`⌘ K` on Apple devices, `Ctrl K` elsewhere) after mount, so server and
  client renders agree; `shortcut` overrides it.
- The highlighted option is marked with an inset `--janso-focus` edge as well as the
  `--janso-selected` tint: in a combobox the highlight *is* the focus indicator.

---

## 6. Conventions

- **Class names** are `janso-`-prefixed BEM-ish: `janso-card`, `janso-card__header`,
  `janso-card--nested`. Tones are data attributes, not classes: `data-tone="warn"`
- **Figures** carry `.janso-figure` (tabular numerals) — always, everywhere
- **Icons** are 24×24 `viewBox`, `stroke="currentColor"`, `fill="none"`, sized by the caller,
  `aria-hidden` unless they are the only label
- **Focus** is always visible: `:focus-visible` → `--janso-focus-ring`. Never `outline: none`
  without a replacement
- **Motion** respects `prefers-reduced-motion`, honoured once at the root
- No inline `style` for anything a token covers

---

## 7. Accessibility floor

Non-negotiable, and each is a test:

- Every interactive element has an accessible name
- Contrast per §2.4, verified in all three palettes
- Keyboard reachable and operable, in DOM order; visible focus at every stop
- `role="tablist"` / `radiogroup` implement arrow-key semantics, not just the roles
- Status is never colour alone
- One `<h1>` per page; headings descend without skipping

---

## 8. Testing

Per [CLAUDE.md](../CLAUDE.md) §7 — every shared component and every page ships tests. Vitest +
React Testing Library, run from each package.

Per component: renders · every conditional branch and every `tone` · accessible name, role and
focus · keyboard interaction where it has any.

Per theme, as system-level tests:

- **Token parity** — the three theme files define identical key sets
- **No colour literals** — no hex / `rgb()` / `hsl()` outside `theme-*.css`, with the §1
  exceptions allowlisted by path
- **Resolution** — all four preferences, plus a live OS change while on `system`
- **Pre-paint** — `themeScript` sets the same value the provider would

Formatting tests cover a non-`en` locale, `indian` and `western` grouping, precision and
rounding from config rather than locale, and string-in → string-out.

Per list screen, against a loader that applies the **real** cursor, filter, sort and limit rules —
so a cursor reused across a query change earns the same `422` it would earn in production rather than
a convenient page:

- the first page, with every figure read through the session's display config
- a sort request per allowlisted header, and **no** control on a key the endpoint would refuse
- search: the debounced request, a term below the minimum sending nothing, and the chip stating what
  the search actually matches
- the walk forward and back — no row seen twice, `cursor: null` at the head — and a page-size change
  restarting it
- selection scoped to the page, unselectable rows having no checkbox, and the selection dropped when
  the query changes
- a destructive verb: confirmation shown, cancel inert, confirm re-querying and reporting
- each row verb present for a permitted actor, **absent** without the key, and disabled-with-a-reason
  where the row forbids it
- `422` and `500` each rendering their own state, and `Try again` actually re-requesting the page

---

## 9. Decision log

2026-11-04 searchable dropdown focus: single-selection `SearchSelect` keeps its selected
label visible on focus and opening. Typing starts a separate replacement search;
dismissal restores the committed value without emitting a selection change. This fixes
selected fields appearing empty when reached by Tab or click across all consumers.
Shared UI version 0.1.63; pointer, keyboard, remote lookup, dismissal and explicit-clear
regressions accompany the change.
Verification: 204 dropdown/custom-field tests, 121 consuming-form tests and workspace
TypeScript checks pass. Browser checks pass at 1440px and 390px in light, dark and ledger
themes, including replacing the label after reopening, without browser errors. Pointer
entry suppresses native caret placement until an actual search is being edited.
The workspace lockfile was refreshed; consumers use unchanged workspace links. Manual
simplification and security/correctness review found no additional issue; review slash
commands are unavailable. The broader UI run also exposed existing `FieldGroup` client
boundary and `AttributeValueInput` ambiguous-label failures outside this change.

2026-11-04 product-section scrolling: reproduced a 407px document offset after opening
Barcodes, leaving the same empty band below the shell even when its content was scrolled
back to the top. Section navigation now adjusts only the app content scroll position
and retains accessible focus. This does not change routes, return links, product data
or unsaved-change guards. Regression tests cover deep links and related-action clicks.
All 82 affected product tests and the scoped TypeScript check passed. Manual simplicity
and security review found no additional issue; financial writes and authorization are
unchanged. The review slash commands are unavailable in this environment.
Live verification on the reported MASCPL product covered Details, units and Barcodes:
the document offset stayed zero, the shell filled the viewport, and scrolling back up
restored the product heading. Desktop (1440px) and narrow (390px) captures were inspected;
the narrow layout had no horizontal overflow. Catalog intermittently refused reads with
`verified current Identity context is required`; Retry loading recovered. That source
freshness issue is separate and remains outside this scrolling fix. No product writes
were made during verification.

2026-10-30 branding decision: the user selected KiscoBooks and Khushiyan Enterprise.
Use one shared two-colour text lockup, retain the ledger tile and internal selectors,
and change visible app/preview/recovery copy and accessible labels together.
Verification and deployment limits: [KiscoBooks branding plan](kiscobooks-branding-plan.md).

### Master directory filter alignment (2026-10-30)

Directory search, native dropdowns, entity lookups and date filters use `FilterBar`.
The simple-product directory now uses that shared layout. In `table.css`, each
query field keeps its visible label beside the control and its hint/error below
the control. Filter controls use the shared 36px height token, and query fields
shrink/wrap within the available width. Ordinary forms and explicitly stacked
dropdowns retain their layouts. These rules also cover reference/date filters in
accounting, warehouse, stock and tax directories without per-page CSS overrides.

Shared UI version: 0.1.37. Consumer lockfile resolutions remain workspace links;
the version change does not change those links. Browser geometry regressions cover
1440px, 768px and 390px widths, mixed field kinds, hints and stacked-form isolation.
Live available-master results are recorded in the tenant-admin execution ledger.

| # | Decision | Why |
|---|---|---|
| 1 | Three palettes (`light`, `dark`, `ledger`) + `system` as a resolver, not a fourth palette | A stored `system` follows the OS across machines; a stored resolved value can't |
| 2 | Colour lives in `theme-*.css`; every other stylesheet is colour-free and token-only | Two palettes drift the moment one literal survives. Enforced by test, not discipline |
| 3 | `tokens.css` keeps only non-colour tokens | Type, space and radius are theme-invariant; duplicating them per palette would be three places to change one scale |
| 4 | Signals are `{ink,tint,line}` triplets | The whole reference vocabulary — emphasized tiles, count badges, warning rows — collapses into one primitive |
| 5 | The logomark stays theme-invariant | It's a self-contained gradient SVG that carries its own colour; a brand mark that repaints per theme stops being a brand mark |
| 6 | ~~Cards keep the 6px ledger radius rather than the reference's 10–12px~~ — superseded by 70 | The console must look like the same product as the auth screens |
| 7 | Shell primitives go to `@janso/ui` from day one, not after a second consumer appears | Every authenticated MFE needs the rail and top bar; the auth split-screen stays in its app because nothing else will ever want it |
| 8 | Hand-rolled SVG `BarChart`, no chart library | A dependency needs a stated reason ([CLAUDE.md](../CLAUDE.md) §5.15). Revisit when a chart needs interaction beyond hover — then Recharts, deliberately |
| 9 | `--janso-font-mono` is a system stack | A second webfont for a `USD` badge is not worth the request |
| 10 | Money and quantities are strings in the client, end to end | Float coercion is silent; the client is the last place it would be caught |
| 11 | Tabs are client state, not routes, in the first console screen | The tabbed views have no data yet; promoting them to routes is a change of one component when they do |
| 12 | Chips carry their tone on the border and an accent glyph, not as a tinted fill | A chip states context. Two saturated pills side by side in the top bar read as two alerts — the opposite of what they are for. The tone is still never colour-alone: a text descriptor rides along |
| 13 | Chart palettes are validated with a script, and the measured ΔE is recorded in the theme file | The first version of these tokens was hue-picked and *failed* colour-blind separation in all three themes while the doc claimed it passed. Anything asserted about colour that can be computed must be computed |
| 14 | A separate `--janso-control-line` at 3:1, rather than lifting `--janso-line` | An empty input is defined entirely by its edge (WCAG 1.4.11), but a card border is decoration. One token for both would either fail the control or shout on every card |
| 15 | The focus ring is a solid 2px ring plus a halo, not a halo alone | The original translucent-only ring measured 1.4–1.9:1 against every surface in all three themes: `outline: none` with an invisible replacement is worse than no rule at all, because it looks deliberate |
| 16 | Business dates are formatted without ever entering a timezone conversion | `'2026-07-01'` is a `posting_date` bound with no instant attached. Treating it as UTC midnight rendered the fiscal period a day early for every company in a negative-UTC offset — a wrong date on a financial report |
| 17 | A date that parses but isn't real renders an em-dash, not a rolled-over date | `new Date('2026-02-30')` silently yields 2 March. A confident wrong date is worse than a visible gap, and bad importer output is exactly how it arrives |
| 18 | `DisplayConfig` carries the separator, symbol-position and negative-format fields from [company](company.md) §4.5 | Hardcoding `.`/`,` and a prefix symbol quietly ignores a company's configured presentation. `show_amount_in_words` stays out of scope — it is a document concern, not a figure |
| 19 | The pre-sign-in screens get the theme switcher too | A returning user meets `/login` before anything else, and the cookie and `localStorage` the pre-paint script reads work without a session — so the choice is available immediately and carries into the console |
| 20 | `SearchSelect`'s list is portalled and fixed-positioned, not absolute inside its parent | An absolutely positioned popover is clipped by any ancestor with `overflow` — that bug hit `UserMenu` in the top bar and put a scrollbar on the tab strip. A picker will live inside cards, toolbars and scroll regions, so it cannot depend on its ancestors. No positioning dependency: `popover` + CSS anchor positioning replaces most of the JS once Firefox and Safari ship anchor positioning |
| 21 | `SearchSelect` takes a `loadOptions` function rather than an endpoint | Keeps the library free of any service's routes and lets one control serve customers, items and accounts. The same mechanism-vs-policy line as `libs/platform` |
| 22 | Changing the query always resets the cursor | A cursor is bound to its query, filters and sort; reusing one after a change is a `422`. Making this a rule of the control rather than a caller's responsibility means it cannot be forgotten per call site |
| 23 | The input's text and the list's query are separate state | A commit in multiple mode clears one and not the other. One value meant choosing between an input the user must clear by hand and a list that blanks itself on every pick |
| 24 | Auto-paging is gated on the row count, not on the cursor | An empty page is legal and still carries a cursor, so a cursor-identity guard lets the next one straight through and the list chases pages to the end of the table. Paging resumes only once the list has actually grown |
| 25 | Stale-response guarding uses a request id as well as `AbortController` | An aborted request can still settle first, and the failure is invisible: the list shows results for a query the user has already moved on from. Cheap to add, impossible to notice missing |
| 26 | `SearchSelect` tracks *which query the rendered rows belong to*, not just the current query | Everything derived from "the results" — the create-new row, the truncation notice, the empty state — is otherwise judged against the previous query's rows during the debounce. One piece of state fixes a class of defect rather than three symptoms |
| 27 | The `maxOptions` truncation notice is gated on rows actually having been dropped, not on the row count reaching the cap | A final page that lands exactly on the cap is complete. Telling someone to narrow a search that already showed them everything is worse than saying nothing |
| 28 | `Select`'s stylesheet moved from `data.css` to `janso-ui.css` | A form field is a framework primitive, and `data.css` is not imported by every app — the auth app never loads it, so the control rendered unstyled there. Where a component's CSS lives is part of its contract, not a filing preference |
| 29 | `Select` renders an empty row whenever `value` matches no option | A native `<select>` with an unmatched value has `selectedIndex === -1` and renders **blank**, with nothing on screen to explain it. `Select…` is a visible, honest empty state; it is `disabled` when the field is `required` so it cannot be chosen back |
| 30 | `Select`'s `loading` disables the control but mirrors an already-chosen value into a hidden input | A `disabled` select submits nothing, so a form posted while options refresh would silently drop a field the user had already answered. "Busy" and "withheld" are different states and only the second should lose the value |
| 31 | `FileUpload` never uploads and never authorises — the caller owns transport, the server re-validates every limit | An upload belongs to a service and a tenant. `accept` / `maxSizeBytes` / `maxFiles` exist so someone is told before a 10 MB round trip; treating them as enforcement would put the only size check in the client, reachable by a replayed request ([CLAUDE.md](../CLAUDE.md) §5) |
| 32 | File names are stripped of bidi controls before they are rendered anywhere | `invoice<U+202E>gnp.exe` displays as `invoiceexe.png`. Every layer renders the name the OS handed it and React escapes markup without undoing this, so the strip has to happen where the name enters the UI |
| 33 | An `uploading` row with no `progress` is an indeterminate progressbar, not `aria-valuenow={0}` | Zero is a claim that nothing has been sent. "In flight, unmeasured" is a defined ARIA state and the honest one for a transport that reports no progress events |
| 34 | `FileUpload`'s validation is written against **drops**, not the picker | `accept` filters the file dialog and does nothing to a dropped file. Testing through the picker would have proven only the path the browser already guards |
| 35 | Email, phone and password are components, not conventions on `TextField` | Their value is seven invisible attributes each. A convention gets retyped per screen and is wrong on one of them every time — and the wrong `autocomplete` on a password field is a password manager filling the old value into a "new password" box |
| 36 | `EmailField` normalizes on blur and lowercases only the domain | Rewriting per keystroke fights the caret. Lowercasing the local part too would silently change the mailbox on the servers that honour RFC 5321's case-sensitivity — most providers fold it, but "most" is not a guarantee to make on someone's behalf |
| 37 | `isEmailLike` is deliberately permissive | Every strict RFC 5322 regex rejects deliverable addresses. Being wrong here means a customer who cannot be invited; being loose means a bounced verification mail, which the platform already handles |
| 38 | `PhoneField` reports two values, matching the two columns | `phone_country_code` + `phone` is the stored shape. One E.164 string would be re-split by every caller, differently, and `toE164()` gives the transports the one form they need |
| 39 | `PhoneField` sets **no** `maxlength` and caps in JS instead | The browser truncates a *paste* before any handler sees it, so `+91 9876543210` under a 13-digit cap silently loses its last digit. The correct cap is only knowable after the dial code is split off |
| 40 | `PhoneField` has no `role="group"`; the label names the number input and the picker names itself | Two controls sharing one accessible name is worse than no grouping — it makes every label query ambiguous and tells a screen-reader user nothing. Each half is named, which is what the floor in §7 asks for |
| 41 | The strength meter caps a repeated character or a straight run at 1, and pays a bonus at 16 characters | `12345678` scored "Fair" for containing digits, and a passphrase scored below `P@ss1x!`. A meter that is confidently wrong is worse than no meter, because it is advice |
| 42 | The password toggle's accessible name carries the field name | A create-account form has two "Show" buttons. The visible word stays inside the name so speech control still works (WCAG 2.5.3) — this changed one existing assertion, which is a behaviour change and is recorded as one |
| 43 | `PhoneField` holds a typed `+` in local state until it names a country | Digits-only state has nowhere to keep the `+`, so stripping it on that keystroke meant a *typed* international number could never split — only a pasted one. It stored `+91` twice and `isPhoneLike` accepted the result. Held for at most four digits, the longest code the ITU issues |
| 44 | A `00` prefix is read as international only for a string long enough to be a whole number | `001` is also what a national number beginning `001…` looks like three keystrokes in. There is nothing in a change event that distinguishes them, so the ambiguous case stays national |
| 45 | `EmailField` writes the tidied address onto the input before the caller's `onBlur` | Validation on blur reads `event.target.value` — the only value a caller has at that moment. Handing over the untidied text produced an error message about an address the field was in the middle of fixing |
| 46 | `hideLabel` clips the label, not the label row (`Select`, `SearchSelect`, `FileUpload`) | `janso-visually-hidden` hides without removing, so an `action` inside the hidden row was a focusable, invisible tab stop (WCAG 2.4.7). Two existing assertions moved from the wrapper to the label — a behaviour change, recorded as one |
| 47 | `FileUpload` screens duplicates on the tidied name, and keys rejection rows by position too | Both are the same class of bug: comparing two spellings of one name, and a React key built from a name and a reason that a batch of three identical files produces twice |
| 48 | `SearchSelect` keeps a cursor when the query it belongs to is typed back verbatim | Multiple mode clears the input on a commit and keeps the results, so the identical query can arrive in one change event — `filterQuery` never changes, the search effect never re-runs, and a dropped cursor is never minted again. The rows stayed with no way to page past them |
| 49 | The list surface is **nine composable pieces**, not one `<Table>` that owns the query, the toolbar and the pager | Every screen needs a different subset — the audit log has no search, no selection and no row verbs at all — and a component that owns all of it grows a boolean per screen. `DataTable` renders rows; `useListQuery` owns the query; the screen composes. The same mechanism-vs-policy line as `libs/platform` |
| 50 | A `Column` is **data** — `{key, header, type, …}` — and the table decides the markup | `type: 'money'` formats through the reader's own display config in one place. The alternative is forty call sites each reaching for `toLocaleString()`, which is precisely the locale-default bug [company](company.md) §4.5 exists to prevent. `render` is the escape hatch and is handed the formatters, so even a bespoke cell cannot fall back to a browser default |
| 51 | "Try again" bumps a nonce in the fetch effect's dependencies as well as calling `query.restart()` | `restart` is a deliberate no-op when the walk is already at its head — and a first-load `422` or `500` leaves the reader exactly there, so the button was dead on the one page it is most needed. Two console screens shipped with it; the failing tests were written first. `restart` stays because the likeliest `422` is a cursor the server refused, and both land in one update so it is still one request |
| 52 | The cursor stack lives in `useListQuery`, and every query mutator drops it — including `setLimit` | A cursor is bound to the sort, the filters, the search *and* the page size: the position it carries is expressed in pages of the size it was minted for, so honouring one across a resize returns the wrong window rather than erroring. Making it a rule of the hook is the only version that cannot be forgotten in the next screen |
| 53 | Selection is scoped to the visible page, and there is no "select all matching this query" | A keyset list has no total to size that set with, and a bulk verb over rows nobody has seen turns one mistaken filter into forty wrong records. The count says "on this page" for the same reason, and the selection is intersected with the rendered rows and cleared whenever the request changes |
| 54 | A verb the actor lacks is **absent**; a verb they hold but cannot use now is **disabled with the reason** | A greyed item advertises a capability the reader is not going to get; a silently missing verb they *do* hold sends them hunting. Both are cosmetic either way — the server checks every call ([CLAUDE.md](../CLAUDE.md) §5.1) — so the only question is which one informs, and it differs by case |
| 55 | The filtered-empty state and the genuinely-empty state are different sentences | "No customers" under an active filter is how a reader concludes a record was deleted and creates it a second time. One offers `Clear filters` and names the predicate; the other offers the create verb |
| 56 | Every predicate in force is a chip, including ones the screen imposed on itself | The audit log's `Security events excluded` is unremovable and still stated: it is a separate surface behind `audit.read_security` ([audit](audit.md) §5.1), and a reader looking for a failed sign-in must not conclude there were none |
| 57 | Wide and JSON columns live behind `renderDetail`, fetched on expand and cached per row | A list must not return JSON columns (api-conventions §3), and eager-loading the detail for 25 rows to show the one that gets opened is 24 wasted queries against the widest columns in the table |
| 58 | Export is a server request, never a file built from the rows in hand | The endpoint covers the query rather than the page, re-applies field policy, is audited, and answers with a signed expiring link ([CLAUDE.md](../CLAUDE.md) §5.14, §6.15). A client-built file is the page, with read-denied fields in it |
| 59 | A plain semantic `<table>`, not `role="grid"` | A grid promises a spreadsheet keyboard model — arrow-key cell navigation, one tab stop for the widget. Claiming the role without implementing it leaves a screen-reader user worse off than an honest table, and the model is not what a list of records needs |
| 60 | No virtualization, no drag-resize, no footer aggregates, no tree rows in v1 | The row ceiling is the page size (25–200), so virtualization buys nothing and costs the accessible table. A footer total over a page that is not the result set is a wrong figure presented as a subtotal — worse than no figure. Grouping ships when a screen needs it |
| 61 | `formatRelative` was added to the shared formatters, and no *column* is rendered with it by default | "2 hours ago" computed on the server and again in the browser disagree — a hydration mismatch on the audit log's leading column. The elapsed form is prose inside a detail panel, which only ever renders client-side; the column states the instant, which is what an auditor cites |
| 62 | The href scheme allowlist moved out of `ListRow` into `lib/url`, and is exported | It was written once, documented as load-bearing, and then not applied to the `link` cell the review pass found rendering `column.href` straight into an `<a>` — the same payload-derived href, the same session. A security check that lives in one component is a check the next component does not have. Now stricter than the original in two ways: `//host` is refused (a single slash is a route, two are a host) and the stripped set covers every C0/C1 control, not just the C0 range |
| 63 | `useListQuery` decides "did the query change?" in one place, through `listQueryString` | The guard had been written per mutator, and `setFilter` / `setFilters` did not have one — so re-selecting the value a `<select>` already showed produced a new-but-equal query object, and every screen's fetch effect is keyed on that object. A second request for the page already on screen, from a control that did nothing |
| 64 | The table's horizontal scroller is a focusable, caption-named `role="region"` — accepting one tab stop per table | A wide table's off-screen columns are often figures and status chips with nothing focusable in them, and arrow keys scroll a container only once focus is inside it: the columns were keyboard-unreachable content (WCAG 2.1.1). The alternatives are worse — a visible scroll button duplicates a native gesture, and making every cell focusable is the grid model decision 59 refused |
| 65 | `data-stack` on the shell, and the stacked layout drops `max-height` rather than keeping a scroller | The height cap exists to give the sticky header something to stick within; once the heading row is clipped there is nothing to freeze, so the cap only nests a scroller inside the page's own — on the narrowest viewport there is. CSS cannot ask a component whether `stack` is on, hence the attribute. `overflow-y: visible` is *not* set alongside it: `overflow-x: auto` computes it back to `auto`, and an uncapped box has nothing to scroll |
| 66 | One plural rule in `lib/text`, with an explicit `nounPlural` escape hatch instead of an irregulars dictionary | Three components wrote `${noun}s` independently, and the platform's second resource is `company` — "2 companys selected on this page" shipped. A dictionary would be a dictionary to maintain; the rule covers consonant-`y` and sibilant endings, and the one real irregular here (an invoice **series**, whose plural is itself — [fiscal-year](fiscal-year.md) §7) is stated by the screen that names it |
| 67 | `ConfirmDialog`'s typed-phrase gate matches trimmed and case-insensitively (`delete`, `LOCK FY2026`), and `tone="danger"` now carries its own visual treatment | The gate is deliberate friction that proves intent; the *words* are the proof, so a caps-lock or a trailing space blocking a correct phrase was friction without safety. Separately, `data-tone="danger"` had been a dead attribute — it set only the confirm button variant and the initial focus, so a destructive dialog looked identical to an ordinary one. It now adds a danger-tinted alert badge beside the title and a top accent strip (an inset shadow, so it follows the rounded corners and shifts no layout between tones), keyed off the existing `--janso-danger-*` tokens; ordinary confirmations stay unadorned, because an icon on every dialog means nothing |
| 68 | `Toast` reuses `Notice`'s tone→icon map (`TONE_ICONS`, exported) rather than keeping its own | An inline banner and a floated toast both saying "success" must not be two different greens or two different check marks. The map was written once and is now imported by both; a second copy is the copy that drifts. The toast also defaults an **error** to persistent (`duration: null`) — a failed save that fades before it is read is a failure the reader never learns about, and notifications are ephemeral UI, never the durable record (that is the audit log) |
| 69 | The focus trap / Escape / focus-restore / scroll-lock is one hook (`lib/dialog` `useDialogA11y`); `Modal`, `Drawer` and `ConfirmDialog` all consume it, and `Modal`/`Drawer` share one `Overlay` and one `janso-overlay-*` chrome | A focus trap that lets Tab wander out of one dialog but not another is exactly the drift a second copy invites (CLAUDE.md §3). `ConfirmDialog` was refactored onto the hook with its DOM, classes and behaviour unchanged, so its suite passed untouched; the refactor also gave it the body scroll-lock it had been missing — an intended addition, not a regression. `Modal` (centred) and `Drawer` (inline-end sheet) are the same overlay differing only in placement and entrance, so they are one component behind two thin wrappers |
| 70 | Re-skin to a dense, precise product look: Inter as the single family on a 14px body; radius `sm` 4→6px and `md` 6→10px (supersedes decision 6); rail 288→248px (collapsed 72→64px), top bar 3.75→3.5rem, page cap 1600→1440px; KPI figures 34→28px; refined neutrals and a brighter indigo brand (`#4a4fd4` light, `#9599f7` dark, `#4246c4` ledger) with a re-cut logomark gradient; sentence-case labels in place of uppercase overlines; a neutral raised rail selection; layered popover shadows; and a focus ring that adds a 1px surface gap before the solid 2px `--janso-focus` stop (decision 15's solid ring and halo are kept) | The first palette and type scale were correct but generic and loose: 15–17px body copy, uppercase tracked labels on every heading, brand-tinted fills on selection and two webfonts made each screen loud and sparse at once. The new scale fits about a third more on a laptop screen. Every contrast gate in §2.4 still passes in all three palettes (`contrast.test.ts`), and the token key set is unchanged, so no component API moved. The chart series tokens were **not** re-tinted: they are validated values (decision 13) and the validator is not in the repo, so changing them waits until it can be re-run |
| 71 | The table's identifying link column reads in ink (500), turning brand on hover; row icon buttons are a size down; rows are 44px; the filter bar is one top-aligned row, with `TableSearch` hiding its label through `TextField`'s `hideLabel`; dense hosts use `IconButton size="sm"` rather than a container override; the filter and bulk bars carry no outer margin and the page column sets what follows them at `space-3` | A column of brand-blue names was the loudest thing on every list and only said "clickable", which the pointer and underline already say. Hiding the search label through a prop keeps the input's accessible name while letting every control in the bar start on one line; the hint hangs below instead of dragging the selects to its baseline |
| 72 | `--janso-overlay-line`, a popover-edge token separate from `--janso-line-strong` | Popovers had used `--janso-line-strong` for the dark-theme 3:1 edge, which made every light menu and dialog look outlined. Measuring it showed the dark value was **2.66:1** on the lifted `--janso-overlay` — a fail the old pairing never checked, since it measured against `surface`. The new token is a hairline in light/ledger and 3.2:1 in dark, and `contrast.test.ts` now measures it on `overlay` and `paper` |
| 73 | Toasts are a neutral overlay surface with the tone on the icon; inline `Notice` keeps the tinted triple | A toast floats over arbitrary content, and a full signal tint fought whatever was beneath it. Same icon map (decision 68), so the two still agree on each tone; each signal ink is now measured at 3:1 on `--janso-overlay` |
| 74 | A busy `Button` keeps its variant's fill and shows `cursor: progress`, instead of falling to the disabled grey — the disabled fills are scoped `:not([aria-busy='true'])`, so no fill is restated | The reader just pressed it; a primary that turns grey under the pointer reads as "that failed". It is still `disabled` and `aria-busy`, so nothing about the double-submit protection changed |
| 75 | KPI tiles take a `trend` slot, and the dashboard fills it for Invoiced and Collected from each measure's own weekly series; no period-over-period delta yet | The series is already in the payload, so the sparkline is real data. A "vs last period" delta would need a prior-period figure the reports contract does not carry — adding one is a contract decision, not a UI one, and it is left open (§10, item 1) |
| 76 | Chart series 1 moves onto the brand indigo (`#4a4fd4` light and ledger, `#7075e8` dark); slots 2–8 unchanged | Series 1 is documented as "reads as the brand", and after decision 70 it no longer did. Re-validated with the dataviz `validate_palette.js` against `#ffffff`, `#fffdf8` and the new dark surface `#131418`: every check passes with the same worst-pair figures as before (ΔE 10.7 / 8.6 deuteranopia, 18.9 normal, all ≥ 3:1) |
| 77 | A `CommandPalette` in `@janso/ui`, opened by ⌘K / Ctrl+K or a top-bar trigger, built from the rail's own nav and permission keys | A keyboard path to every page is table stakes for software used all day. Building it from `navSections` means it can never list a page the rail hides. Hand-rolled on `useDialogA11y` rather than a dependency (§5.15 of CLAUDE.md), for the same reason the menu is |
| 78 | `SearchSelect` remains the shared listed autocomplete; `scopeKey` resets dataset state, retries retain their cursor, required validity follows IDs, and creation waits for complete search results | The 2026-10-24 review reproduced stale selection, missing focus, inaccessible retry, incorrect dynamic labels and late creation callbacks. Unknown IDs stay visible and removable without fabricated callback options. IME and dialog Escape follow the input's interaction state. Version 0.1.18; execution and validation are recorded in [searchable-dropdown-review](searchable-dropdown-review.md) |
| 79 | `RailGroup` provides a working parent link and a separate accessible submenu disclosure; callers resolve scopes and the deepest active destination | The 2026-10-24 navigation review reuses one permission-filtered tree for the rail and command search. Desktop collapsed rails retain child icons; mobile drawers retain disclosures. Version 0.1.19; evidence is recorded in [administration navigation review](administration-navigation-review.md) |
| 80 | `required` draws a visible mark, automatically, from the same prop the control already takes — outside the `<label>` and `aria-hidden` | It was reaching only the native element: four of six fields on the company wizard's first step were required with nothing on screen saying so, and the only feedback was a failed submit. Outside the label because `getByLabelText` reads raw text and 426 queries across 169 console test files match on it; `aria-hidden` because `required` on the control is the statement and the asterisk is its echo |
| 81 | `FieldGroup`/`FieldPair` group a form and pair two short fields; `ChoiceCard` is the card-shaped checkbox, named by its title alone | The wizard's Presentation step was 22 controls in one undifferentiated column with a one-character separator in a full-width box, and its capability step was seven flat checkboxes whose descriptions were not part of their hit area and whose three-level dependency chain was stated in prose. `aria-labelledby` on the title because a label wrapping a whole card puts its description into the control's accessible name |
| 82 | Inter is self-hosted in `@janso/ui/styles/fonts.css`, not merely named in the tokens | The tokens had named it since they were written and nothing loaded it, so every screen rendered in a fallback face while the base rule applied Inter-specific tracking and OpenType features. A CDN is wrong for on-premise software; one variable woff2 covers every weight the tokens ask for |
| 83 | The `janso-tabs` strip carries `aria-current="page"` as well as `aria-selected="true"`, so one strip serves client tabs and routed area links | The notification console has thirteen areas, each its own URL, drawn as thirteen `janso-link`s in a row: the open area had no mark at all and every label the same weight. They cannot become a `role="tablist"` (decision 11), so the two existing tab selectors gained the `aria-current` case rather than growing a second near-identical block — which is how the two would have drifted apart |
| 84 | `.janso-preview__text` — verbatim content inside the shared preview panel: mono, `pre-wrap`, `overflow-wrap: anywhere` | Template bodies, rendered previews and provider payloads were bare `<pre>`s at the UA default, so the first long line scrolled the card sideways and hid the rest of the message. It extends the existing preview panel rather than adding a stylesheet |
| 85 | `.janso-setup` is its own scroll container (`block-size: 100dvh; overflow-y: auto`), with `scroll-padding-bottom` moved off `html` onto it (§4.4) | `apps/console` sets `body { overflow: hidden }` for the shell, which propagates to the viewport on every shell-less route: `/companies/new` was its full height with the lower half unreachable by wheel, trackpad or scrollbar, while `scrollTo` and Tab-into-view still worked — which is exactly why the 2026-10-26 review's browser probe, which scrolled with `window.scrollTo`, reported the page scrollable. A shared layout decides its own scrolling, like `.janso-shell`, instead of depending on a host's `globals.css` |
| 86 | `.janso-fieldpair` and `.janso-fieldgroup__fields` reset `.janso-field + .janso-field`'s `margin-top`, and a pair is `align-items: start` | The grid gap already spaces them, so the stacked-column margin was additive: it put the second field of every pair 16px below the first — "Incorporation date" beside "Entity type" and visibly lower — and doubled a group's 16px gap to 32px. `.janso-form-grid` carried this reset from the day it was written; the two containers added for the wizard did not, and nothing in a `css: false` suite can see the difference |
| 87 | `GroupedBarChart` joins `BarChart`: several series per category on one scale, always with a text legend, built on the same geometry helpers | The business overview needs income beside expenses. A second single-series chart would have repeated the scale, grid and label thinning; two charts side by side cannot share a scale, so the comparison the page exists to make would have been by eye. No chart library was added (decision 8): the interaction needed is still hover only. Palette slots 1 and 2 are already validated adjacent pairs (decision 13), so no token changed |
| 88 | `ContextSwitcher` scrolls its options between a search field and footer that retain their height | Six company rows exceeded the bounded popup and painted over Create company. The list now clips and scrolls its rows; keyboard focus scrolls the chosen row into view while footer actions remain visible. Version 0.1.59; verified in the browser and with the 44 switcher/picker unit tests. |

## 10. Open questions

1. **Period-over-period comparison on KPI tiles.** A "▲ 12% vs Q1" delta needs the prior period's
   figure for each total. The overview response (`GET /v2/companies/{id}/overview` on `reports`)
   carries only the selected period. Which comparison is canonical — the previous period,
   the same period last fiscal year, or both — and does `reports` return it computed, or the raw prior
   totals? `StatTile` has no `delta` prop until this is settled (decision 75).
2. **Theme switcher placement.** It still occupies the top bar. Moving it into the user menu needs a
   menu that can hold a radio group, which `UserMenu` (`role="menu"` of `menuitem`s) cannot express
   today; the alternative is a Preferences page. Which one?


## Setup wizard additions ? 2026-10-20

`Stepper({steps, current, onStep?, orientation?})` is shared sequential navigation.
`orientation` defaults to `vertical` for setup sidebars; `horizontal` provides a
compact page-wide progress row and uses the shared two-column layout on mobile.
Product import uses this variant. `steps` is a readonly
string array; `current` is its zero-based active index. Only current/completed steps can
invoke `onStep`; without a handler all buttons are disabled. The active item exposes
`aria-current="step"`, completed/upcoming status is announced independently of colour.
Shared `styles/setup.css` uses the existing theme tokens for the wizard shell, connection
rows, review details and narrow-screen step layout. Screens move focus to their heading
when the step changes. Existing Card, Notice, Badge, Button, TextField, Select and Checkbox
components provide form and status controls; no app-local wizard stylesheet is introduced.
The shared `.janso-setup__fields` grid also serves tenant drawers. It uses `space-4`
between controls, removes stacked-field sibling margins, and resets direct paragraph
margins so the grid alone controls the spacing.

Account registration (2026-10-20) uses `styles/registration.css` for the wider Auth
form, responsive detail fields, grouped password inputs and manual-review result.
It reuses TextField, PasswordField, Button and Notice in all three themes. The
success region receives focus; server validation returns focus to the first
invalid field. Password strength guidance is advisory; Authentik enforces policy.

Decision amendment (2026-10-20): the meter accepts the field's `minLength` and
counts Unicode code points, matching the registration validator. Registration
uses six as its minimum; valid six- and seven-character passwords are rated Weak
with advice to choose a longer passphrase. Other consumers retain the default of eight.

Decision amendment (2026-10-20): shared setup/tenant form grids own their spacing.
Combining a grid gap with the ordinary stacked-field margin produced an excessive
40px separation; `space-4` now provides a single 16px gap across these screens.

Decision amendment (2026-10-20): `FilterBar` supplies an inline-label default to
query dropdowns through context, including wrapped controls, while preserving an
explicit layout choice and ordinary form defaults. Shared list CSS owns field
alignment, responsive wrapping and card gutters; list pages need no local overrides.

Decision amendment (2026-10-20): the AppShell scroll region uses a flex column with
non-shrinking content and footer. Content grows on short pages to keep the footer
at the viewport bottom, while long pages scroll to the footer in normal flow.
Shared shell CSS owns this placement; pages do not set footer offsets or heights.

Decision amendment (2026-10-20): `ActionCard` is the shared navigation card for
administration destinations. It provides one named link, an icon, heading,
description and trailing action. Disabled cards show a badge and a native disabled
button. `data.css` owns token-based gradients, focus, hover, reduced motion and the
responsive `.janso-action-card-grid`; apps supply content and permission gates.
Editors reuse `.janso-form-grid` and `.janso-grid--split`, with
`.janso-grid--start` to keep guidance cards at their content height.

Decision amendment (2026-10-20): the top bar hides direct context/role chips at the
existing 720px breakpoint, preserving theme, notifications and the named account
menu on phones without clipping popovers or introducing horizontal scrolling.

Decision amendment (2026-10-21): Console `/settings` reuses `ActionCard` and the
shared responsive grid for Payment gateway, Notifications, Countries and States.
All four are disabled placeholders with Coming soon labels and no destination or
configuration calls. Globe and map icons follow the shared line-icon convention.
Verification: Settings/shell/platform tests (23) and shared icon/card tests (222)
passed, alongside both TypeScript checks and the Console production build.
An isolated browser rendering the actual page and shell passed at 320, 390, 768
and 1440px in light, dark and ledger themes. The live route requires sign-in.

Decision 2026-10-21: `janso-form-grid--pair` keeps related controls in two equal
columns from 600px upwards, including narrow auth panels where the ordinary
16rem auto-fit grid would stack them. Mobile remains one column. Country and
State reuse this shared modifier in both tenant creation paths. UI version 0.1.12.

Decision 2026-10-21: `PageNavigation` centralizes back links and breadcrumbs above
page titles. Tenant directory uses `/platform` as its explicit back destination;
direct visits work without browser-history assumptions. `data.css` owns compact
header spacing, wrapping and theme/focus states. UI version 0.1.13.


### Reference catalog management (2026-10-21)

Settings Countries, States, Languages and Currencies reuse ActionCard, shared
PageNavigation (back before title and breadcrumbs), PageHeader, Card, FilterBar,
TableSearch, Select, IconButton/RefreshIcon, DataTable and Pager. No per-directory
CSS. DataTable declares code/status cell types and uses a value accessor for
country labels. Dedicated create/view/edit pages share ReferenceRecord policy
metadata and the central form grid/review definition-list styles. Notices show
validation, synchronization and version conflicts; ConfirmDialog collects the
archive/restore reason. Filtered safe return paths, stale-edit reload, pending
controls and before-unload/cancel dirty protection apply consistently.

### Company context switchers and the creation wizard (2026-10-21)

`ContextSwitcher` (§5.2) is the shared switcher popup; `OrgSwitcher` is its trigger and stays
usable alone. `WizardLayout` is the shared multi-step layout — masthead, `Stepper` rail, one
`Card` of fields and a pinned action bar — and it owns three things a hand-composed wizard
gets wrong: the `form` (so Enter submits the step), the heading focus on a step change (and
*only* on a change — focusing it on arrival steals focus and scrolls), and `noValidate`, so a
field left empty and a field the server rejected read the same way through the caller's own
messages. `FieldGrid` and `ReviewList` expose the existing `.janso-setup__fields` and
`.janso-setup__review` grids so no app repeats those class names. `apps/auth`'s first-run
`/setup` page predates this and still composes them by hand; it should migrate rather than a
second copy of the layout growing beside it.

`Stepper` gained `reached` and per-step objects. `reached` defaults to `current`, so the
forward-only wizard is unchanged; passing it explicitly lets the user jump back and return.
A step may now report `complete: false` with a `note` — a visited step with something still
missing, which a label alone cannot express and which otherwise either traps the user or lets
them reach the end believing everything behind them was done. The marker carries it as a glyph
as well as a tone (§2.4).

`Checkbox` gained a `hint`, rendered **outside** the `<label>` and attached with
`aria-describedby`: inside it, a forty-word consequence becomes part of the control's
accessible name. `TextField` forwards its ref so a field inside a popup can take focus on
open. `businessToday(timezone)` joins the formatters: which financial year is current and what
date a form opens on are decisions, and a server in UTC must not answer them for a company in
`Asia/Kolkata`. It never decides a `posting_date` (CLAUDE.md invariant 4).

Console-local: the rail's own `ContextPicker` composition, the company directory and the
creation wizard's steps are app policy and stay in `apps/console`, with only two app classes
(`.console-context__*`, `.console-wizard__*`) for the switcher's rail-level failure line and
the creation run's task list.

Decision amendment (2026-10-21): `asErrorStatus(status)` joins `ErrorStatus` in `States`. Four
list screens were each inlining `[401,403,422].includes(x) ? x : 500`, and a screen that spelled
it differently would read a permission refusal as an outage. The three pre-existing copies in
the platform and reference directories still inline it and should adopt the helper.

Known duplication, recorded rather than left implicit: `Menu`, `UserMenu`, `SearchSelect`,
`CommandPalette` and `ContextSwitcher` each carry their own copy of the portalled
roving-index/outside-dismissal/Tab-restores-focus contract. `lib/placement` already shares the
geometry; the keyboard half should follow it into a `lib/popup` hook, and that extraction is
worth making before a sixth popup is written.

Platform review delivery (2026-10-22): account and tenant details reuse PageNavigation,
PageHeader, Card and ReviewList with configured date formatting. Shared UserMenu
supports a non-focusable separator before Sign out. Checkbox labels establish their
own positioning context so the hidden native input stays with the visible control
during scrolling and keyboard interaction; no per-page checkbox styles are needed.

Decision amendment (2026-10-23): Auth onboarding uses a dedicated workspace transition
with a rotating workspace symbol, an accessible live status and two actual stages:
checking access and opening the workspace. Setup copy and invitation guidance appear
only after the access check resolves to an actionable state. Existing and newly created
workspaces both show the opening state until navigation completes. No timed percentages
are shown. Presentation is centralized in `registration.css`, uses theme tokens and the
existing spinner, and follows the shared reduced-motion rule. Onboarding, login and shell
regression tests and the auth TypeScript check pass. Manual simplification and security
review also included browser screenshots at desktop/mobile sizes in all three themes,
reduced-motion verification and checking for browser page errors. Automated transition
state coverage uses mocked navigation in the onboarding tests. Manual
reviews found no issues; `/simplify` and `/security-review` commands are unavailable in
this environment. Session checks, workspace creation and return-URL restrictions remain
covered by the existing tests.

Decision amendment (2026-10-23): stacked DataTable cells use content-driven height.
The desktop row height clipped multiline commercial descriptions on mobile, allowing
them to overlap the next cell. Pricing uses the shared FilterBar, DataTable, Drawer,
forms, confirmation and currency formatters. Browser checks cover mobile content bounds
as well as horizontal overflow in all three themes. `@janso/ui` is now 0.1.16.

### Platform editor consistency (2026-10-23)

Back navigation and create/edit chrome are now one shape at every depth under platform
administration. Three things changed, and the reasoning is worth keeping.

`PageNavigation` is the only back affordance. The tenant and platform-details editors had
each rendered a bare `.janso-link` instead, so walking Platform administration → Tenants →
a tenant → Edit lost both the chevron and the whole breadcrumb trail on the last step. A
back link that changes shape as the reader goes deeper reads as a different kind of page,
not a deeper one. Because those bare links carried the discard confirmation, `onNavigate`
was added to `PageNavigation` and applied to the crumbs as well — guarding only the back
link would have let a breadcrumb drop a draft silently.

`FormLayout` and `FormActions` own the editor shape. Four pages had copied the split
form/aside grid and the footer by hand and had drifted: `ReferenceRecord` was full width
with no context card, and `AccountDetail` put its actions in a `.janso-setup__actions` div
inside the card body with the submit button *before* Cancel. Cancel is now always the
left-hand link and the committing action is always right-aligned in the footer.

`FieldGrid` takes `disabled` and renders a `<fieldset>`. That is what let the platform pages
stop writing `.janso-setup__fields` by hand, which is a setup-wizard class and had no
business naming the layout of an account review.

Reference catalogs moved from `/settings/[catalog]` to `/platform/references/[catalog]`.
They always rendered with `activeHref="/platform"` and always claimed Platform
administration as their breadcrumb parent, while `/settings` itself is company settings —
the trail and the URL disagreed. The old path also placed a dynamic segment beside the real
`/settings` children (`readiness`, `notifications`), where any future static page would have
shadowed a catalog name.

Deferred: the notification editors remain modals rather than routed pages. Their chrome now
matches the routed forms — grouped disable, Cancel before Save, the same wording and action
class — but giving them real URLs needs roughly fifteen new routes and a rewrite of
`notification-navigation`'s route validation, which is its own change.

Tests: `form-layout.test.tsx` is new; `page-navigation.test.tsx` and `wizard-layout.test.tsx`
gained cases for `onNavigate` and the `disabled` fieldset; the tenant, platform-details,
reference and account-review suites assert the trail, the discard guard and the footer order.
The console suite times out under full file parallelism on the development machine — run it
with `--no-file-parallelism --testTimeout=20000` for a trustworthy result.

### Dark-mode structural visibility (2026-10-23)

The console's landing and administration pages read as one undivided surface in dark mode.
Measured rather than argued, with the repository's own WCAG function: `--janso-line` was
`#25272e`, which is **1.23:1** on a card — *lower* than light's equivalent hairline, while
light additionally gets a shadow that renders. `--janso-shadow-card` on near-black measures
**1.03:1** against the page, and a card's fill is **1.06:1**. All three separation cues were
below the threshold at which most readers see an edge, so cards, stat tiles, table shells and
the rail had no boundary.

Worse on the administration pages specifically, because they are grids of `ActionCard`:
`--janso-grad-panel` ran `#14151a → #0e0f12` on a `#0c0d10` page, *descending toward* the page
rather than away from it, so each card faded to **1.01:1** at its lower edge — exactly where
its call to action sits. In light the same gradient descends away from white paper, which is
why the direction had never been questioned.

Three changes, dark only. Light and ledger are cream/white palettes where the shadow works, and
nothing there moved.

1. `--janso-line` → `#43474f`: 1.97:1 on `surface`, 2.09:1 on `paper`, **1.87:1 on
   `surface-2`** — the rail and nested tiles, which is the binding surface and the reason the
   value is not a notch lower. Not 3:1, because this token is also every table row divider and
   fifty consecutive rows ruled at 3:1 read as a wireframe. The tiers stay ordered: 1.97 →
   `line-strong` 3.01 → `control-line` 3.39.
2. `.janso-action-card` and `.janso-page-navigation__back` now draw with
   `--janso-control-line`. Both are links drawn as outline controls, so WCAG 1.4.11 owes their
   boundary 3:1 in every palette; both had been reaching for the decorative rule. The pairing
   table already proves `--janso-control-line` ≥ 3:1 on a card and on the page in all three
   themes, so this connects an existing proof to the edges that needed it.
3. `--janso-grad-panel` → `#1b1d23 → #15171c`: 1.15:1 → 1.08:1 against the page, lifting
   throughout instead of sinking.

Why it shipped: `contrast.test.ts` already carried a **dark-only** popover-edge rule with
exactly the right reasoning — "on near-black the shadow renders as nothing, so the edge is the
only thing separating a menu or dialog from the page" — and that argument was never carried
across to the things that are not popovers. `--janso-line` and `--janso-line-strong` appeared
in **no** pairing in the table, despite 49 consumers across eleven stylesheets. The one token
holding up the console's structure was the one token nothing measured. Three tests now cover
it: the 1.8 floor on all three dark surfaces, the gradient's direction against `paper`, and a
CSS-text assertion that those two interactive edges name `--janso-control-line`. The first of
them is what caught `#3d4149` landing at 1.70:1 on the rail during this change.

Not done here, and deliberately: an inset top highlight to replace the unusable dark card
shadow, and lifting `--janso-surface` clear of `--janso-paper` (1.06:1). Both compound with the
above rather than substituting for it; neither is needed for the structure to read.

### Menu navigation destinations (2026-10-23)

`MenuItem.href` renders a safe ordinary anchor for navigation, preserving native new-tab
and keyboard behavior. Existing commands and checkboxes remain buttons. Unsafe URLs
are excluded; disabled destinations omit the href while retaining their readable reason.
Company directory/chooser and financial-year menus use this shared implementation.
Shared UI version: 0.1.17. Menu regressions and the full shared UI suite pass.

### Dark-mode elevation, and why the surface was not lifted (2026-10-23)

The follow-on to the entry above. Two items were outstanding: give the dark card the elevation
cue its drop shadow cannot provide, and lift `--janso-surface` clear of `--janso-paper`. The
first is done. The second should not be, and the measurements are the reason.

**`--janso-shadow-card` in `dark` gains `inset 0 1px 0 rgba(255, 255, 255, 0.08)`**, keeping the
cast layer for the few surfaces that sit on something lighter. The lit edge measures 1.23:1
against `--janso-surface` and 1.26:1 on the `ActionCard` gradient — a second edge at the top,
inside the 1.97:1 border, where a light source would catch it. The idiom is already this
palette's own: `--janso-shadow-action` and `--janso-shadow-inset-mark` both light their top
edge rather than casting a shadow that would not render.

The alpha is 0.08 rather than the 0.10–0.12 that would read more strongly, because
`.janso-btn--primary:active` swaps `--janso-shadow-action` for `--janso-shadow-card`. At 0.12
the two tokens are identical and a pressed button stops looking pressed; 0.08 keeps the press
reading while the card still gains its edge. A test asserts the ordering in every palette that
lights both, so raising the card's elevation can never again quietly cost the button a cue.

**Lifting `--janso-surface` was abandoned on two independent grounds.**

It is nearly immovable: `--janso-line-strong` sits at 3.013:1 against it, which is **0.01** of
slack against the 3:1 gate. Any lift of the surface puts that token under the gate, and
`--janso-control-line` (0.39) and `--janso-chart-8` (0.20) are not far behind. The cascade turns
out to be just one token — `--janso-line-strong` re-tinted — rather than the chart re-validation
first feared, so the cost is real but modest.

The benefit, though, is nothing. Card-versus-page fill separation is **1.06:1** today; lifting
the surface to its ceiling buys **1.09:1**, darkening the page instead buys **1.08:1**, and
doing both buys **1.12:1**. For scale, light mode's own card sits at **1.07:1** against its
page and nobody has ever found a card hard to see in light mode — because fill is not what
separates a surface in this system. The border and the elevation cue are. So the premise of the
item was wrong: the fix for an invisible dark card is a visible line (done, 1.23 → 1.97:1) and a
working elevation cue (done, the inset edge), not a fill difference no eye can resolve.

Recorded here rather than silently dropped, because "lift the dark surface" is the obvious
suggestion and the next person to look at this will have it again.

Decision amendment (2026-10-25): `SplitButton` joins a primary link or command to the existing
portalled `Menu`. Both halves preserve permission filtering, safe links, disabled reasons
and pending protection. `Menu.onNavigate` lets a page protect drafts without replacing links
with commands. Intrinsic menus measure their mounted width and clamp both viewport edges;
their CSS also bounds width for narrow screens. Product detail uses the control for native
supplementary workflows and section-aware return navigation.

### Notification console look and feel (2026-10-27)

The thirteen areas of `/platform/notifications` and `/settings/notifications` were built with
the design system's primitives but almost none of its *patterns*: each screen was a `Card`
whose body held a run of bare `<p>`, `<dl>`, `<details>` and `<pre>` elements with no vertical
rhythm, lists paged through two blue links, filters submitted from an unframed field grid, and
every record's verbs sat in one undifferentiated row with no primary among them. Nothing was
broken; it simply did not look like the rest of the console. This pass closes that gap without
changing a single request, permission check or route.

**The area strip.** Thirteen `janso-link`s in a `janso-toolbar` became the tab strip, as
routed links (decision 83). The open area is now marked, and the row reads as one edge.

**One card header, used.** `Surface` (the notifications' own card wrapper) now takes `icon`,
`badge` and `footer`, and wraps its body in `janso-flow`. Status badges moved from mid-sentence
in a paragraph to the header; a card's standing caveat moved to the footer; everything in a
body now has the shared block rhythm instead of touching its neighbour.

**Facts, not paragraphs.** Record details use `ReviewList` through a `Facts` helper — the same
label/value list `CatalogMasterDetail` uses — so a provider, a route, a delivery and a receipt
all read the same way. `References` became a `Disclosure` over the `janso-preview` key/value
grid, and message content a `janso-preview__text` panel (decision 84) instead of an unwrapped
`<pre>` that scrolled the card sideways.

**Lists.** `NotificationTable` hands `loading` to `DataTable` rather than replacing the region
with a skeleton, so the columns stay put while a page is in flight; it states what each empty
list is *for*; and cursor paging is drawn as `janso-pager` with the range and both steps.
`ListFilters` renders inside `FilterBar` and shows a chip for every predicate in force —
including one that arrived in the URL, which is how a reader finds out why a row is missing.
The chips are `fixed`: this console navigates by link, so a chip's remove button would have
nowhere to report, and the form and "Clear filters" are the way to lift one.

**Four tones for state, not two.** `StateBadge` was success/danger/neutral, so `sending` — an
unresolved provider outcome, the one state this console exists to chase — rendered in the same
grey as `cancelled`. In-flight states are now `info` and withheld ones (`unmatched`,
`suppressed`, `expired`) `warn`.

**Verbs.** Each record has one primary action and the rest ghost; a destructive toggle is
`danger`. Delivery lineage links moved out of the verb row into their own `nav`, because a
reader following lineage is not the reader about to re-send a message. The recovery screen
leads with its warning.

**Landing page.** Twelve cards all carrying the same bell, each described as "Manage X for the
platform", became four `SectionHeader` groups in the order the work is done — transport,
content, policy, operations — with one glyph and one real sentence per area, those sentences
living in `notification-navigation`'s section table so the nav and the cards cannot disagree.
Channel readiness is a `ListRow` per channel rather than a paragraph per channel.

A review pass found five defects in the first cut of this change, all fixed and all now covered:
the cursor pager stated "No deliveries" over a table of loading skeletons whenever a page was
opened at a cursor; the back chip's label was read off the top-level area while its href pointed
at an intermediate record, so a content version offered "Back to templates" beside a link to its
variant; `Feedback` for the WhatsApp approval sync had moved into the card above the button that
drives it; the filter chips were derived from the declared form fields, so the one predicate no
form offers — `recipient_endpoint_id`, arriving from a delivery — produced no chip, which is the
exact silence the chips exist to prevent; and wrapping `FilterBar` in its GET form stopped
`data.css`'s bar-to-table spacing rule from matching, so the selector list now also covers
`form:has(> .janso-filter-bar)`.

Tests: `notification-chrome.test.tsx` is new (area strip, grouped cards, pager range and its
loading case, filter chips including the URL-only predicate, empty and error states, collapsed
references, and the back label on every nested route); the recipient suite gained the two
empty-search states, the operations suite the in-flight tone and the local attempt pager, and
the template suite the source panel and the approval-sync feedback placement. `content-layout`
and `density` in `@janso/ui` pin the two new CSS contracts. Three existing assertions changed:
a receipt's signature now reads "Verified against the registered provider secret" rather than
"Signature verified" (wording, not behaviour), and `density`'s bar-to-table regex matched the
selector pair as an exact adjacent pair, which the added `form:has(…)` selectors break.
Everything else in the console's 206 files and `@janso/ui`'s 69 passed untouched.


### Company Masters hub and tablet header sizing (2026-10-27)

Decision: the company Masters hub reuses ActionCard grids, SectionHeader and
FilterBar without a new app stylesheet. TableSearch belongs inside FilterBar;
its horizontal flex basis otherwise becomes unwanted vertical space when it is
a direct child of the page flex column.

The topbar right cluster and account-menu wrapper use min-width: 0 so names and
chips can shrink at intermediate tablet widths. This fixes a measured 2 px
overflow at 1024 px without clipping the account popover or adding a scrollbar.
Header/shell/content tests and the Masters desktop/mobile/theme browser checks
passed; see docs/company-masters-hub.md for verification and applicability rules.

### Company edit layout (2026-10-27)

Edit company follows the existing routed editor shape: FormLayout, one form card,
context card and FormActions footer. SectionHeader and the shared responsive form
grid provide consistent headings, field alignment and mobile stacking. Document
text spans the grid width and retains metadata limits and accessible hint/error
associations. Company identity in the narrow context card uses ListRow; ReviewList's
fixed label column is intended for wider review content. The read-only company
details share the section hierarchy. No new CSS was needed. Verification is recorded
in [company-edit-layout-review.md](company-edit-layout-review.md).

### Edit form alignment (2026-10-27)

Routed editors use FormLayout with contextual guidance and one form card containing
named sections and an attached FormActions footer. Inline editors use the same
card and footer primitives; FormActions supports a disabled non-submit Cancel
button for closing in place. Shared field grids and FieldGroup provide responsive
spacing without browser-default fieldset borders or nested manager padding.
Form-action footer groups wrap inside their card on narrow screens. Accounting,
product configuration, custom fields, product attributes and tenant-administrator
editors now follow this pattern. Verification and the decision record are in
[editor-layout-alignment.md](editor-layout-alignment.md).

### Business overview access and preview clarity (2026-10-27)

Decision: the missing-report-access overview state keeps PageHeader and the open
company name, explaining the required company report access and the available
menu without implying no workspace is selected. The current demonstration
dashboard explicitly labels its sample figures until live Reports integration
replaces that loader. Tenant3 fresh-login and new-company evidence is recorded in
[company-owner-access.md](company-owner-access.md#fresh-tenant3-company-verification-2026-10-27).

### The bar's leading verb — `Menu` with a primary trigger (2026-10-27)

Decision: the console top bar gains one primary action, "New", beside the
command trigger. It is a `Menu` with `triggerVariant="primary"`, not a
`SplitButton`, and that is the decision rather than an implementation detail.

`SplitButton` exists for a **default action plus its variants** — its two halves
do different things, so they need separate focus targets and separate names. "New"
is not that shape: every entry in it starts the same kind of work, and there is no
one voucher kind the console may assume. A face that navigated somewhere the caret
did not would be two actions wearing one name. So the control stays one button with
one job, and the split is presentation: the action gradient both halves of a split
button would carry, with a hairline (`--janso-brand-bright`, a step off the gradient
in all three themes) ruling the caret off from the label. No new colour is named and
no second keyboard or portal implementation is introduced.

`MenuItem.separatorBefore` arrives with it, matching the flag `UserMenu` items have
had: a list of five verbs no one scans is the thing the control exists to avoid. The
rule is ignored on the first *surviving* item — so an item filtered out by permission
cannot leave a rule hanging off the panel's top edge — and never doubles the rule that
already divides off destructive verbs.

Decision amendment (2026-11-01, user-requested access review): the New control
requires an open company and current `vouchers.read` plus `vouchers.create`
grants in that company. This supersedes the 2026-10-27 ungated-navigation
exception. Administrator classification alone does not reveal the action;
company creators may also hold Stock Operator, and their combined grants apply.
Readers retain voucher menus and list cards, while New links and entry pages
require creation authority. Saved Purchase bills remain readable by reviewers,
with each operation checked separately. APIs independently enforce live grants,
object scope, field policy and capability gates.

Destinations are `/vouchers/new/<kind>` for sales, receipt, purchase, payment and
stock adjustment. These pages now use native entry workflows. Their ids and
hrefs are equal so the pointer and keyboard paths navigate to the same place.
See [voucher-access-review.md](voucher-access-review.md) for the permission matrix.

**The second control in the top bar exposed a latent overflow, now fixed.**
`.janso-topbar__mid` was `flex: 1` — a `0%` basis. Shrinking is apportioned by
`flex-shrink × flex-basis`, so a zero basis gave that slot a scaled shrink factor
of **zero** and pushed every pixel of shrinking onto the right-hand cluster, whose
chips are `white-space: nowrap` and cannot shrink either. The cluster then
overflowed a band that deliberately cannot scroll, so the theme switcher and the
avatar left the page — the very bug the bar's own comment claims to have fixed.
It was latent while the slot held one search box with slack either side; a second
control widened its content and brought the overflow into ordinary laptop widths.

The bar's documented strategy was *shed content at breakpoints*, and what was
missing is that it also has to **shrink between them**. Four rules, all now
asserted against the stylesheet (jsdom computes no layout, which is why the
original shipped past a green suite):

- `.janso-topbar__mid` takes `flex: 1 1 auto`, so both sides give in proportion to
  what they hold.
- `.janso-topbar__right` states `flex: 0 1 auto` rather than inheriting it, since
  being able to give way is the whole point; `margin-inline-start: auto` stays, for
  when there is no middle slot to push it.
- Inside the middle slot the **search yields and the primary action holds**
  (`min-width: 7rem` on the trigger, `flex: none` on the menu): a squeezed search
  ellipsizes its placeholder and still reads as a search box, while a squeezed
  "New" clips a gradient pill mid-word and reads as a rendering fault.
- `.janso-chip__label` gains `min-width: 0`, which is what makes the ellipsis it
  already had actually fire — a flex item's automatic minimum size is its
  min-content width, so a long one-token company name had been overflowing the
  chip's own border. Chips get a `4.5rem` floor so they shrink instead of shoving.

The Ctrl+K keycap now hides at the existing 960px step rather than at a breakpoint
invented for it: it hints a shortcut that keeps working, so it is the cheapest
~3rem in the bar, and spending it there keeps the search legible beside "New".

Shared UI version: 0.1.23. The `@janso/ui` suite (2071) and the console
new-voucher suite pass; `triggerVariant` defaults to `ghost`, so no existing
`Menu` caller moved.


### Local font loading correction (2026-10-27)

Decision: tokens.css no longer imports the Google Fonts stylesheet. Both apps already
load the self-hosted Inter font through fonts.css before tokens; the redundant remote
import could delay hydration on installations without reliable external font access.
The token regression rejects external stylesheet imports. Existing font assets, type
families and visual tokens remain in use. Verification is recorded in the account and
party experience review; this belongs to the pending shared UI 0.1.22 delivery.

### Compact master and report cards (2026-10-27)

Decision: Masters and Reports opt into the shared compact grid, with fixed equal
card heights, smaller padding and icons, and columns retained for short sections.
Report search has a visible label on the overview and every category page; matching,
clearing and unavailable report actions retain their existing behavior. This is part
of the pending shared UI 0.1.23 delivery. Verification: 98 focused UI tests, console
typecheck, and live tenant3 checks across six routes, four widths and three themes.

### Freely navigable product setup (2026-10-27)

Decision: Stepper supports optional allowFuture navigation without changing the
default linear wizard behavior. Progress can still distinguish upcoming, incomplete
and completed steps. Product creation uses this mode in its existing FormLayout and
Card layout. Checkbox decoration ignores pointer events so the real input receives
pointer interaction. This belongs to shared UI 0.1.24; no new visual tokens or app CSS
were needed. See product-creation-wizard.md for workflow and verification evidence.

### Contextual row-menu reads (2026-10-27)

Decision: Menu has an optional onOpen callback for loading current contextual
actions when opened by pointer or keyboard. Existing synchronous menus keep their
behavior. Product directory menus use it to resolve effective inventory settings
only for the selected row, keeping configuration out of lean list projections.
Their custom action cell retains the shared hidden heading and end alignment.
This belongs to shared UI 0.1.25; no new CSS, tokens or dependency is needed.
Live keyboard review also exposed a focused row outside the visible scroll area
producing a negative panel offset. Shared placement now clamps its vertical anchor
to viewport edges and caps height to available room. The failing regression was
verified before the fix; menus and the other select/switcher consumers pass their
affected suites. Normal pointer/keyboard focus and Escape restoration are retained.

### Disabled secondary actions (2026-10-27)

Decision: the disabled, non-busy ghost Button uses the existing disabled surface
and ink tokens, a muted border, no shadow and a disabled cursor. Busy secondary
buttons retain their progress appearance. The future merge buttons exposed the
missing visual state; a failing token-contract regression was confirmed before
the fix. This belongs to shared UI 0.1.26. Workspace-linked consumer resolutions
remain unchanged; no app CSS, new tokens or dependency is introduced.

### Stacked saved-record summaries (2026-10-27)

Decision: ReviewList supports an optional stacked presentation for narrow panels.
Labels sit above values regardless of viewport width, so long product/party names
can use the full sidebar width. The default review layout and edit links retain
their behavior. Product and party edit contexts use this shared variant; the
styles remain in setup.css and use existing spacing tokens. This belongs to
shared UI 0.1.27; workspace-linked consumer lockfile resolutions are unchanged.
Verification: wizard/review, primitive and token tests plus live desktop/mobile
measurements recorded in product-party-edit-review.md.

### Review dialogs and card search (2026-10-30)

Decision: `ConfirmDialog` takes `size: md|lg` (the two widths `Modal` already offers), and its
panel no longer scrolls as a whole. The body is the one scroll region; the title and the
Cancel/Confirm row stay on screen however long the review is. The body is spaced as a column
(`.janso-dialog__body > * + *`, with paragraphs keeping their tighter rhythm), so a fact list, a
sentence, a field and a notice no longer sit flush together. The Product configuration publication
review — a comparison per product kind plus every section's effective values — was a page's worth
of cards in the 30rem panel, with the cards touching and the confirming action at the end of one
long scroll; it now uses `lg`, and each comparison is a `.janso-flow` column. A bare `TableSearch`
placed straight inside a `Card` sat hard against the card border while the heading above it was
indented; Company configuration (Features) and Financial years now seat it in `FilterBar`, which the
card stylesheet already gives the card gutters. No new tokens, colours or dependencies. Verified by
rendering the real pages and dialogs in a browser at desktop and phone widths before and after;
failing structural regressions were confirmed before the fix. Shared UI version: 0.1.38.

### Card status chips and voucher print (2026-10-30)

Decision: `ActionCard` takes an optional `status: { label, tone? }`, drawn as a `Badge` in the card's
top row, where `disabledReason` already sits (which still wins). It is informative, not a gate — the
Console's Voucher print page uses it for "Standard layout" / "Custom layout" on a card for each voucher kind.
The chip stays out of the link's accessible name, so the link is called the same thing in every
state, and is carried in its `aria-describedby` with the description; every `ActionCard` link now
exposes its description that way. The page itself reuses `ActionCard` grids, `SectionHeader`,
`DataTable` with a `link` column, `Card`/`FormActions` and the routing page's
`.console-routing-fields` — no new app stylesheet, token or dependency. Verified by rendering the
real pages inside the console shell at desktop and 390px; tests cover the chip, its tone, its
description and its precedence. Shared UI version: 0.1.39.

Second pass, same day: a voucher's own page now opens on the answer — a `Card` with a `CardHeader`
(layout name, `Badge` for Built in / Custom layout / Draft in progress / Organisation layout) and the
action in its `FormActions` — with the rules table and the picker of existing templates inside a
`Disclosure` ("Advanced: other templates and rules"), and *Back to standard layout* asked through
`ConfirmDialog`. All existing components and classes; nothing added to `@janso/ui`.

### Aligned controls and compact designer (2026-10-30)

Shared UI version 0.1.40 adds `--janso-control-h: 2.25rem`; filter height aliases it.
Text/native date/select/single lookup outer controls share that height. Lookup
inner padding and line-height preserve alignment; multiple selected chips retain
automatic growth. Hint/error rows remain outside the control. Form fieldgroups
and action groups use shared existing classes. Report history buttons wrap long
native identities within their container.

Below 68.75rem, the designer uses a wrapping toolbar and a full-width document
stage, with one explicit palette/properties panel open at a time. Desktop rails
retain their existing layout. Panel triggers expose expanded/control relationships;
Escape/dismiss returns focus. Geometry and focus were checked at 1440/768/390px.
Workspace consumers resolve the local UI package through existing workspace links;
no dependency or lockfile resolution changed.

### Document entry workspace (2026-10-31)

The Purchase preview uses `janso-entry-workspace` in the shared `entry.css`. The
workspace groups supplier/invoice fields, a mode-aware `EntryGrid`, a provisional
summary and sticky actions. Below 72rem of content, the summary moves under the
lines. Below 42rem, fields stack, a horizontal-scroll hint appears, and primary
actions use two columns with 44px minimum targets. Grid labels are positioned
relative to their own scroller so hidden labels cannot widen the document.

The shared non-colour tokens `--janso-entry-subject-w` (18rem),
`--janso-entry-quantity-w` (6rem), `--janso-entry-amount-w` (7rem) and
`--janso-entry-kind-w` (7rem) size the workspace's columns. They apply only inside
this opt-in workspace; existing Sales styles retain their behavior. All colours,
type, spacing, surfaces and focus treatments use existing theme tokens.

Purchase policy, synthetic masters, validation and preview arithmetic stay in the
console. The workspace's fixture currency remains explicit while company display
preferences control formatting. No tax resolver, upload, persistence, posting or
printing capability is implied by these shared styles. See
[Purchase UI delivery](purchase-ui-todo.md) and its browser evidence.

### Auth screens: the ledger sheet (2026-10-31)

The split shell shared by `/login`, `/signin`, `/signup`, `/recover` and `/reset` kept its layout
(brand panel left, form card right) and its tokens; what changed is how finished it looks. The work is
in `apps/auth` only — `auth.css`, `BrandPanel.tsx` and two classes on the sign-in and login footers —
and uses no colour of its own, so all three palettes follow (a test fails on any literal colour).

- **The panel is a sheet of account-book paper.** A double margin rule in the palette's brand line sits
  down the left, faint ruled lines run behind the heading (mixed from `--janso-line`; less of them in
  the dark palette, whose rules are bright), and the logomark's own two strokes — the rising rule over
  the flat base, the "books balance" — are drawn as hairline outlines beside the heading, once, on load.
  All of it is `aria-hidden` and inert; the drawing is dropped below 1180px, where it would sit behind
  the heading, and drawn already under `prefers-reduced-motion`.
- **The tagline stays at `--janso-text-2xl` (32px).** A first pass set it at up to 52px; the screen
  is for signing in, and a statement that size out-shouts the form. A test pins the token. The rows
  under it follow the window's height (`clamp(3rem, 12vh, 7rem)`), not the panel's, because the panel
  grows with the sign-up form beside it.
- **The feature rows are ruled rows**, with a brand-tint tile for the glyph, instead of floating tiles.
- **The form card** is 26.5rem with 2.5rem padding; its controls are 2.75rem and its button 2.875rem
  (the console keeps its dense 2.25rem — the change is scoped to `.auth__form`). The way off the
  sign-in path (create account, forgot password, set up the platform) is the card's own footer band,
  a quieter surface running to the card's edges from one `--auth-pad`; on a phone the card and the band
  dissolve into the page.
- **On a phone** the palette switcher shares the header row with the wordmark, and the grid is
  `auto 1fr auto` so the header stays compact and the legal strip stays at the foot.

Checked in Chrome at 1440, 1000 and 390px in Light, Dark and Ledger, with real Inter. Shared UI package
unchanged.

### Purchase detail panels (2026-10-31, P3)

Centralized `entry.css` adds opt-in `janso-entry-detail-*` cards, field groups,
two-column pairs with a narrow-container fallback, calculation summaries and
bounded raster previews. They reuse existing theme/spacing/type tokens and shared
Drawer, Modal, numeric inputs, CustomFields and FileUpload; no app stylesheet or
new dependency is introduced. Panel header/footer remain pinned while content
scrolls, including on mobile. Apply commits panel changes; dirty close offers
Keep editing / Discard panel changes and returns focus to its trigger.

`FileUploadStatus` adds `selected`, rendered as **Selected locally**, for files
held only by the current page. Existing `done` still means Uploaded; no upload
is inferred from local selection. Purchase supplies extension/MIME/signature
checks and local image decoding/error guidance, then revokes preview object URLs.
PDFs are not embedded. Secure storage and server validation remain owner work.

See the [Purchase UI ledger](purchase-ui-todo.md) and
[P3 browser evidence](testing/purchase-ui/phase3/review.json). The comprehensive
accessibility/locale/scale gate remains P5; this phase does not certify it.

### Purchase workflow surfaces (2026-10-31, P4)

The opt-in `janso-entry-workflow-*` rules in `entry.css` provide a wrapping status
bar, collapsed example controls, responsive revision-comparison cards and readable
submission line summaries. They use existing tokens and shared Badge/Notice,
Button, Select, TextField and Modal. Workflow dialogs keep footer actions at least
44px tall on narrow viewports; the selector is restricted to these marked dialogs.
Pending review/correction uses the shared overlay's busy state so close, scrim and
Escape behavior agree with disabled actions. No global Sales/overlay behavior changes.

One controlled Purchase editor renders new, draft, rejected, submitted and approved
states; available actions follow existing company-scoped grants. The workflow and
memory adapter remain console policy, not a shared UI state machine or a financial
service contract. See [P4 evidence](testing/purchase-ui/phase4/review.json) and the
[Purchase delivery ledger](purchase-ui-todo.md) for checks and remaining P5 work.

### Purchase quality review and overlay access (2026-10-31, P5)

Shared UI 0.1.43 adds named focusable overlay body regions, allowing keyboard
scrolling of read-only Modal/Drawer content. The body is now a deliberate Tab stop
between the close button and footer; the focus-cycle test reflects this behavior.
SearchSelect's portalled search panel is a named region, including empty results.
Focus-visible styling remains token based. The affected overlay/search tests pass.

Opt-in centralized Purchase styles add labelled line cards, complete wrapped names,
staged line-editor composition, sticky invoice context, scroll margins and aligned
compact actions. Marked Purchase dialog actions meet 44px through 48rem viewports.
Responsive measurement reads a CSS container marker rather than duplicating the
breakpoint in application code. The draft reducer and numeric mechanism remain
shared with desktop entry. Existing workspace dependency links remain unchanged;
no application dependency is added. See the [readiness report](purchase-ui-readiness.md)
for actual evidence, incomplete audit review and production integration limits.

### The live Purchase page (2026-10-31)

`/vouchers/new/purchase` is one `janso-page` column — header, notices, the bill, the lifecycle — so it
has the page gutter, width cap and rhythm of §4.2–4.3. Its previous sections were siblings of the
workspace outside any page container, which is why they ran flush to the shell edge with no spacing.

- **No side rail.** The live workspace is a single column (`janso-entry-workspace__layout--single`).
  The action bar shows **Lines total** (what has been typed, when every line is complete) until
  Accounting has calculated, then **Bill total**. The synthetic previews keep their rail.
- **The header** is `PageHeader` with `meta` chips (status, type, "Amounts in INR") and the two
  actions that belong to the page: Saved drafts and, once a bill is saved, New purchase.
- **Fields** sit on a twelve-column grid (`janso-purchase-fields`) that collapses by the frame's
  width. A value that is read, not typed (payment due, say) uses
  `janso-purchase-static`, with the same label and height as a field.
- **An account bill's grid** has account, description and amount. Discount and net columns return
  only when the type allows discounts. Entry mode is hidden while only one mode is allowed, and an
  empty "Purchase details" card is not rendered.
- **Tax** is a required confirmation checkbox, not a one-option select; a refused save marks it
  invalid in words (`janso-purchase-confirm`).
- **Lifecycle** (`janso-purchase-track`): five steps, each with a mark and a word, the next one
  `aria-current="step"`; a stopped bill shows where it stopped. Status is never colour alone.
- All rules are in `entry.css` under "the live Purchase page", tokens only; a test fails on a literal
  colour, a missing token, or a class the components emit that the stylesheet does not define.

Shared UI 0.1.45 adds `PageHeader`'s optional `meta`. Rationale, section-by-section purposes and
evidence: [purchase-page-redesign.md](purchase-page-redesign.md).

### Day Book workspace (2026-11-01)

Shared UI 0.1.47 exports `day-book.css`. The Day Book is a direct report workspace with
compact, aligned quick filters, a separate advanced drawer, a four-figure summary strip,
sticky table headings and expandable complete journal details. At narrow widths its
filters become a labelled disclosure and voucher rows become readable stacked entries.
Accounting lines retain a keyboard-accessible horizontal table region.

All palettes resolve through existing theme tokens. Three structural tokens are added:
`--janso-report-viewport-height`, `--janso-report-table-min` and
`--janso-report-detail-min`. The report workspace uses one spacing mechanism; inherited
page/field stack margins are reset inside its grid to keep labels and controls aligned.
The advanced drawer uses an opaque theme surface for readable financial filters.

Operation-specific progress is announced outside the busy report region, with retained
results explicitly identified during updates. Export preparation leaves the report readable.
Long voucher numbers wrap inside mobile entries; desktop tables retain horizontal scrolling.
Native date controls follow the active theme for readable calendar icons and pickers.
Status and transaction-currency filters remain visible as removable chips when mobile
filters are collapsed. Condition editing moves focus to the new or adjacent value, and
returns to Add condition when the final condition is removed.

Decision: keep interactive Day Book styles in their own shared stylesheet. The existing
`report.css` remains the print renderer's stylesheet; server presentation assets are
regenerated when shared tokens change. Evidence and accounting semantics are recorded in
[day-book-delivery.md](day-book-delivery.md).

### Business overview (2026-11-01)

Shared UI 0.1.48 adds `GroupedBarChart` and the `.janso-overview*` rules in `data.css`. The page
is a calm, decision-first layout: header with the company and financial year; a toolbar holding the
period control and a freshness line; a four-tile KPI band with exactly one emphasised tile (cash
and bank); then cards. There are no tabs: a tab with nothing behind it is an empty promise
(decision 83), and every figure shown has a verified source.

Long explanations collapse into one "About these figures" disclosure. Only an unusual condition
(ledger history starting late) earns a visible chip. A refetch keeps the previous figures on screen,
announced as "Updating…" (never dimmed: that would drop their contrast), and every caption states the range of the data actually displayed, not of
the control. Empty and unavailable states are specific: nothing posted offers the next steps the
reader may take; no verified snapshot explains how to prepare one.

Business dates stay strings end to end; money is summed with exact integer arithmetic; the figure's
symbol comes from the display config only when its currency matches the source's. The plan, phases
and evidence are in [business-overview-redesign-plan.md](business-overview-redesign-plan.md).

### Create from the field — Purchase supplier and expense account (2026-11-01)

On the Purchase account bill, the **Supplier** field and each **expense / service account** row have a small
outline "+" icon that opens a right-hand drawer to create what is missing, so a bill is never abandoned
halfway to set up a master. The pattern, for the next lookup that needs it:

- **Icon, in the control's own row.** `IconButton` (`variant="outline"`, `PlusIcon`), `aria-haspopup="dialog"`,
  named for the act ("Create a new supplier", "Create a new expense account for line 2"). It sits *beside the
  box*, after it in reading order — not in the label row above it. A header lookup uses `InlineCreate`, which
  is the product masters' `console-reference-create` layout with a `--flush` modifier: that layout's row gap
  stacks on the label row's own margin, which would push the box lower than the plain fields beside it
  (measured on the live page: both boxes now start at the same pixel). In a grid row the icon sits beside the
  lookup's cell element, not inside it — the grid reads Enter inside a cell as "next row", which would swallow
  the button's Enter. It is hidden when the actor lacks the permission or the bill is read-only (presentation
  only; the service authorizes each command), and disabled, not removed, while the bill is busy.
- **Drawer.** `Drawer` `md`, a compact two-column form (`console-quick-create`), not the page's airy rhythm:
  fields pair up and a field that needs room spans both. A purpose line, only what the bill needs, the cursor
  in the first field. Supplier: name (it is also the legal name — the full form tells them apart), code
  (suggested from the name), country, and for an Indian supplier the GST status (regular, composition,
  unregistered, or add later), state and GSTIN, offered only to an actor who may record tax registrations.
  Expense account: name, code, group (only groups under an expense head), optional description. Service
  rejections are shown beside their fields; one with no field (the payable account, say) is listed in a notice.
  Closing with typed data asks first — by Escape, the close button or the scrim alike — and not at all while a
  request is in flight.
- **A way out to the whole form.** A "Full supplier form" / "Full account form" link at the foot opens the real
  master page in a **new tab**, so the bill and what is typed on it stay exactly as they are; the new record is
  found in the lookup afterwards, because the lookup reads the server.
- **One command, one key.** A supplier is created together with its payable account and GST registration, and
  an expense account is created already active, each in a single atomic request with one idempotency key: a
  half-created supplier cannot be billed, and an inactive account cannot be selected. A failure with no answer
  (network, 5xx) locks the form and offers **Retry**, which resends the *same* request and key, so it cannot
  create twice; cancelling then says the record may already exist.
- **Choosing the result.** The created record goes through the bill's own selection path, which re-reads and
  verifies it exactly as for a pick from the list; success is announced in the bill's polite status line, and
  focus moves to the next thing to fill (invoice number; the row's amount). A staged line editor (compact
  screens) receives the account only after it has been verified, and the bill is not touched until that line
  is applied.
- **What it does not do.** Addresses and contacts stay with the full supplier form; account kinds other than a
  general, postable, non-stock expense account stay in Masters.

Decision: there is no `action` slot on `SearchSelect` for this. It was built first (the icon in the label row,
as `TextField` and `Select` allow) and removed when the icon belonged beside the box; `onCreate` (§5.5) creates
from typed text with no form, which these creations — a form, a permission, a verification step — are not.

### GST on the Purchase account bill (2026-11-02)

On `/vouchers/new/purchase`, "This bill carries no tax" stays the statement a person makes. Where GST can be recorded
the box starts unticked and a **GST section** opens under it; ticking the box closes it, unticking brings it back with
what was chosen. The pattern, for the next document that has tax facts of its own:

- **Facts of the bill in a field grid, results beside the lines.** How the tax is charged, the company's registration, the
  place of supply, the service completion date and the supplier's registration are fields of the bill
  (`janso-purchase-tax__fields`, a wrapping grid that never needs a breakpoint); what each expense account says about its
  tax is a ruled list beneath (`janso-purchase-tax__lines`). No rate or amount is ever typed or shown as an input.
- **Automatic is blank.** A value the masters can supply (primary registration, its state, the invoice date, a supplier's
  only regular registration) is shown with a hint that it follows the masters, and is stored in the draft only once the
  person chooses one. A value shown is therefore always the current one.
- **A fact that cannot be supplied is a notice with its way out,** not a disabled field: no supplier registration, or a
  supplier that is composition or unregistered, says so in a warning notice with "record the bill without tax" as the
  other road and a link to the master in a new tab (`target="_blank" rel="noopener noreferrer"`, with the visually
  hidden "(opens in a new tab)"), and a button that reads the masters again after the person fixed one.
- **Refusals wait for the save.** Field errors appear only after a save was refused, and focus goes to the first field that
  needs attention; the notice for a missing supplier registration is always visible because it is a fact, not an error.
- **Gated three ways, and says which.** Without `accounting.tax.read` nothing is read; a voucher type that allows no
  service lines, or a company with no registration in force on the invoice date, leaves only the box, and its hint says
  why. A saved taxed bill opened without tax access shows what it carries and is not re-saved.
- **The calculation shows the tax as Accounting worked it out:** a figure per component (CGST, SGST, UTGST, IGST, Cess),
  reverse-charge tax marked as the company's own to pay and kept out of the supplier payable, and a table with one row
  per line (`janso-purchase-tax-table`: logical edges, tabular figures, the first column a row header).

### Simple product form review (2026-11-04)

The Simple creation page uses `.janso-page.janso-simple-product` to keep the
`--janso-form-max` width after the shared page styles load. Name/code use the
existing responsive `FieldPair`; mobile keeps one field per row. Error summaries
use `Notice`, field messages stay attached to their inputs, and focus moves to
the first editable invalid control or the summary. Completion has a named,
programmatically focused region. No new colour or spacing tokens were introduced.
Shared UI version is 0.1.62; workspace consumers continue to use linked UI source.
See [the UI review](simple-product-ui-review.md) for behaviour and verification.

### Account opening steps (2026-11-04)

The opening worksheet uses three shared Stepper stages: choose the account category
or group, edit openings in an alphabetical server-paged table, and review source
settings and posting. Company context is a compact wrapping row. Account choices use
labelled native radios; row controls retain accessible labels while the table header
provides the visible labels. The shared Toggle exposes automatic mode as a switch.
The layout uses `financial-opening.css`, imported by `janso-ui.css`, and existing
spacing, colour, focus and typography tokens. Shared UI version is 0.1.64.

Decision: preserve typed edits across account filters/pages, enforce row validation
before the review stage, and display configured offset/source values read-only in
automatic mode. A mode change has no financial effect. Desktop (1440px) and mobile
(390px) checks cover all three themes, with no page overflow or runtime errors.

### Opening workflow visual review (2026-11-04)

Shared UI 0.1.66 refines the scoped opening styles: selected category cards use the
brand tint, the three-stage stepper stays aligned on phones, and account controls
stack at full available width so amounts and dates remain visible. Search gets its
own row on narrow screens. Balance and completion summaries use compact metric
tiles; the finalized accent is shown only for a finalized opening. All treatments
use existing theme tokens and remain scoped to the opening workflow.

Decision: automatic source fields remain available in a labelled disclosure, while
historical reporting and review checks stay visible. Manual mode expands source
fields. Step changes focus the new heading, forward navigation is the primary
action, and inapplicable previous/next buttons are omitted. Exact money values,
field permissions and the final posting confirmation remain intact.

### Simple product alignment follow-up (2026-11-04)

Shared UI 0.1.67 reduces the Simple product page and card horizontal padding to
`--janso-space-4` below the existing 40rem field-pair breakpoint. This leaves
254px of input space on a 320px phone. The desktop page retains its 52rem cap.
Type, Model and MRP use the existing `FieldPair` columns so short controls align
with the other inputs; all fields stack at full available width on mobile.

Decision: reuse the current form, controls, colours and spacing tokens. These
rules are scoped to `.janso-simple-product`. Auth and Console use workspace links
to the shared UI package, so their lockfile resolutions remain unchanged.

# Invoice Designer UI — live phase checklist

The working checklist for the designer front end. [invoice-design.md](invoice-design.md)
governs the service and its contract; this file tracks the UI build only.

**Agreed scope (2026-10-25).** UI first, **static fixtures only** — no API calls, no
persistence beyond the browser, no asset upload, no PDF. The layout types mirror the shape
the canvas schema will take at `1.1.0` (item-table columns, totals rows, tax grouping,
print options) so wiring the real service later is a change of data source, not a rewrite.
The editor gets its own visual language: a new token layer and stylesheets inside
`packages/ui`, never per-app or inline CSS.

**Interaction model.** Zones with live preview is the default — hover outlines a region,
clicking it opens that region's typed options, every change re-renders instantly. Free
placement with millimetre precision is a per-zone toggle for people who want it.

| Phase | Scope | State |
|---|---|---|
| 1 | Paper and engine — editor tokens, `designer.css`, mm geometry, page frame, rulers, dot grid, zoom, static types and fixtures | **done** |
| 2 | Selection and inspector shell — hover outlines, selection ring and handles, element tree, keyboard model, inspector chrome | **done** |
| 3 | Design controls — paper, margins, theme, title, show/hide, type, colour, borders, spacing, and the control library behind them | **done** |
| 4 | Item table and totals — column designer with add/remove and reorder, on-canvas width handles, totals row builder | **done** |
| 5a | Direct manipulation I — undo/redo, drag, resize, grid snapping, smart guides, keyboard nudge, inline text edit | **done** |
| 5b | Direct manipulation II — multi-select, marquee, align/distribute, z-order, duplicate and delete | **done** |
| 6 | Bindings and presets — field palette with sample values, placeholder/resolved toggle, copy marking, thermal presets, printable-area and page-break warnings | **done** |
| 7 | Gallery and version UX (local) — template cards with live thumbnails, draft/live badges, version history, publish confirmation | **done** |
| 8 | Polish and review — keyboard-only pass, roles and focus order, contrast in three palettes, empty states, 200-element performance, screenshots, docs | **done** |

## Phase 1 — delivered

- `packages/ui/src/styles/canvas-tokens.css` — editor density, paper geometry, ruler and
  handle sizing, canvas stacking order. Colour-free by construction.
- Canvas colour tokens in all three palettes (`theme-light`, `theme-dark`,
  `theme-ledger`), with identical key sets, enforced by `tests/tokens.test.ts`.
- `packages/ui/src/styles/designer.css` — editor chrome and the document paper surface.
- `packages/ui/src/lib/paper.ts` — paper sizes, orientation, printable area, zoom steps,
  fit-to-viewport, millimetre/pixel conversion.
- `packages/ui/src/components/DesignCanvas.tsx`, `CanvasRuler.tsx`, `ZoomControl.tsx`.
- `apps/console/app/(editor)/` — a full-bleed route group outside the console shell, with
  the designer at `/invoice-designer/[templateId]`.
- Layout types and fixtures: a GST tax invoice on A4, a compact A4, an 80mm thermal
  receipt and a delivery challan, over one sample invoice with six lines, HSN codes,
  batch and expiry, CGST/SGST, round-off and amount in words.
- `apps/console/designer-preview.html` — the dependency-free static review page, following
  the same convention as `apps/console/preview.html`: double-click it, no build step, and
  it links the real stylesheets so a token change shows up on reload. It carries a palette
  switch, the stepped zoom and the copy-mark switch.

**Verified.** `@janso/ui` 1861 tests pass (34 of them new), with the four new modules at
100% statement coverage; the console's 35 designer tests pass; `pnpm -r typecheck` is
clean; the token parity and colour-free checks accept the two new stylesheets, and the
class-coverage check confirms every class the new components emit is styled.

**Found by its own tests.** The GST template's column widths summed to 204mm inside a
190mm table — the one layout error that looks fine on screen and comes out of a printer
wrong. The fixture assertion that every column set fits its table caught it; widths now
total exactly 190mm.

## Open questions this UI must not answer silently

1. **The renderer.** The on-screen preview is the client's own rendering of the layout
   tree. The authoritative PDF needs a server renderer that produces identical output
   ([invoice-design.md](invoice-design.md) §9.1); until it exists, "Download PDF" is
   present in the toolbar and **disabled, with the reason attached**, rather than absent
   (which reads as "it must be somewhere else") or producing something that differs from
   the preview. Added in phase 8: the sentence had been in this doc since phase 1 and the
   control had never been built.
2. **Object storage.** No upload path exists, so there is **no asset panel and no upload
   anywhere in the editor** (§9.2). An `IMAGE` or `SIGNATURE` element renders whichever of
   the fixture's two assets it names, and an element naming none prints an empty frame —
   which `checkLayout` reports for an image and deliberately does not for a signature,
   since a blank signature box is a space to sign. Choosing or replacing an asset is not
   offered, because the only honest version of that control uploads a file.
3. **Element options beyond 1.1.0.** Column grouping, per-element locale and number
   formatting are undecided (§9.3). The UI exposes only what the typed schema carries.
4. **Localisation of static text.** One string per element today; multi-language documents
   need a decision (§9.6) before the designer offers a language switch.

## Phase 2 — delivered

- `packages/ui/src/components/SelectionLayer.tsx` — the editing affordances as a layer
  *above* the document: hover outline with a name chip, selection ring, eight resize
  handles, a millimetre size badge. One listbox with one option per target, so a page of
  200 elements is one tab stop and the arrow keys move the selection.
- `packages/ui/src/components/Inspector.tsx` — the panel's anatomy (group, labelled row,
  hint, empty state, `Kbd`), so phase 3's controls drop into a shape already proven
  against a forty-row page.
- `app/(editor)/invoice-designer/selection.ts` — the model: every selectable target with
  its **absolute** page millimetres, readable names (a field is its binding, static text
  is its first words), and `navigate()` as a pure function. Two levels, not a flat list:
  `↓`/`↑` move between siblings, `→` enters a zone, `←` leaves it, `Home`/`End` jump,
  `Esc` clears, and the ends hold rather than wrapping.
- `ElementTree.tsx` — the same selection as a tree in the rail, with roving tabindex, for
  finding an element that is two millimetres tall or behind another one.
- `SelectionInspector.tsx` — what the panel can state today: identity, geometry in
  millimetres, binding with its resolved sample, content, column and totals summaries,
  typed style values, and a zone's placement mode.
- Selection wired through `DesignerShell`: canvas and tree are two views of one selection,
  the status bar announces it politely, and a template switch drops it because the ids
  change with the template.
- `designer-preview.html` updated: one zone hovered and one element selected, side by side.

**Verified.** `@janso/ui` 1880 tests pass (19 new for the layer and the inspector);
console designer tests 70 pass; `pnpm -r typecheck` clean across the workspace;
`SelectionLayer` and `Inspector` at 100% statements.

**Review pass, six findings, all fixed with tests:**

1. A click on bare paper did not clear the selection — every editor clears it.
2. Moving the pointer off a target onto bare paper left the hover outline behind: the
   container's own `pointerleave` cannot fire while the pointer is still inside the layer,
   so each target now clears its own hover.
3. The canvas had `outline: none` on focus, so with nothing selected — the state a keyboard
   user *starts* in — focusing it was invisible.
4. A leaf tree node claimed `aria-expanded="false"`, which tells a screen reader there is
   collapsed content when there is none.
5. Focus-driven hover never cleared on blur, leaving a stale outline after tabbing away.
6. The status bar's live region announced hover as well as selection, so one keyboard move
   spoke twice; hover is now reported beside the live region, not inside it.

A seventh, smaller one: `janso-editor__node--element` carried no CSS rule, so it was a
class name pretending to be a style. Removed rather than given a rule it did not need.

## Phase 3 — delivered

- `packages/ui/src/components/EditorControls.tsx` — the control family: `MeasureField`
  (number with a unit, arrow stepping, `shift` for a coarse step, commit on Enter or blur),
  `SegmentedControl` (a radiogroup, one tab stop, arrows move and commit), `ColourField`
  (picker plus the hex a brand guideline actually gives you, with caller-supplied document
  swatches), `Toggle`, `EditorSelect`, `EditorTextField`, `InspectorStack`.
- `app/(editor)/invoice-designer/layout-edit.ts` — the rules, as pure functions:
  paper and orientation (a roll never rotates), margins that always leave 10mm to print on
  and are re-clamped when the paper shrinks under them, zone and element geometry clamped
  so nothing leaves its parent, style patches that delete a cleared property, and column
  widths capped at what the table has left.
- `SelectionInspector.tsx` — every row is now a typed control: page, margins, grid, theme,
  print options, zone title and placement, element geometry, content, binding label, type,
  box, and the per-type options (image fit, symbology, tax grouping, column show/width).
  No "custom CSS" escape hatch, by design.
- `DesignerShell.tsx` owns the layout: edits funnel through one `edit()` that applies a
  pure change, counts it, and keeps each template's edits separate. A shipped template is
  read-only, as the domain says.
- `designer-preview.html` shows the controls at the values the selected element carries.

**Verified.** `@janso/ui` 1904 tests pass (24 new for the controls); console designer
tests 122 pass (27 edit-model, 24 control integration); `pnpm -r typecheck` clean.

**Review pass, five findings, all fixed with tests:**

1. **A colour literal in the design system.** `ColourField` carried `#000000` as the
   picker's value for an unset colour — `tests/tokens.test.ts` caught it, correctly: a hex
   in a component is a colour decision smuggled out of the palette. The unset ink is now a
   required `fallback` prop, supplied by the app beside the document swatches it already
   owns, and the placeholder became a format hint (`#rrggbb`).
2. **A rejected-colour example in a doc comment** tripped the same test. Reworded rather
   than exempting the file — the test reading comments is a feature, not a false positive.
3. **Hiding a column handed it the whole table's width.** `updateColumn` tested the
   *target's* patch against every *other* column, so `show: false` made the others count as
   hidden and the headroom became the full 190mm. Now it sums the other shown columns.
4. **`onSection` took `Record<string, unknown>`**, which let a caller past the model's own
   types — the one thing a typed patch exists to prevent. Now `Partial<CanvasSection>`.
5. **An invalid value on Enter was silently reverted** in both the measurement and colour
   fields, throwing away what the designer typed. Enter now keeps the text with its invalid
   marker so it can be corrected; blur still reverts, because an invalid field must not be
   left behind.

**Behaviour changes that updated phase 1–2 tests** (each noted in the test): the rail's
read-only zone list became the selectable tree; the inspector's margin, geometry, placement
and column rows became controls, so those assertions now read the control's value; and the
toolbar's copy switch gained an explicit name, because the inspector now has selects of its
own.

**Known gap for phase 4:** `updateColumn` only patches columns a layout already carries.
Adding, removing and reordering columns is the column designer's job, and the model needs
functions for it.

## Phase 4 — delivered

- Model functions in `layout-edit.ts`: `addColumn` (arrives **hidden** when the table is
  full, so nothing else changes width), `removeColumn` (never leaves a table empty),
  `moveColumn`, `distributeColumns` (proportional fit, drift onto the widest column),
  `resizeColumnBoundary`, `availableColumns`, and the totals equivalents
  (`addTotalsRow`, `removeTotalsRow`, `moveTotalsRow`, `availableTotalsRows`).
- `ColumnDesigner.tsx` — per column: show/hide, width, rename, reorder, remove; an add
  menu of the keys the table lacks; "fit to table width"; and a budget stated both as a
  sentence and as a progressbar, because *whether the table is full* is a shape.
- `TotalsBuilder.tsx` — the printed rows, in printed order, with add/remove/move. A block
  may end up empty, which is correct for a document that carries no money.
- `ColumnHandles.tsx` — dividers on the table itself, with pointer capture, a live
  millimetre readout, and deltas converted once so a drag moves the same paper distance at
  any zoom. Shown only for the selected item table, and never on a shipped template.
- `TOTALS_ROWS` added to the layout model, so the totals vocabulary is named once rather
  than implied by a union.

**Verified.** `@janso/ui` 1904 pass; console designer 161 pass (39 new); designer files
typecheck clean.

**Review pass, two findings, both fixed with tests:**

1. **Dragging a divider on a full table did nothing.** `updateColumn` caps a width at the
   table's free space — right when a designer *types* 52mm, wrong for a divider, which
   moves a boundary. `resizeColumnBoundary` now takes the millimetres from the next shown
   column (skipping hidden ones, never squeezing the neighbour below 1mm, falling back to
   the capped behaviour for the last column, which borders the table edge). The two
   gestures stay deliberately different, and the distinction is documented at both.
2. **The dividers were unlabelled spans in the accessibility tree.** They are a pointer
   affordance whose every width is also a labelled field in the inspector, so the layer is
   now `aria-hidden` rather than presenting eleven nameless elements carrying a tooltip.

**Note for phase 5:** `ColumnHandles` already establishes the drag pattern this phase
needs — pointer capture, one conversion from screen pixels to paper millimetres, a live
readout — so element drag and resize should reuse its shape rather than invent a second one.

## Phase 5a — delivered

Phase 5 was split to keep each change reviewable. 5a is the single-selection half: moving,
resizing, aiming, and taking it back.

- `packages/ui/src/lib/transform.ts` — the arithmetic, framework-free: `moveRect` (snaps
  the **position**, not the delta, so a rectangle that started off-grid can reach the
  grid), `resizeRect` (a north or west handle moves the edge *and* the origin; below the
  minimum it stops rather than inverting), and `alignmentGuides` (nearest candidate per
  axis, like compared only with like, a centre beating an edge at equal distance, one line
  per position).
- `app/(editor)/invoice-designer/history.ts` — undo/redo as an immutable stack, with
  **label coalescing**: consecutive edits carrying the same label inside 700ms replace the
  top entry. Typing a heading is one undo; typing, dragging, then typing is three. Clock
  injected, so the window is tested without waiting.
- `SelectionLayer.tsx` gained the gesture: pointer capture, deltas in paper millimetres
  measured from where the pointer went down, an explicit `start`/`move`/`end` phase, a
  0.3mm threshold so a click with jitter in it stays a click, and `onActivate` for
  double-click and Enter. It applies nothing itself — snapping, bounds and alignment belong
  to the layout model, which is the only thing that knows the zone.
- `GuideLayer.tsx` and `InlineTextEditor.tsx` — guides drawn only during a gesture, and a
  textarea sized and styled exactly like the element it covers.
- `DesignerShell.tsx` — one `transform()` applying the layout's rules, history per
  template, undo/redo in the toolbar with the action named in the tooltip, `ctrl+Z` /
  `ctrl+shift+Z` / `ctrl+Y`, `alt+arrow` to nudge, `alt+shift+arrow` for a grid step,
  `alt+ctrl+arrow` to resize from the bottom-right, and the selection's position in the
  live region so a nudge is audible.

**Verified.** `@janso/ui` 1934 tests pass (29 for the selection layer, 20 for the transform
arithmetic); console designer tests 209 pass (48 new); `tsc --noEmit` clean in both
packages; the token parity, colour-free and class-coverage checks still accept the
stylesheets.

**Review pass, six findings, all fixed with tests:**

1. **A fine nudge cancelled itself.** `alt+arrow` snapped to the grid *and* then accepted a
   1mm alignment correction, so pressing it on an aligned element moved nothing — and from
   an on-grid position it could never leave that grid line at all. A pointer drag aims; a
   key is exact. `transform()` now takes `{ aim, snapMm }`: plain `alt+arrow` moves one
   millimetre with no grid and no correction, `alt+shift+arrow` moves a grid step and lands
   on the grid.
2. **A shipped template could be edited with the keyboard.** `readOnly` was enforced on the
   controls and on the drag callbacks, but `alt+arrow` went straight to `transform()`. The
   guard moved into `edit()` — the single funnel every change passes through — so it holds
   for routes added later too.
3. **A read-only template still drew eight resize grips.** Handles rendered whenever an
   element was selected, regardless of whether a drag was possible. Grips that do nothing
   when pulled are worse than none.
4. **A selected zone advertised a drag it could not perform.** The grab cursor and the
   pointer handlers were on any selected target; a zone is placed by the layout, so only an
   element is draggable now.
5. **A lost `pointerup` left a stale drag origin.** The shell re-pinned the origin by
   comparing ids, so a second drag on the same element reused the first drag's starting
   rectangle and the element jumped. The gesture now carries its phase, and the origin is
   pinned on `start`.
6. **`ctrl+Z` and `alt+arrow` reached past a focused text field.** Half way through typing
   a margin, `ctrl+Z` means "take that word back", and a nudge must not move an element out
   from under someone editing its label. While text entry has focus the keyboard belongs to
   the field; zoom, which has no such conflict, stays global.

A seventh, smaller one: the gesture reported `4.999999999999998` for a 5mm drag. The layout
model rounds, so nothing was wrong on paper, but a measurement should read as one — the
conversion now rounds to 0.01mm, finer than the model's own 0.1mm.

**Behaviour change that updated a phase 2 test:** the status bar's selection readout now
carries position as well as size, because the same live region announces a keyboard nudge
and "it moved" is only audible if the numbers that moved are in it.

**`designer-preview.html` is deliberately frozen at phase 3.** It is a hand-written,
dependency-free mirror of the editor's chrome for looking at tokens without a build step.
Teaching it to drag, snap and undo would mean a second implementation of this phase's
rules, which is the thing the model functions exist to prevent. Use `pnpm --filter console
dev` and `/invoice-designer/tpl-gst-a4` for the live editor; the preview page stays useful
for exactly what it was for — the three palettes against the paper.

## Phase 5b — delivered

The set half: selecting several things, and the operations that only make sense on a set.

- `app/(editor)/invoice-designer/layout-arrange.ts` — the group operations as pure
  functions, deliberately *not* the single-element ones in a loop, because that is where
  this goes wrong. `moveSelection` reduces one delta until every member can take it, so the
  group stops when its first member reaches a zone edge and the arrangement survives the
  gesture. `alignElements` aligns against the box around the selection — and against the
  *zone* for a lone element, since aligning one element to its own bounding box is a button
  that does nothing. `distributeElements` equalises the **gaps**, not the centres, because
  gaps are what the eye reads on a document. `reorderElements` writes array order and
  `zIndex` together, so the preview, the schema and the rail's tree cannot disagree about
  what is in front. `duplicateElements` lands each copy directly after its source and turns
  the offset inwards when there is no room outwards. `deleteElements` never removes a zone.
- `ArrangePanel.tsx` — align, distribute, stack, duplicate, delete, with the selection's box
  in page millimetres and the lone element's depth stated as "3 of 7 in this zone".
  Buttons, not drag: "these six share a left edge" is an exact statement, and a pointer is
  the wrong instrument for making it.
- Multi-select through `SelectionLayer` and `ElementTree` — shift or ctrl adds, clicking a
  member again removes it, shift with an arrow extends, `ctrl+A` takes the active *zone*
  rather than the page, and the two views stay one selection.
- `targetsInRect` in `selection.ts` plus the marquee gesture — **touching counts, not
  containing**, so a 190mm divider is catchable; zones are never caught.
- `DesignerShell` keyboard set: `ctrl+D`, `Delete`/`Backspace`, `ctrl+[`/`]` and
  `ctrl+shift+[`/`]`, each stepping aside for a focused text field.
- The per-element inspector hides for a group — one font size shown for four elements with
  four different sizes is a lie whichever one it picks — and Arrange becomes the whole panel.

**Verified.** `@janso/ui` 1958 tests pass across 67 files; console designer tests 295 pass
(86 new across `invoice-designer-multiselect` and `invoice-designer-arrange`);
`pnpm -r typecheck` clean across `packages/ui`, `apps/console` and `apps/auth`.

**Note on running these locally.** The designer suites are jsdom- and `userEvent`-heavy and
this machine is load-sensitive: run in parallel with another suite, four of them fail on
timeouts that have nothing to do with the code. `pnpm vitest run --no-file-parallelism` is
the trustworthy figure, and the one quoted above.

**Review pass, two findings, both fixed with a failing test first:**

1. **A group drag aimed at its own members.** The alignment candidates excluded the anchor
   but not the rest of the selection, so a group-mate travelling with the anchor was still
   treated as something to line up against. Two elements sharing a baseline — a row of
   fields, the commonest thing on a document — could not be dragged a short distance at
   all: the correction pulled the anchor back onto the edge it was carrying with it, the
   step rounded to nothing, and the page sat still. It also drew a guide against an element
   that was moving. The whole selection is excluded now.

   The regression test needs a purpose-built two-element page (`BASELINE_PAIR`), because
   the four shipped fixtures *hide* this: every near alignment on a real invoice has
   unselected neighbours on the same line, and they supply the same correction, so the
   defect sits behind correct behaviour. Worth recording — a fixture rich enough to look
   realistic is not automatically a fixture that can fail.

2. **Discrete actions coalesced in undo history.** `record` collapses same-labelled edits
   inside 700ms, which is right for continuous input — typing a heading, dragging an
   element — and wrong for a button. Walking an element up a stack with four quick presses
   of "Bring forward" was one history entry, so a single undo dropped it below where it
   started; `ctrl+D` twice made two copies that one undo took back together. `record` now
   takes `{ coalesce }` and `edit()` takes `{ discrete: true }`, which every arrange
   command passes. This also fixed the phase-3/4 column and totals buttons, which had the
   same defect from the day they shipped — the labels are per-action, so the bug arrived
   with the second button that anyone would press twice.

**Quality pass — one consolidation.** `Math.round(value * 10) / 10` was written out in six
places across four files, as `round` in `transform.ts`, `round` in `layout-arrange.ts`,
`tenth` in `DesignerShell.tsx` and three times inline in `layout-edit.ts`, and the private
`snapTo` in two of those duplicated the exported `snapMm` nobody was using. The layout
model's storage scale is a *decision* — a tenth of a millimetre, finer than a printer
resolves and coarser than float drift — so it is now `roundMm` in `packages/ui/src/lib/paper.ts`,
the module that already owns millimetre geometry, and `snapMm` rounds its own result.
That also fixed a latent bug in passing: snapping to a fractional step reintroduced the
drift the rounding exists to remove, since 3 × 2.5 is 7.500000000000001. `SelectionLayer`
keeps its own 0.01mm gesture rounding, which is a different and deliberate scale.

**§5 and §6 walk.** Nothing to report, and nothing in scope to report: this phase adds no
route, no query, no persistence and no permission check. It reads four static fixtures and
holds the result in React state, so tenant scoping, object-level authorization, idempotency,
`assert_postable` and audit have no surface here. `/security-review` is not warranted until
phase 2 of the service work gives the editor an API to call — at which point every
operation in `layout-arrange.ts` becomes a request body and the walk becomes real.

## Phase 6 — delivered

Bindings, presets, and the half of a designer a preview cannot do.

- `app/(editor)/invoice-designer/layout-warnings.ts` — `checkLayout`, pure, returning typed
  warnings that each name the zone or element to look at. Seven checks: a zone outside the
  printable area, overlapping zones, a page break inside a zone, an element outside the
  zone that clips it, a column set wider than its table, a binding the sample document
  cannot resolve, and a missing or dangling asset. `error` means it will print wrong;
  `warning` means it may be deliberate and says what will happen.
- `WarningsPanel.tsx` — the list, errors first and then down the page, **every row
  selecting its subject**. "A zone is 4mm past the right edge" is unactionable until you
  know which zone, and hunting for it on a page of seven is where a panel stops being used.
  It renders nothing when there is nothing wrong.
- `presets.ts` — `a4-invoice`, `thermal-80`, `thermal-58`. A preset applies the typed
  settings *and* fits the geometry, because changing paper through the inspector alone
  leaves every zone 190mm wide on 74mm of printable width — the layout is still there and
  none of it prints. Widths scale, heights do not, vertical positions translate with the
  margin, zones stack on a roll, and the item table is refitted to a receipt-sized column
  set that sums to the table exactly.
- `FieldPalette.tsx` — every path the document can print, grouped by root, each with its
  sample value, searchable by **value as well as path**. Placing drops a `FIELD_BINDING`
  into the selected zone below whatever is there, and selects it.
- `layout-edit.ts` additions: `placeField`, `boundPaths`, `freeId`/`elementIds`, and the
  copy set (`addCopy`, `removeCopy`, `moveCopy`, `availableCopies`).
- `DocumentLayer` gained `values: 'resolved' | 'placeholder'`, with a toolbar switch.
- The copy set is editable in the Print group — add, remove, reorder — never below one.

**Three decisions worth stating**

1. **The palette is an allowlist, not a text field.** Binding paths are a published
   contract the service validates (`sample-document.ts`), so a designer typing
   `voucher.invoice_no` would get a box that previews fine and fails on save. Offering only
   what resolves makes that mistake unavailable rather than merely discouraged. It is
   convenience, not enforcement — the service must still validate every path it is sent.
2. **Placeholder mode keeps the geometry.** It swaps values for paths and changes nothing
   else: same row count, same boxes. A mode that reflowed the page would be useless for
   checking the page, which is what the canvas is for. Labels survive too, because a label
   is static text the document always prints.
3. **A preset reshapes; it does not redesign.** A two-column "Bill to / Ship to" header
   becomes two narrow columns, not the stacked pair a real receipt uses, because deciding
   that is design and this is arithmetic. Reshaping is lossy and one `ctrl+Z` is the
   honest reverse.

**Verified.** Console designer tests 348 pass across 11 files (53 new: 23 for the checks
and presets, 28 for the editor, 2 for the style guard); `@janso/ui` 1958 pass across 67
files; `tsc --noEmit` clean for `packages/ui` and for every designer file.

**Found by its own tests, again.** The "nothing is wrong with a shipped template"
assertion — deliberately the load-bearing one, because a check that fires on all four
fixtures is a check nobody will keep — failed on `asset-missing`. The fixtures were right
and the check was wrong: a `SIGNATURE` with no asset is a *space to sign*. The delivery
challan's "Receiver's signature" is meant to be blank, and so is every invoice signed with
a pen. Warning about those would have been warning about the normal case. Only `IMAGE` now
requires an asset; a dangling `assetId` is still reported for both.

**A second one, from the preset tests.** Converting a roll back to A4 left the first zone
7mm *above* the printable area, because the roll's 3mm top margin became A4's 10mm and
vertical positions were being left alone. Positions now translate with the printable area —
symmetric with the horizontal treatment, and a no-op when the margins have not moved, so
re-applying the A4 preset to an A4 layout preserves it exactly. What remains after that
fix is honest and tested: a roll accumulates more height than one sheet holds, no
arithmetic fits it, and the panel reports the page break instead of this code pretending
the text shrank.

**Review pass, two quality findings, both applied**

1. **A rectangle-overlap test written twice.** `targetsInRect` (phase 5b's marquee) and the
   new zone-overlap check had the same four strict comparisons. "Touching is not
   overlapping" is one rule that both need to agree on, so it is now `rectsOverlap` in
   `packages/ui/src/lib/paper.ts`, beside `Rect` and `printableArea`.
2. **`boundPaths` was scanning the layout on every render**, including every pointer event
   of a drag. Memoized on the layout, like the warnings.

Phase 5b's `roundMm` consolidation paid off here: `layout-warnings.ts` reuses `formatMm`
for its millimetre figures, so "4mm past the right edge" cannot become
"4.000000000000001mm past the right edge" in a sentence a designer reads.

**New guard: `invoice-designer-styles.test.ts`.** `packages/ui` checks that every `janso-`
class its own components emit is styled, and explains why — the component tests run with
`css: false`, so a misspelt class passes every behavioural assertion and renders unstyled
in a browser. But that check scans `packages/ui/src/components`, and most of the designer's
markup is in the editor route group, which it never looked at. Phase 2's review found
exactly this defect by hand (`janso-editor__node--element` was a class name pretending to
be a style). The console now runs the same scan over `app/(editor)/invoice-designer/*.tsx`
against the shared stylesheets, which also enforces the other half of the rule: the
designer styles through `packages/ui`, never its own CSS.

**Two phase-1 tests changed, both deliberately.** The copy preview switch was hidden for a
one-copy template, which was right while the set was fixed — a two-option control nobody
could act on. Now that the set is editable it is always offered: the mark is printed
content, a single-copy receipt designer needs to see whether it collides with the header,
and the set they can now edit starts at one. The second test asserted that a copy the
switched-to template does not print disappears from the page; it now asserts that against
the switch and the printed mark, because phase 6's add-copy menu legitimately lists every
copy the template does *not* print.

**§5 and §6 walk.** Nothing to report. As in phase 5b there is no route, query, persistence
or permission check in scope — four static fixtures in React state. The one item worth
recording for later: the palette's allowlist is a *client* convenience and the service must
still validate every binding path it receives (§5.6, never trust the client), and
`checkLayout` is pure precisely so it can gate a publish server-side when there is one.

**`designer-preview.html` stays frozen at phase 3,** for the reason phase 5a gave: it is a
hand-written, dependency-free mirror of the editor's chrome for looking at tokens without a
build step, and teaching it this phase's rules would mean a second implementation of them.
The new stylesheet rules use existing tokens, so it still renders correctly for what it is
for. Use `pnpm --filter console dev` and `/invoice-designer/tpl-gst-a4` for the live editor.

## Phase 7 — delivered

The way in, and the record of what has printed.

- `publication.ts` — versions and publishing as pure, clock-injected functions, the same
  shape as `history.ts`. `publish` takes a snapshot and makes it live; `canPublish` is the
  gate; `snapshotOf`/`isRestorable` say what this session can honour.
- `TemplateGallery.tsx` + `app/(editor)/invoice-designer/page.tsx` — a card per template,
  each drawing the **real document** scaled down, with Live/Draft, a Shipped marker, the
  live version and its date, and phase 6's `checkLayout` on the card so a broken template
  is visible before anyone opens it. Server component; no client state to hydrate.
- `PaperThumbnail` in `@janso/ui` — a page shrunk to a box by `transform: scale`, scaled by
  the **longest** edge so an A4 sheet and an 80mm roll fit the same box and stay visibly
  different shapes. Decorative (`aria-hidden`): a scaled 7pt address line is a shape that
  says "invoice", not something to read out.
- `VersionPanel.tsx` — the history, newest first, the live one marked, and the publish
  control with a sentence saying what it will carry or why it is refused.
- The publish confirmation: what will happen, the warnings being accepted, and a required
  change summary enforced through the dialog's own error channel so the dialog stays open
  with what was typed.

**Three decisions worth stating**

1. **Publishing is gated on the layout being printable.** An `error` from `checkLayout`
   disables the control with the count in the reason; warnings are listed in the dialog and
   can be accepted. This is what phase 6's checks were for — a check that never blocks
   anything is a decoration.
2. **Dirtiness is a reference comparison, not an edit count.** `layout !== snapshot`
   against the published version. Every edit returns a new tree and history keeps the
   actual objects, so undoing back to the published state restores *that* object and the
   panel correctly says nothing has changed again. Counting edits cannot do that.
3. **Restore is offered only where it can be honoured.** This session keeps the layouts it
   published; the versions a template arrived with live in the service that does not exist
   yet. The row says so instead of carrying a button that quietly does nothing.

**Verified.** 26 new tests in `invoice-designer-gallery.test.tsx`, 9 in
`packages/ui/tests/paper-thumbnail.test.tsx`.

**Known gap, deliberately not closed: the gallery is not in the console nav.** Reaching it
means typing the URL. Adding a nav entry needs a permission key, and permissions are a
fixed catalogue (CLAUDE.md §6.13) belonging to the `design` service's own work — inventing
one here would be answering an open question silently. The route is live at
`/invoice-designer`; the nav entry lands with the service.

---

## Phase 8 — delivered

The pass that looks at the thing rather than at the tests for the thing. It found more than
the other seven phases' reviews combined, which is the argument for doing it.

**New guards**

- `invoice-designer-a11y.test.tsx` — 20 tests the rest of the suite is blind to by
  construction, because every other test looks a control up *by* its accessible name and so
  can never discover that nobody could find it. Landmarks and their names, one h1 and no
  skipped level, a sweep asserting no button/input/select is nameless, the tab order across
  regions, the one-tab-stop canvas, editing with no pointer at all, empty states, and a
  200-element page.
- 16 designer pairings added to `packages/ui/tests/contrast.test.ts`, in all three palettes.

**Six findings, all fixed**

1. **Every editor input was drawn at 1.26:1.** `--janso-editor-chrome-line` was doing two
   jobs — a control's edge and a divider between regions — and had been tuned for the
   second. A control boundary is information a low-vision user needs to find the field
   (WCAG 1.4.11); a divider is decoration. The editor's inputs, selects, textareas,
   segmented controls and zoom group now use `--janso-control-line`, the same token the
   console's forms use, and it is asserted on the editor's own surface. The divider token
   stays light, with the reasoning recorded where the next person will look for it.
2. **The zone outline and the printable-area guide missed the gate** at 2.89:1 and 1.77:1
   on paper. Both carry meaning — where a zone is, where printing stops — and both were
   darkened in all three palettes.
3. **The editor had no `main` landmark.** It had a banner, a navigation, a complementary
   panel and a contentinfo, and the one region holding the work was a bare `div` — no name,
   no skip target.
4. **The rail clipped its own content.** No overflow rule, so on a 1000px viewport the
   field palette and the version panel were not below the fold, they were *unreachable*.
   The rail scrolls now, and the element tree and the palette are bounded so all four group
   headings stay on screen.
5. **A preset left element type at its old size.** `thermal-80` took the base from 9pt to
   7pt and left a 14pt company name at 14pt in a box that had gone from 96mm to 37mm. The
   screenshot showed "Nandini Trading Company" clipped to "Nandini". Element sizes now
   scale with the base. **No geometry check could have found this** — the box fits
   perfectly; it is the text inside it that does not.
6. **A continuous roll was drawn at its nominal length** with the content hanging onto the
   backdrop below the sheet, which reads as a broken editor rather than as a long receipt.
   A roll is now drawn as long as its content plus the bottom margin, never shorter than
   nominal, through a `drawnHeightMm` override on `DesignCanvas`. The model keeps the
   nominal stock, because that is what the renderer is told about.

A seventh, found in the same screenshot: the field palette's rows collided — name, "on the
page" tag and sample value competing for a 280px rail. They stack now, which also puts each
value directly under the name it belongs to.

**Screenshots.** Eight, in `.test_artifacts/invoice-designer-phase8/` (gitignored): the
gallery and the editor in all three palettes, plus placeholder mode and the 80mm reflow.
Captured against `next dev` with system Chrome through `.tools/ui-review-runner`, since no
Playwright browsers are installed in this environment. Findings 4, 5, 6 and 7 came from
*looking at these*, after thirteen test files had passed.

**200 elements.** The page renders, stays one tab stop, `ctrl+A` selects all 200 and the
Arrange panel reports them. The models are asserted linear rather than timed tightly — this
machine is demonstrably load-sensitive — with a generous ceiling that still catches the
failure that matters: a nested scan turning 200 elements into 40,000 comparisons.

**Two reasoned exclusions from the contrast table**, both recorded rather than suppressed:

- `--janso-canvas-page-edge` on the backdrop. The sheet is identified by its fill against
  the backdrop and by its drop shadow, both of which survive greyscale; the hairline is the
  third cue. A 3:1 hairline would be a near-black outline around a sheet of paper.
- `--janso-canvas-copy-mark`, the 7%-alpha watermark. **This one is a real open issue, not
  just an exclusion.** Choosing `watermark` as the copy-mark position currently *replaces*
  the readable top-of-page label rather than accompanying it, so the only indication of
  which copy you are holding sits at about 1.1:1. No gate it could meet would still look
  like a watermark. The fix is a document-rendering decision — print the label *and* the
  watermark — which belongs to [invoice-design.md](invoice-design.md) and not to a polish
  pass. **Raised, not fixed.**

**Known limit, stated plainly: the editor cannot measure text.** A box too small for the
words in it is invisible to `checkLayout`, which checks geometry. The 80mm reflow still
clips "PLACE OF SUPPLY" and wraps the company name over the address below it, because
heights deliberately do not scale — scaling a 4mm field to 1.5mm produces a layout that
fits and cannot be read. Detecting this needs text metrics, which is the server renderer's
job ([invoice-design.md §9.1](invoice-design.md)). It is the reason "a preset reshapes, it
does not redesign" is written where it is.

**Verified.** Console designer tests **400 pass across 13 files**; `@janso/ui` **2015 pass
across 68 files**; `pnpm -r typecheck` clean across `packages/ui`, `apps/console` and
`apps/auth`; contrast, token-parity and both class-coverage checks green in all three
palettes. The full console suite is **3198 of 3199**, the one failure being an async-focus
test in the platform-access area that passes in isolation — this machine's load
sensitivity again, and not a designer file.

**Docs.** [invoice-design.md](invoice-design.md) §9.3 now records that a concrete canvas
proposal exists and is *not* ratified, §9.4 records what the roll work does and does not
settle, and its decision log carries the entry for building the front end ahead of the
schema. Open questions 1, 2, 5, 6 and 7 are untouched and still open.

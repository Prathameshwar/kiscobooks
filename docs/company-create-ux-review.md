# Company creation — UI, style and UX review

Requested 2026-10-26: review the company create screen and bring it to a professional
standard. Reviewed and executed in one pass. The screen is `/companies/new` —
`CompanyWizard`, six steps.

## How it was reviewed

The wizard needs a session and a running identity service, so it was reviewed by **rendering
the real component with the real stylesheets** rather than by reading its source: a temporary
harness mounted `CompanyWizard` with the same mocks `company-wizard.test.tsx` uses, wrote each
step's markup out, wrapped it with the production stylesheet set, and screenshotted it in
Chrome. Measurements were then taken in the page rather than judged by eye.

That mattered. **Two findings from the first look were artifacts of the harness, not the
product**, and both were dismissed after measuring:

- Mismatched control heights (a 52px date input against a 36px select) — the harness had not
  put `janso-root` on `<body>`, so no base typography applied and font metrics inflated the
  native input. With the class, 38px against 36px.
- A serif typeface throughout — same cause. The real app sets the font on `.janso-root`,
  which the root layout puts on `<body>`.

A third was **downgraded** by measuring: the sticky action bar was reported as clipping the
form. At full scroll nothing is occluded (the bar returns to its static position); mid-scroll
it covers exactly one field at a time. Real, worth fixing, not "content is unreachable".

Anyone repeating this: the harness is `.test_artifacts/wizard-review/` (gitignored) and the
screenshot runner is `.tools/ui-review-runner/wizard-shots.mjs`.

## What was already good

Worth recording, because the gap to a professional standard was smaller than the list below
suggests. Jurisdiction conventions arrive as *editable suggestions* — pick India and the
fiscal year moves to April with Indian digit grouping and GST; the legal name derives both the
short name and the company code while staying overridable; the finish is a retryable sequence
where a retry replays rather than duplicates; and step 6 opens with "Check it over. Nothing
has been created yet."

## Findings and what was done

### 1. Required fields were invisible until you failed

Measured on step 1: four of six fields carried `required` in the DOM, zero asterisks, zero
"optional" markers. The red borders and per-field "Required" appeared only after pressing
Next. A design-system gap rather than a wizard one — no component rendered a marker and
[design-system.md](design-system.md) did not address it.

Fixed in the design system, so every form in the console gains it: `FieldLabel` draws the mark
from the `required` prop callers already pass. See §5.13 and decision 80. The structural
constraint is recorded there and is the reason this took a probe before it took an edit: a
marker **inside** the `<label>` breaks `getByLabelText`, which 426 queries across 169 console
test files use. `getByRole` honours `aria-hidden`; `getByLabelText` reads raw text.

### 2. The sticky action bar occluded a field at a time

68px pinned to the bottom of the viewport with no clearance under the form, so a field could
be read with its lower half behind the bar — and `scrollIntoView` on a validation failure
could park the invalid field underneath it. The second is the one that mattered.
`scroll-padding-bottom` on the scroll container fixes it, clearance padding fixes the first,
and a top border makes the bar read as a surface content passes beneath.

### 3. Stored values were reaching the screen as themselves

The tax dropdown offered **`gst_in`** as its option text; the review step printed "Tax:
gst_in" and "rounded half_up". The wizard already had human labels for entity types and
rounding modes as local constants — they simply were not used everywhere a value is shown.

Now [`app/lib/company-labels.ts`](../mfes/apps/console/app/lib/company-labels.ts), one home for
these vocabularies, with the review step and the select both reading it.

**An open item this exposes.** Entity types and rounding modes are a closed set the client can
own. **Tax systems are not**: `GET /v1/reference/countries` returns `tax_systems: ['gst_in']`
as bare codes, so every jurisdiction the identity service learns about needs a matching entry
here or it shows a code again. The endpoint should return `{ code, label }` as it already does
for currencies and states. Until it does, an unknown code renders as words (`gst_sg` → "GST
SG") rather than as a code — a fallback, not a fix.

### 4. Step 5 was 22 controls in one undifferentiated column

Time zone, language, two date formats, digit grouping, two separators, negative format, two
currency fields, payment terms, three signatory fields and a checkbox, every one full width —
the decimal separator is one character and had the whole width of the form. Two fields were
both labelled **"Currency symbol"** (one was the position), which is a confusing read and two
identical labels for a screen reader.

Now four groups — Dates and time, Numbers, Currency, On printed documents — with short fields
paired, via `FieldGroup`/`FieldPair` in the design system (§5.13, decision 81). The duplicate
label is now "Symbol position".

### 5. The formatting choices had no preview where they were made

Step 6 proved the preview was already computed: "₹12,34,567.89 · rounded half up". That is one
step too late — by then the choice is made and the only way back was Back.

`FormatPreview` renders the same values live on step 5, from the same resolved display config.
It shows a negative amount and zero on purpose: `negative_format` is invisible until a
negative number is on screen, and zero catches a separator typo a positive number hides.

**What was *not* done, and why.** The original review suggested turning date format, language
and time zone into selects. Checking the server first showed all three accept free-form
strings, and checking `formatDate` showed why: it is a pattern formatter with a documented
token vocabulary and deliberate support for quoted literals — `'day' d MMMM` is a case it
handles on purpose. A `Select` would have removed capability the platform offers. They are
text fields with `datalist` suggestions instead, and the live preview is what makes free entry
safe.

### 6. Step 4 was seven flat checkboxes with a dependency chain in prose

Four of seven ended "Permanent once used." in the same type as their descriptions — the one
irreversible fact on each card formatted exactly like the reversible ones — and a three-level
chain (stock → batches → expiry dates) was stated as "Also turns on: Batches."

Now `ChoiceCard`s in a `capabilityTree`: the chain is an indent, the whole card is the label
so the description is part of the target that explains it, "Permanent" is a badge, and a
dependent that was switched on for you says so.

A defect in the new component, found by the existing tests: a label wrapping the whole card
makes every word inside it part of the control's accessible name, so the checkbox announced
itself as "Expiry dates Permanent Record and report expiry against each batch". The name is
now the title via `aria-labelledby`, with the badge and description as `aria-describedby`.

### 7. The review step had no way back to a mistake

The stepper can be clicked back to any completed step, but nothing said so, and a reader who
spots a wrong legal name should not have to work out which of six steps it came from.
`ReviewList` takes `onEdit` and each row carries its step (§5.14).

Scoped carefully: the value is wrapped in a span **only** when there is an action to make room
for. 42 components call `ReviewList` read-only and one of their tests queries
`getByText(…, { selector: 'dd' })`, which stops matching the moment the text moves into a
child. Found by the full suite, fixed by scoping rather than by editing the test.

### 8. Step 6's pre-creation notices read as a list of failures

Three stacked notices of dense prose, two of which described what would *not* happen —
"Warehouse settings will need initialization by an authorized administrator. Default price
levels will need initialization by an authorized administrator." Now one "What creating this
will do" list, a line each, state as a badge: **Included** or **Needs an administrator**. What
is simply added later moved to its own short notice, because it is not blocked on anyone.

### 9. Two different "Back"s on one screen

The top-left "Back" left the wizard; the footer "Back" went to the previous step. The
breadcrumb trail beside the top one already named every destination it offered, so it is gone.
The footer owns "Back" because that is where a wizard's Back lives, and Cancel on step 1 is
the explicit way out.

### 10. The typeface was named and never loaded

`--janso-font-body` has led with Inter since the tokens were written and nothing ever fetched
it: no `@font-face`, no `next/font`, no link. Every console screen rendered in whatever came
next in the stack while `janso-ui.css` applied `letter-spacing: -0.006em` and
`font-feature-settings: 'cv11' 1, 'ss03' 1` — tracking calibrated for Inter, and OpenType
features that do nothing in a face without them.

Inter Variable is now self-hosted in `@janso/ui/styles/fonts.css` and imported by both apps
(decision 82). Self-hosted because this is on-premise software: an installation with no route
to a font host must not fall back, and a third-party request per page load is a privacy detail
nobody asked for. One variable woff2, 344KB, covers 100–900. Verified served: the `@font-face`
is emitted and `/_next/static/media/InterVariable.*.woff2` returns 352,240 bytes as
`font/woff2`.

### 11. Smaller things, fixed in passing

- The review summary gave a label a third of the card, putting 260px between every label and
  its own value, eleven times. The label column is sized to a label now.
- The preview strip fitted four pairs on a row and ran them together; two to three now.
- Groups had the same gap above them as between their own fields, so a heading read as another
  row. Groups now get more air than their contents.
- The checked state of a `ChoiceCard` was carried by `--janso-brand-line`, which measures
  1.38:1 on a card. A boundary that carries a state owes 3:1 (WCAG 1.4.11), so it is
  `--janso-brand`; the contrast suite caught it.
- Seven new colour pairings added to the contrast table, measured in all three palettes.
- `Intl.supportedValuesOf('timeZone')` reports `Asia/Calcutta` on this runtime, not the
  canonical `Asia/Kolkata` the country default uses — so the suggestion list omitted the value
  already in the field. The runtime list and a canonical list are merged.

## Verification

| Check | Result |
|---|---|
| `@janso/ui` | 2049 pass, 69 files |
| `apps/console` | 3214 pass, 202 files |
| `apps/auth` | 151 pass, 15 files |
| `pnpm -r typecheck` | clean across all three packages |
| Contrast, token parity, class coverage | green in all three palettes |

New tests: `packages/ui/tests/field-structure.test.tsx` (13) and
`apps/console/tests/company-presentation.test.tsx` (15).

Two existing wizard tests were updated, both deliberately and both noted in the test: they
asserted the prose of the three step-6 notices, and that prose is now a list. The property each
checked — whether the review step says the books are included or handed off — is asserted on
the new line instead.

## Second pass — 2026-10-27

Reported from the running console: controls hidden with no way to scroll to them, and
"Incorporation date" not sharing a row with the control beside it. Both reproduced, both
measured, both fixed in `@janso/ui` — they are design-system defects, not wizard ones, so every
console form and every `WizardLayout` route carried them.

**1. The page could not be scrolled.** `apps/console/app/globals.css` sets
`body { overflow: hidden }` so the shell's `main` owns the only scrollbar. `/companies/new`
renders no shell, and that rule still applies: `overflow: hidden` on the body propagates to the
viewport, which does *not* clip the content and does *not* block `scrollTo`. So the document was
its full height — 1940px on the Presentation step at 1024×768 — with everything past the first
viewport unreachable by wheel, trackpad or scrollbar, while Tab moved focus into it and scrolled
it anyway. Steps 1, 2, 3, 5 and 6 all exceed a 768px viewport.

**This is also the correction to §2 above.** The first review's probe reported the page
scrollable and the occlusion "real, worth fixing, not *content is unreachable*". It scrolled
with `window.scrollTo`, which keeps working under a viewport-level `overflow: hidden` — so the
probe measured a page no user could have scrolled and recorded that it scrolled fine. The fix is
that `.janso-setup` is now its own scroll container, as `.janso-shell` already was, rather than
trusting a host app's `body` (design-system §4.4, decision 85).

**2. A `FieldPair`'s second field sat 16px low.** `.janso-field + .janso-field` carries
`margin-top: space-4` for a stacked column; in a grid the gap already does that, so the margin
was additive and offset the second field of every pair — measured at exactly 16px on all four
pairs of step 5 and on step 1's. Inside `FieldGroup` the same margin doubled a 16px gap to 32px,
which is why the groups looked loosely spaced. `.janso-form-grid` was given this reset when it
was written; the two containers added for this wizard were not (decision 86).

**3. The company code is no longer asked for.** It was a required field on step 1, and the
operator has no way to know what is already taken inside the tenant: a typed code either
duplicates an existing one or is unique by luck. It is now generated as the legal name's stem plus a four-character
random suffix from an alphabet with no `I`, `O`, `0` or `1`, since the value gets read off a
printed invoice (`companyCode` in `app/lib/company-defaults.ts`; `ACME-FGKQ` from "Acme
Manufacturing Private Limited", inside `VARCHAR(20)`).

Generated is not hidden: the review step shows it on its own row, with the fact that it prints
in document numbers and freezes on the first posting, and with no Edit link because there is no
field to send a reader to. It stays editable afterwards in the company settings editor, which
renders from the field set and is where the ratchet applies.

A refused code draws a fresh suffix and retries, bounded at three attempts. **Only a conflict
that names `code`** — the review below caught this: `POST /v1/companies` has a second 409, an
unseeded system-role catalogue, and under the generic conflict envelope the two read
identically, so retrying on the status alone fired three creates and changed the code twice
before showing a message that was already final on the first attempt. Identity now pre-checks
the code and returns `fields: {"code": "already in use"}`, and that is what the retry tests
(docs/company.md §4.1). Nothing is created on a 409 either way, so no attempt can leave a
company behind.

**4. "What you track" arrives with the ordinary capabilities selected.** Seven flat checkboxes,
all off, in front of someone who has not yet seen the product. The defaults come from the
jurisdiction profile — `JurisdictionProfile.default_features`, carried per country by
`GET /v1/reference/countries` — because a list in this client would be a fourth opinion about
what a company in India does ([company-features.md](company-features.md) §3). India suggests
stock, credit limits and e-way bills; the UK the first two. `e_invoicing` is offered unselected:
it begins at a turnover threshold and needs IRP credentials nobody has at creation time.

Nothing is seeded — each suggestion is still enabled by its own call with its own audit event,
and the step says "What most businesses in India use is already selected — clear anything this
one does not do." Changing the country re-suggests until the operator touches the step; after
that their selection stands, minus anything the new jurisdiction cannot offer. That last part
fixed a real defect found while building this: `e_waybill` chosen under GST and carried into a
UK company was a 422 from the enable call at the end of the run, *after* the company existed.

**Not a defect: only two countries are offered.** Reported alongside the above. The wizard lists
only `jurisdiction_supported` countries, and `JURISDICTION_PROFILES` holds exactly `IN` and `GB`
— deliberately, and the module says why: a third profile means writing a jurisdiction's statutory
identifiers, their patterns and its licence gates down, which is a research task with a reviewer.
A wrong pattern rejects a valid identifier at the boundary and a missing licence kind fails a
posting gate open, and `profile()` refuses an unsupported country at creation rather than
accepting one with an empty profile — a company that could be created and could never post. The
country field already says "Only supported tax jurisdictions are listed." Adding a jurisdiction
is a decision with a research task behind it, not a fix.

Verified in Chrome at 1440×900, 1280×720, 1024×768, 820×900 and 640×820 on all six steps: the
scroller is `.janso-setup`, every control becomes fully visible above the pinned bar somewhere in
the scroll range, the bar is on screen at the top and bottom of the range, and every pair reports
a 0px top delta — collapsing to one column at 640px as intended. Probe:
`.tools/ui-review-runner/companies-new-check.mjs`; the markup it measures is written by a
temporary vitest probe against the real component.

### What the review pass caught

Run over this change's own diff (CLAUDE.md §2). Seven findings; five were in this work and are
fixed, two belong to concurrent work and were handed back.

1. **The retry fired on any 409**, not just a taken code — the root fix is the named conflict
   above, and the client now tests `fields.code`. Found by reasoning about the route's *other*
   409; confirmed the hard way when the new identity test hit exactly that message, because the
   fixture had not seeded system roles.
2. **`useRef(codeSuffix())` evaluated on every render.** The argument to `useRef` is computed
   and discarded each render, so `crypto.getRandomValues` ran on every keystroke in the form —
   and ran *during render*, so a host without WebCrypto would have thrown while rendering
   rather than where a code is asked for. The ref is filled on first use.
3. **The "already selected" notice was driven by the jurisdiction, not the selection**, so
   clearing every card left the step still claiming things were selected. It now reads the
   intersection of the selection with the suggestion — the sentence is the only thing on that
   step that says who chose.
4. **Two filters disagreed about the tax system.** `suggestFeatures` resolved it from the
   country while the cards read `draft.default_tax_system`. Harmless with one system per
   jurisdiction, and silently wrong with two: every tax-gated default would be filtered out
   and never pre-selected. One `soleTaxSystem` helper now feeds the draft and the suggestion,
   and choosing a tax system re-suggests — so a gated default is never selected while its card
   is hidden, nor missing once the card is there.
5. **The profile validator did not enforce the ordering its API comment promised.**
   `("e_waybill", "inventory")` booted clean. It now checks each key's `requires` against what
   *precedes* it.

Handed back, not touched: the nav consolidation to the `/masters` hub left
`units-identifiers-pages` and `warehouse-structure-pages` asserting links that no longer exist,
and widening `canConfigureFeatures` to `company.create || company.update` made the "needs
tenant-level company.update" notice unreachable for anyone who can finish the wizard — it now
names a permission the only actors who could see it do not lack.

**One artifact of that method, for anyone repeating it.** A `<select>`'s chosen value does not
survive an `innerHTML` dump — React sets the DOM property, and only a `selected` *attribute*
serializes — so in a static harness every select without a placeholder option displays its
first one. The Money step screenshots therefore read "January" where the live draft holds
April. The review step, which renders computed text rather than controls, shows the real value
("FY2026-2027 · 01-04-2026 → 31-03-2027"). Box geometry and scrolling, which is what was being
measured, are unaffected.

## Still open

Decision amendment 2026-10-27: selecting the current country again preserves its
state choices and selected state. Resetting choices is reserved for an actual
country change; otherwise the country-dependent reload does not run. Regression
and live browser checks passed. The fresh tenant3 company creation outcome and
remaining Catalog deployment blocker are recorded in
[company-owner-access.md](company-owner-access.md#fresh-tenant3-company-verification-2026-10-27).

Decision amendment 2026-10-27: once all company setup writes finish, the wizard
temporarily releases its own unsaved-change guard for the final company-context
handoff. Other editors retain their guards. A refused handoff stays retryable
without recreating the company or repeating completed bootstrap steps.

- **`GET /v1/reference/countries` should return tax-system labels**, not bare codes (§3 above).
  The client-side map is a stopgap.
- **Inter's italics are not loaded.** A second 344KB file, and nothing in this interface uses
  real italics; the browser's synthesised oblique covers the rare `<em>`. Add the file when
  something needs it.
- **`next lint` is not configured** in this repo — it prompts to set ESLint up — so there is no
  lint gate on any of this. Out of scope here, worth a decision.

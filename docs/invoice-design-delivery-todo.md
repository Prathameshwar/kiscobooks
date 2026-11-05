# Invoice Designer — service/UI delivery checklist

The live checklist for making the designer **work end to end**.
[invoice-design.md](invoice-design.md) governs the service and its contract;
[invoice-design-ui-todo.md](invoice-design-ui-todo.md) tracked the eight phases of front-end
build that preceded this. This file tracks closing the gap between them.

**Starting position (2026-10-27).** Both halves existed and neither called the other. The
service had 8 migrations, ~23 endpoints, 11 `design.*` permission keys and 133 passing tests,
all at canvas `1.0.0`. The front end had all eight UI phases delivered against **static
fixtures** — zero HTTP calls — on a client-side model it called `1.1.0`. `design` was not in
the console's service map, had no request policy and no proxy route; `design.d.ts` was
generated and imported nowhere. The split was deliberate and logged (invoice-design.md §10,
*"The front end leads the canvas schema, and says so"*).

| Phase | Scope | State |
|---|---|---|
| D1 | **Transport** — service map, gateway origin, request allowlist, request helper, response verifiers | **done** |
| D2 | **Canvas 1.1.0** — ratify the proposal, freeze 1.0.0, page-geometry single source of truth, validation | **done** |
| D3 | **Read path** — gallery and editor on real templates and versions; snake/camel boundary mapper | **done** |
| D4 | **Write path** — create a template, save a version, publish one | **done** |
| D5 | **Assignments** — voucher-kind → template routing and resolution preview | **done** |
| D6 | **Reachability** — rail and command-palette entry, gated `design.template.read` | **done** (`app/nav.tsx`, `tests/design-navigation.test.tsx`) |
| D7 | **Review** — `/simplify`, `/security-review`, §5/§6 walk, fixes | todo |
| D8 | **Voucher print** — a card per voucher kind; prints on the standard layout until customized in one step; rules under Advanced | **done** (console; the service's standard-layout fallback is not built — see D8) |
| — | Renderer, object storage, ZPL/ESC_POS, template export/import, localisation | **blocked** — open questions §9.1–§9.6 |

---

## D1 — transport (done)

| Change | Where |
|---|---|
| `design` in the `Service` union and origin map | `app/lib/services.ts` |
| `DESIGN_GATEWAY_URL=http://127.0.0.1:8090/design` | `.env.local` (hand-maintained; nginx `/design/` and port 8014 were already configured) |
| Closed allowlist over all 23 endpoints — method, path, every query key and bound | `app/lib/design-request-policy.ts` |
| Dispatch, so an unrecognised design path is refused there rather than judged by catalog's rules | `app/lib/product-request-policy.ts` |
| `designRequest`, `designBase`, `assertDesignRow`, `assertDesignVersion` | `app/lib/design-api.ts` |
| 28 tests | `tests/design-policy.test.ts` |

Two deliberate narrowings beyond "what the API exposes", both tested:

- **`POST /renders` is excluded.** Recording that a document was printed belongs to the
  renderer under `design.render.record`; a browser asserting it is evidence of nothing, and
  print evidence is what a reprint gets verified against. The console reads that history and
  never writes it.
- **`assertDesignRow` accepts a tenant-wide row** (the shared house style carries no company
  of its own) but rejects a reply for a *different* company. That arrives in practice, because
  the company is switchable from the rail, and painting it would show one company's template
  under another's name.

Also established: **`design` needs no Identity projection.** It authorizes from the signed
actor context plus the row's own `company_id`, so wiring it cannot hit the
`503 source_unavailable` class of failure that the catalog masters hit. That de-risks D3–D5.

## D2 — canvas 1.1.0 (done)

Ratified, closing open question §9.3. See the decision log in
[invoice-design.md](invoice-design.md) for the three decisions this phase made.

**1.0.0 is frozen, by a discriminated union rather than by widening.** `CanvasV10` keeps its
exact shape and `CanvasV11` sits beside it, discriminated on `schema_version`; `CANVAS` is the
`TypeAdapter` that parses either. A version row stores its tree verbatim with a `layout_digest`
over those exact bytes (§4.3), so widening the old model would re-validate every stored layout
against a different shape, and normalising one on read would change its digest and silently
invalidate a published document's print evidence. **1.0.0 is frozen in behaviour too**: the new
page-fit rule applies only to 1.1.0, because a stored version is re-read on every resolve and a
new rejection on the old shape would break reprints, not just new saves.

What 1.1.0 adds, all typed fields and no open map:

| Added | Notes |
|---|---|
| `print_options` | `copies` (4 GST copy marks, distinct, at least one), `copy_mark_position`, `pre_printed_stationery` |
| `ItemColumn` | 19-key closed vocabulary, `width_mm`, `align`, `show`, optional heading override |
| `RowOptions` | `description_under_item`, `zebra`, `repeat_header`, `blank_rows` |
| `totals_rows` | 11-row vocabulary, distinct, at least one |
| `tax_grouping`, `show_cess` | `TAX_SUMMARY` only |
| `TOTALS_BLOCK` element | 1.0.0 had no way to say "print the totals here" except as free text |
| Section box + `free_placement` | 1.0.0 carried an optional `height` and no position, so a zone had no geometry to hit-test |

New rules, each with a reason it exists:

- **Visible column widths may not exceed their table.** This is the 204mm-in-a-190mm-table
  error the front end found by printing a real invoice; on paper it is a clipped last column,
  discovered at the worst possible moment. Hidden columns stop counting, and exactly filling
  the table is allowed.
- **An option is refused on a type that cannot act on it.** `totals_rows` on a `DIVIDER` is the
  same problem as an open map, reached by a different route: the layout's meaning would depend
  on which fields the renderer happens to read.
- **Section and element ids are unique across the tree.** The editor addresses selection, undo
  and z-order by id; a renderer resolving a duplicate takes whichever it saw last.
- **Nothing may be bigger than its paper** (`assert_layout_fits`). It needs the template *row*,
  because 1.1.0 took paper size out of the tree. Crowding a margin stays a **warning** — the
  editor lists warnings at publication where a person can decide, which is not a decision a 422
  can make for them. Continuous roll stock has no length to overflow, only a width.

Evidence: 143 tests pass (`test_canvas_v11.py` 20, `test_page_fit.py` 10, the rest unchanged).
Ruff and mypy strict clean. `openapi.json` and `design.d.ts` regenerated; `@janso/api-client`
0.2.33.

## Open questions this work must not answer silently

These stay open and nothing here assumes an answer (invoice-design.md §9):

1. **The renderer** (§9.1) — nothing compiles a layout into a document. Until it exists the
   designer persists, versions, assigns and resolves templates and **prints nothing**. Adding
   a renderer is a new component, which CLAUDE.md gates behind an explicit decision.
2. **Object storage** (§9.2) — asset registration records metadata and derives a path; no bytes
   are uploaded or served. Downloads must be signed and expiring when it lands (CLAUDE.md §5.14).
3. **ZPL / ESC_POS** (§9.4) — untouched. Millimetre geometry is proven workable for roll stock;
   line-mode command streams are the half still open.
4. **Template export/import** (§9.5) and **localisation of static text** (§9.6).
5. **System templates** (§9.7) — `is_system` exists, no shipped designs are seeded.

## D3 — read path (done)

The gallery and the editor now open what the service holds. `TemplateGallery` and
`DesignerShell` kept their signatures — eight phases of editor behaviour are untouched, which
is what the UI-first ordering was betting on. What changed is where the data comes from.

| Change | Where |
|---|---|
| Service ⇄ editor canvas boundary, both directions | `app/lib/design-canvas.ts` |
| `useDesignTemplates`, `useDesignTemplate` | `app/lib/design-templates.ts` |
| Client route components, with loading/denied/empty states | `(editor)/invoice-designer/DesignGalleryRoute.tsx`, `DesignerRoute.tsx` |
| Request-scoped pages: session, company and `design.template.read` resolved server-side | `(editor)/invoice-designer/page.tsx`, `[templateId]/page.tsx` |
| 38 tests | `tests/design-canvas.test.ts` (23), `tests/design-read.test.tsx` (15) |

**The boundary is hand-written and type-checked, not a generic key converter.** Three kinds of
difference sit between the two models and only one is mechanical: case (snake vs camel), unit in
the name (`x` vs `xMm` — the editor spells geometry with its unit because a prop called `x` is
the one that eventually gets multiplied by a zoom factor and silently becomes pixels), and
*ownership* (paper size and orientation belong to the row, so `toEditor` takes the row and
`toWire` deliberately drops them). A converter would have handled the first and silently
mangled the others.

**Round-tripping is the contract**, because the service digests the serialised tree: if the
boundary nudged a layout, every save of an untouched template would mint a revision nobody made.
The test asserts **idempotence** rather than raw equality — one pass is allowed to drop something
meaningless and does (several sample elements carry `style: {}`, an empty object that says
nothing), but a second pass must change nothing. Writing that test immediately found two real
bugs: `prePrintedStationery: false` and `freePlacement: false` were being collapsed to absent
keys by a truthiness check, which is a different document.

Two states no fixture could produce, now handled: a **draft with no version at all** opens on an
empty page in two requests rather than three, and a layout stored on the **frozen 1.0.0 shape**
is read-only with a reason — it prints and its history is intact, but it cannot express a column
set, a totals block or a zone box, so editing it would mean inventing geometry and saving the
invention back as the author's choice. Shipped `is_system` designs are read-only by domain rule.

Two §5 details worth recording: a cross-company row is rejected **for every item in a list**,
not just a detail — the list is what the gallery links from, and the company is switchable from
the rail, so a stale reply arrives in practice. And a 404 is rendered as a **403**: "not yours"
and "gone" must not be distinguishable, or the 404 becomes an existence oracle (CLAUDE.md §5.2).

`useServiceList` is deliberately not used: it appends `sort=-id` to every query and the design
service takes no `sort` — its lists are keyset-ordered newest-first by construction. Borrowing
it would have meant widening the console's allowlist to carry a parameter nothing honours.

## D4 — write path (done)

| Change | Where |
|---|---|
| `useDesignWrites` (save a version, publish one), `useTemplateWrites` (create) | `app/lib/design-commands.ts` |
| An optional `persistence` port on the editor, plus `readOnlyReason` | `(editor)/invoice-designer/DesignerShell.tsx` |
| A **Save draft** action beside Publish, and a `busy` state for both | `(editor)/invoice-designer/VersionPanel.tsx` |
| Create form: name, code, paper, orientation, custom size | `(editor)/invoice-designer/NewTemplateDialog.tsx` |
| 12 tests | `tests/design-write.test.tsx` |

**Saving and publishing stay two requests, in that order.** The service appends an immutable
version and then, separately, makes one of them the layout every future document prints on.
Collapsing them would make every intermediate save live, which is the one thing the version
model exists to prevent. The publish step names **the id it just created**, never "the newest":
two people publishing at once must not make one of them live the other's version — and the
response is verified to confirm that exact version as `current_version_id`, because telling
someone their layout is what customers receive when it is not is the worst available outcome.

**`persistence` is an optional port**, which is why eight phases of editor behaviour and their
four suites are untouched. Absent, the editor publishes into local state exactly as it did
against the fixtures. Present, it writes to the service. The footer's "nothing is saved yet" was
honest against fixtures and would have become a lie, so it now reads differently when there is
somewhere to save to.

One real bug the tests caught, worth recording because the shape of it recurs: the dialog was
copying `persistence.failure` into local state *inside an async callback*, which read the value
captured when the callback was created — so the service's actual reason was replaced by a
generic fallback. The dialog now renders the live failure. A failed save never closes the dialog
and never discards the typed summary; a closed dialog over an unsaved layout is how work is lost.

A 5xx leaves the command **uncertain** rather than failed, and the retry is the identical
request under the identical idempotency key. A design write is not money, so the service does
not require a key — but "the save may or may not have landed" is exactly as bad for a layout as
for a payment.

A reader holding `design.template.read` without `manage` opens the design **read-only** rather
than being refused: looking at a layout is a legitimate thing to be allowed to do, and the
service rejects the write regardless.

## D5 — document routing (done)

The missing half of the designer. A tenant could author a template and had no way to say *when*
it is used; the service has had the whole surface all along.

| Change | Where |
|---|---|
| `useRoutingRules`, `useRoutingWrites`, `useRoutePreview`, `ruleConditions` | `app/lib/design-routing.ts` |
| The voucher-kind vocabulary (moved out of `design-routing.ts` in D8, and completed to 22 kinds) | `app/lib/voucher-kinds.ts` |
| Rules in force, add a rule, and check a document | `app/components/DocumentRouting.tsx` |
| Page inside the ordinary console shell | `app/documents/routing/page.tsx` |
| 17 tests | `tests/design-routing.test.tsx` |

Three decisions on this screen:

- **Only a published template may be routed to.** A rule pointing at a draft resolves to
  nothing, which is a rule that silently does not work — so drafts are absent from the picker,
  and a company with nothing published is told why rather than shown an empty select.
- **Retired rules stay visible.** A rule is deactivated, never deleted. Hiding the retired ones
  makes "why is it still printing the old design?" unanswerable on the screen that owns the
  answer.
- **Check a document asks `POST /resolve`** — the same question the renderer will ask. A rule
  set that looks right and resolves wrong is the failure this screen exists to prevent, and the
  only honest test is to ask the thing that will be asked. `assignment_rule_id: null` is
  surfaced as its own outcome, because *configured* and *defaulted* are different facts and the
  second one stops working the moment there are two published templates.

Blank conditions are omitted rather than sent as `""`: absent and null are the same rule to the
service, and an empty string is a 422 on a field nobody touched. The probe's inputs were renamed
(`Document currency`, `Document tax category`) because a condition on a rule and a fact about a
document are different questions, and two inputs sharing an accessible name makes the screen
unusable for anyone navigating by label — a test now asserts no two share one.

## D8 — voucher print (done)

D5 answers "which template does a *kind* print on" from the rules' side; nobody starts there. A
person has *a sales invoice* or *a receipt* in mind. D8 starts from the voucher: a card for every
kind, and behind each card that kind's print.

| Change | Where |
|---|---|
| Rail entry **Document templates → Print templates**, with **Voucher print** and **Document routing (advanced)** beneath | `app/nav.tsx` |
| The 22-kind vocabulary, its four families, the URL segment and the voucher-type address (server-safe, not a client module) | `app/lib/voucher-kinds.ts` |
| `useRoutingRules(company, kind?)` with `hasMore`; `ruleConditions` and `isDefaultRule` shared with the routing page; `useDesignTemplates` gains `hasMore` | `app/lib/design-routing.ts`, `app/lib/design-templates.ts` |
| A card per voucher kind, with **Standard layout** or **Custom layout** | `app/components/VoucherPrintHub.tsx`, `app/documents/vouchers/page.tsx` |
| One kind's print: the layout in use, **Customize layout**, **Back to standard layout**, **Manage voucher type**; the rules, the picker of existing templates and the table under **Advanced** | `app/components/VoucherPrintKind.tsx`, `app/documents/vouchers/[kind]/page.tsx` |
| The new-template form takes a `note`, a `title` and an `onCreated` follow-up; if the follow-up fails the template is kept and offered | `(editor)/invoice-designer/NewTemplateDialog.tsx` |
| `ActionCard` `status` — a state chip beside the icon (`@janso/ui` 0.1.39) | `packages/ui/src/components/ActionCard.tsx` |
| Tests | `voucher-kinds`, `design-routing-rules`, `voucher-print-hub`, `voucher-print-kind`, `voucher-print-pages`, `new-template-dialog`, `design-navigation`, `design-routing`, `design-routing-layout`, `action-card` |

Decisions:

- **The cards are the vouchers service's 22 kinds, not the 16 the routing select carried.**
  `SALES_ORDER`, `PURCHASE_ORDER`, `JOB_WORK_IN_ORDER`, `JOB_WORK_OUT_ORDER`, `MEMORANDUM` and
  `REVERSING_JOURNAL` had no card and no routing option, so those documents could not be given a
  template at all. The list is still restated rather than fetched; a test now reads
  `vouchers/domain/registry.py` and fails if the two drift. Grouped by the four families of
  [vouchers-plan](vouchers-plan.md) §2.1–2.4, so a card can be followed back to its definition.
  The cards are *kinds* (`SALES`), not the company's derived voucher *types*; a rule can also be
  scoped to one type (`voucher_type_id`), which the table shows as "Specific voucher type" but the
  console cannot yet create.
- **What a voucher prints on is what the service would resolve, read by one function.** `layoutInUse`
  (`app/lib/design-routing.ts`) takes a kind's rules and the templates and answers the way
  `design` resolves: only rules **in force on a published template** count (a retired rule routes
  nothing; a rule on a draft is skipped and the next candidate applies); an ordinary document can
  only match a **default** rule; and the first by `compareRules` — **priority, then how many
  criteria are pinned, then the newer rule, then the larger id** (`resolution.py` `_candidates`) —
  wins, *whoever owns it*. So a default set for the whole organisation can outrank the company's
  own, and the page says so instead of showing the company's rule as "in use". The first pass
  trusted the company's own default and was wrong exactly there. The voucher's page and the cards
  page both ask this function, so they cannot disagree (the first pass counted any rule on a
  published template as "Custom layout", so a USD-only rule made the card say custom and the page
  say standard).
- **A card's chip says Standard layout, Custom layout, or Custom for some documents, and is a
  courtesy, not a gate.** *Custom layout*: a default rule in force names a published template.
  *Custom for some documents*: only rules for a currency, tax category, voucher type or branch are
  in force. Without `design.assignment.read` every card still opens, just without the chip. When
  either list runs past one page the chips are withheld with a note, never guessed.
- **Customize writes the new rule at the winning default's priority (at least 100).** A rule
  written at 100 under an organisation default at 300 would never apply; at the same priority the
  later rule wins, so equal priority is enough. The dialog's note says what is printing *now*, which
  is the organisation's layout rather than the standard one when there is one.
- **Reinstate is withheld while an identical rule is in force.** `create_assignment` refuses a
  duplicate active rule, but switching a retired rule back on (`PATCH is_active`) does not make that
  check, so the Console would otherwise have let two defaults be active and *Back to standard
  layout* retire only one. **Service gap, not fixed here:** `update_assignment` should refuse it with
  the same 409 (invoice-design.md §5.2 says an exactly duplicate active rule is a 409); the guard
  in the console is a courtesy, not the control.
- **Rules are named by their conditions, and a failed read can be asked again.** Two rules on one
  template (a default and a USD rule) get different accessible names ("Retire GST tax invoice, Currency
  USD"); a list that fails to read after a write that went through shows the message with *Try
  again* instead of an error page that says nothing changed.
- **A shared hook bug found on the way.** `useServiceCommand` refused a *different* write in the
  same click that `clear()`ed an uncertain one (it closed over the stale `uncertain` state), so a
  Retire after a server error did nothing, silently. `uncertain` is now also a ref; regression
  tests in `tests/product-command-retry.test.tsx`.
- **Opening the page needs `design.template.read`, like the gallery it sits under.** Knowing which
  layout is in use, and the table of rules, need `design.assignment.read`; *Customize layout* and
  *New template* need `design.template.manage`; *Back to standard layout*, *Retire*, *Reinstate* and
  *Use for …* (the picker of existing templates) need `design.assignment.manage` — and *Customize
  layout* and the picker also need read access, because they have to know whether a default is
  already in force.
- **"Use a template" means "make it the kind's default", and the service allows one at a time
  per company.** `create_assignment` refuses a second *active* rule *of the same company* with the
  same voucher type, branch, currency and tax category whichever template it names (409). So the
  picker, now under Advanced, is offered only while the company has no default **of its own**; a
  default set for the whole organisation does not collide and does not block. Any published
  template can be the default — one that only has a currency rule is a different rule. The default
  is written at priority 100 with no conditions; conditions stay on Document routing. When either
  list runs past one page, whether a default exists cannot be told, and nothing is claimed.
- **Nothing is offered on a rule the page cannot stand behind.** A rule whose template is no longer
  listed was retired *because* its template was archived (the service deactivates them together);
  reinstating one would leave an active rule that resolves nothing, so it shows as "Unknown
  template" with no action. A tenant-wide rule needs a tenant-level grant, so it gets none either.
  Retire/Reinstate buttons are named for their template.
- **Print templates, not Document templates.** The gallery heading and page title follow the
  rail label. The rail label changed; the permission and route did not.

**Known limits, and said plainly.**

- *Manage voucher type* links to `/masters/voucher-types`, the destination the Purchase invoice and
  voucher entry screens already send people to. That route had no page when this was written
  (`masterConfig('voucher-types')` is null, so the master page 404ed); the voucher type directory now
  serves it (see [voucher-extensibility](voucher-extensibility.md)). The link is offered to everyone,
  as there is no permission to test; a reader without `vouchers.read` reaches a 403 there.
- *Customize layout* creates the template **and** its default rule, which needs both
  `design.template.manage` and `design.assignment.manage` (and read, to know whether a default
  exists). An author without routing grants gets *New template* instead, and its note says someone
  with routing access must choose it. The service accepts a rule on a draft (it only checks the
  template is visible to the company) and skips it at resolve time, which is what lets Customize
  write the rule before the template is published. Publishing (`design.template.publish`) is a
  third grant, held in the designer.
- *Customize layout* opens an **empty page**, not a copy of the standard layout: no standard-layout
  canvas exists to copy (invoice-design.md §9 item 7). The page says so ("opens in the designer on an
  empty page") rather than promising a starting point it cannot give.
- The standard layout is described, not yet delivered: the service still answers a document with no
  rule from the company's most recently published template, or 404. The Console's wording follows the
  2026-10-30 decision (invoice-design.md §10); the service half, the layouts and the renderer are open.
- Reloading a list after a write empties it first, so a keyboard user loses their place in the
  table. That is how `useServiceRead` refreshes for every screen and is not changed here.
- The routing page itself still reads one page of 200 rules and offers *Reinstate* on any retired
  rule; only this page checks for the archived-template and tenant-wide cases.

# Invoice designer: production plan

Status: **AGREED 2026-11-03** with decisions D1-D3 taken (§6) and the order *P0, then the canvas
renderer (P3) early*. D4 and D5 remain open. Nothing in this plan is implemented by being written
down; §5 records what each phase delivered. It governs the work that makes the
[`design`](invoice-design.md) editor fully working for every voucher kind.

## 1. Objective

The owner's words (2026-11-03): *for a certain voucher type, depending on products or
accounts/expenses or both, the invoice designer should let you design with, and select, the
controls and tables that type needs; make the designer fully working and production ready.*

In practice that means four things a person can rely on:

1. **The designer knows what it is designing for.** A Purchase layout for a *Product* type
   offers a product table; for an *Account bill* type, an account/expense lines table; for a
   *Mixed* type, both. Fields offered are the fields that document actually has.
2. **What you see is what prints.** Every element, position, style and table option the
   designer offers prints exactly so, or the designer says before publishing that it will not.
3. **It works end to end without setup.** Choose a voucher type, customise, publish, print a
   real voucher on it; return to the standard layout at any time.
4. **It holds up in production**: tenant isolation, permissions, audit, versioning, signed
   asset delivery, accessibility, performance and tests on every path.

## 2. Where it stands (verified 2026-11-03)

| Area | Today |
|---|---|
| Editor | Rich: zones, free-positioned elements, drag/resize/snap/align, multi-select, undo, inspector, item-table columns, totals rows, copies, paper presets, versions/publish/restore, warnings. 2026-11-03: palette always has a destination, Text/Line/Box/Signature objects, drag-and-drop onto the page, Back/leave guard ([decision log](invoice-design.md#10-decision-log)). |
| What a template is for | **Nothing.** A template has no voucher kind, type or line profile; only routing rules carry `voucher_kind`/`voucher_type_id`. The palette offers one fixed list of ~50 bindings and one sales-invoice sample, whatever the template will print. |
| Line tables | One `ITEM_TABLE` (goods vocabulary: HSN, batch, qty, rate, GST columns). **No account/expense lines table**, so an Account bill or the account half of a Mixed bill has nothing to design with. |
| Renderer | Only **Purchase** prints (Chromium/Celery, private disk). A custom Purchase layout is accepted only in a narrow *A4 flow profile*: full-width (x = 0, 180 mm) sections and elements, no styles, no free placement, exactly one item table and one totals block, no table options, 11 bindings, types TEXT/FIELD_BINDING/ITEM_TABLE/TOTALS_BLOCK/DIVIDER only. Anything else is refused at print time ([purchase_print.py](../apis/vouchers/src/vouchers/domain/purchase_print.py)). |
| Consequence | Nearly every layout the editor can make — any element not full width, any style, a box, a signature, a logo — **is refused when printed**. The designer does not say so. This is the largest gap. |
| Assets | Registration records metadata only; nothing uploads or serves bytes, so logos and signature images cannot be used ([invoice-design](invoice-design.md) §9.2). |
| Standard layouts | Purchase ships `purchase-a4@N` in renderer code; other kinds have none. *Customize layout* starts from an empty page, not from the standard one (§9.7). |
| Preview | Sample data only; no "preview with a real voucher", no PDF from the designer (the Download PDF button is disabled by design). |

## 3. Gaps against the objective

- G1. Templates carry no document context, so the designer cannot tailor controls, tables,
  fields or sample data to a kind and its line profile.
- G2. No account/expense lines table; Mixed documents cannot show both.
- G3. Binding catalogue is one fixed list, not the published print facts of each kind.
- G4. Designer and renderer disagree: no shared capability contract, refusal only at print.
- G5. The renderer cannot honour the canvas (positions, styles, boxes, images, signatures,
  table options, pagination); only Purchase renders at all.
- G6. No asset upload/serve; no logo or signature images.
- G7. No real-voucher preview; no starting from the standard layout.
- G8. Assigning a layout to a voucher type happens elsewhere (Document routing); the designer
  cannot say "use this for Purchase type X" or show where a template is used.
- G9. Production hardening gaps: multi-page tables (repeat header, carry-forward), thermal,
  localisation of static text, browser-level layout tests per kind.

## 4. Target design

**4.1 Document context on the template.** A template is designed for one
`voucher_kind` and a **line profile** — `ITEMS`, `ACCOUNTS` or `MIXED` — taken from the voucher
type's allowed entry modes when the template is created from a type (*Customize layout*), and
chosen explicitly otherwise. The context decides what the palette offers, which sample
document drives the preview, and which routing rules may point at the template (a rule for a
Product type cannot select an `ACCOUNTS`-only template). Where it is stored is decision D1.

**4.2 Element catalogue per context.**

| Profile | Tables offered | Notes |
|---|---|---|
| `ITEMS` | Product table (`ITEM_TABLE`) | Columns per kind: Purchase adds received/billed quantity and input-credit; Sales adds MRP/scheme columns. |
| `ACCOUNTS` | Account lines table (new `ACCOUNT_TABLE`: account/ledger, description, amount, tax rate, tax, line total) | Expense and service bills, journals, payments/receipts. |
| `MIXED` | Both tables, or one combined lines table with a line-type column (decision D2) | Matches how the bill was entered. |

All profiles: text, line, box, signature (image when assets land), totals block, tax summary,
fields, QR/barcode. Each kind publishes which of these it renders (4.4).

**4.3 Bindings from the owner of the facts.** Vouchers publishes, per kind and version, the
print-fact catalogue it freezes for printing (header, party, addresses, tax, totals, lines,
bank, signatory), with display names, sample values and field-permission classification. Design
validates `binding_path` against the catalogue of the template's kind; the palette lists exactly
that catalogue, grouped, with realistic sample values for the line profile. Field-level read
denies keep printing "restricted" (existing behaviour), never the value.

**4.4 One capability contract.** The renderer publishes a versioned **capability manifest** per
kind: element types, options, styles, page sizes, max sections/elements, pagination support. The
designer reads it and turns every unsupported use into a *publish-blocking error* with the reason
(e.g. "Purchase printing does not support boxes yet") — the same check the renderer runs, from the
same manifest, so the editor and the printer cannot disagree again.

**4.5 A canvas renderer, not a flow renderer.** Replace the A4 flow profile with a renderer that
lays the canvas out exactly as the editor draws it: zones and elements absolutely positioned in
millimetres in Chromium HTML/CSS (the editor's own model, so parity is structural), styles,
borders, boxes, signatures and images, table columns and row options, totals rows, tax summary,
copies and marks, page sizes and thermal rolls, and **multi-page item/account tables** that grow
their zone, repeat headers and carry totals forward. Shared by every kind; each kind supplies only
its frozen facts and its manifest. The existing Purchase pipeline (frozen facts, signed resolution,
private storage, signed tickets, audit) stays as is.

**4.6 Assets.** Upload, scan and serve logo/signature bytes with content-addressed, company-scoped
keys and signed expiring downloads (CLAUDE.md §5.14), on the storage chosen in D3.

**4.7 Flow for a person.** Voucher type → *Customize layout* → the designer opens a **copy of the
standard layout** for that kind and profile → edit → *Preview with a real voucher* (server render
of a chosen saved voucher, permission-checked) → publish → the routing rule is created/updated
from the designer → *Back to standard layout* retires the rule.

## 5. Phases

Each phase ends with tests green and the repo working; services/migrations follow CLAUDE.md §2.

| Phase | Deliverable | Exit evidence |
|---|---|---|
| **P0 — Honest now** ✅ 2026-11-03 | Designer reads a static Purchase capability list (the current flow profile) and warns/blocks publish for layouts Purchase cannot print; Customize-from-type passes the kind so the warnings apply. | Console tests: each unsupported feature named; a supported layout publishes and prints in the Purchase print tests. |
| **P1 — Document context** ✅ 2026-11-03 | D1 storage of kind + line profile; create/duplicate/customize set it; routing rejects a mismatched template; palette, sample document and warnings follow the context. | Design migration + model/schema/factory/client; cross-tenant test for any new table; routing tests for mismatches; console tests per profile. |
| **P2 — Catalogues** ◐ 2026-11-03 (D2 table done for Purchase; per-kind catalogue deferred to P6) | Vouchers print-fact catalogue per kind (start Purchase, Sales); Design validates bindings per kind; `ACCOUNT_TABLE` element in canvas 1.1.0 (widened, not 1.2.0 — see decision log; D2 for Mixed); kind-specific item columns. | Contract tests; Design schema tests for the widened 1.1.0 with existing stored versions still verifying their digests; console palette tests per kind/profile. |
| **P3 — Canvas renderer** ✅ for Purchase, 2026-11-03 | Absolute-mm renderer shared by kinds; capability manifest published and consumed (replaces P0's static list); Purchase moves onto it; pagination of line tables. | Golden PDFs per sample template (A4 GST, compact, 80 mm, challan) compared page by page; real-Chromium tests; refusal tests for anything outside the manifest. |
| **P4 — Assets** ✅ images, 2026-11-03 (fonts deferred) | D3 storage; upload/scan/serve; IMAGE and SIGNATURE images in editor and renderer. | Signed-URL expiry, cross-company refusal, content-type/size limits, audit. |
| **P5 — Preview and flow** | Start from the standard layout; preview with a real voucher; assign to voucher type from the designer; where-used list. | Permission and wrong-company tests on preview; end-to-end browser test: type → customize → preview → publish → print. |
| **P6 — More kinds** | Sales, Credit/Debit note, Receipt/Payment, Delivery challan (order per D4): catalogue + manifest + standard layout each. | Per kind: print tests, standard layout fallback, routing. |
| **P7 — Hardening** | Thermal/58 mm, localisation of static text (D5), performance budgets (200-line bills), accessibility audit, browser layout suites for every kind, operational runbook. | Suites green; review per CLAUDE.md §5/§6; docs and decision logs updated. |

### Delivered

- **P0, 2026-11-03.** `print-capabilities.ts` mirrors the Purchase renderer's flow-profile check
  on the stored wire. A template that an active Purchase routing rule points at shows each
  feature Purchase cannot print as a publish-blocking error naming what to change (boxes,
  signatures, styles, anything not full width, unsupported fields, marked copies, margins, paper,
  a missing or second table/totals block). Templates no Purchase rule prints on are not judged.
  Console tests `designer-print-capabilities.test.tsx` and the route cases in
  `design-write.test.tsx`. Known limits until P1/P3: a reader without routing read access gets
  no check (printing still refuses with its reason), and choosing a template for a rule on the
  routing page does not warn yet.
- **P3 for Purchase, 2026-11-03.** The A4 flow profile is replaced by a canvas renderer
  (`apis/vouchers/src/vouchers/domain/canvas_print.py`, `purchase-pdf@3`): zones and elements print
  at their millimetres on the template's paper (A4, A5, Letter, custom; portrait or landscape) and
  margins, with typed styles re-checked (colours, fonts, numbers, vocabularies) and every value
  escaped. Text, fields, lines, boxes, signatures, the item table (chosen columns, headings,
  alignment, zebra, blank rows, repeated header), totals rows and the tax summary by rate print;
  copies with marks and pre-printed stationery are honoured. The band holding the line table grows
  across pages and pushes the bands below it down. One manifest per kind
  (`domain/print_capabilities.py`, contract `apis/vouchers/contracts/print-capabilities-v1.json`) is
  checked by the renderer before any browser starts and published at `GET /print-capabilities`; the
  designer reads it (replacing P0's fixed list) and blocks publishing with the same sentences.
  Rendered through the real pipeline locally with Chromium (Edge). Not yet printable, and named
  as such: images and logos (P4), QR codes and barcodes (no encoder), HSN/quantity/rate/unit/batch
  columns and amount in words (goods bills and P2 facts), thermal rolls, shared components.
  Tests: Vouchers `test_canvas_print.py` (23) and the updated print suites; Console
  `designer-print-capabilities.test.tsx`, route and proxy-policy cases.
- **Interaction fixes, 2026-11-03** (before P0): palette destination fallback, Text/Line/Box/
  Signature objects, drag-and-drop, keyboard field list, Back and leave guard
  ([decision log](invoice-design.md#10-decision-log)). Boxes and signatures are offered because
  the plan's renderer prints them; until P3, P0 blocks publishing them for Purchase.
- **P1, 2026-11-03.** A template records what it is for (D1): `voucher_kind` and `line_profile`
  columns on `invoice_template` (migration `0009`, one `ALTER`, both nullable so an unstated
  template stays routable by any kind). A line profile requires its kind; a routing rule cannot
  name a template designed for another kind (`422`, same wording the service already uses);
  resolution never falls back across kinds; a design is not re-purposed while active rules still
  print the old kind on it (`409`) — naming the kind its rules already print is not a change.
  Listing by kind returns that kind's designs plus unstated ones. *Customize layout* passes the
  type's kind and starting line profile (money-only kinds — Receipt, Payment, Contra, Journal —
  start `ACCOUNTS`; others start `ITEMS`); a plain "New template" lets the author choose "Any
  voucher" or a kind, then its lines. The gallery and the designer's title bar show what a design
  is for ("Purchase · Products and accounts"); a design whose kind cannot be printed from a
  design yet says so instead of running print checks against nothing. Tests: Design
  `test_template_context.py` (8); Console `design-write.test.tsx`, `design-read.test.tsx` route
  cases and `TemplateGallery`/`NewTemplateDialog` coverage.
- **P2 (D2) for Purchase, 2026-11-03.** Canvas `1.1.0` gains `ACCOUNT_TABLE` beside `ITEM_TABLE`
  (widened, not a new schema version — every stored `1.1.0` layout and its digest are unchanged)
  with its own column (`account`, the ledger a line posts to) and its own default set. A `MIXED`
  design gets **two tables** (D2): a product table and an accounts table, each in its own zone;
  the renderer splits a bill's lines between them by `supply_kind` and prints each table's lines
  in the table alone, present only if a layout carries both. An `ITEMS`- or `ACCOUNTS`-only
  design offers only its own table in *Add to the page*; a design that never said offers both.
  The manifest's single table limit becomes a per-table-type limit (`line_tables.max_each`), so a
  design can carry one product table, one accounts table, or one of each, never two of the same
  or two in one zone. Not yet exercised with real goods/account lines together — that needs
  product-bill printing (blocked on P2's facts work below) and mixed-bill printing, both still
  refused by Purchase's own guard. Tests: Design `test_canvas_v11.py` additions (accounts-table
  option validation); Vouchers `test_canvas_print.py` (+3: accounts table, split lines, two
  tables in one zone refused); Console `invoice-designer-line-tables.test.tsx` (9).
  **Not done in P2**: Vouchers' per-kind print-fact catalogue beyond Purchase's existing facts,
  and kind-specific item columns for kinds other than Purchase — both wait for a second kind
  (P6) to avoid designing the catalogue against one example.
- **P4 (D3) images, 2026-11-03.** `design`'s own content-addressed private-disk store (D3):
  `POST /assets` decodes and signature-sniffs the upload (PNG/JPEG/WebP only — SVG stays refused,
  it is markup), atomically writes it, then stores the row; `GET /assets/{id}/download` takes a
  short-lived (120s) signed, actor-and-asset-bound token minted by the list/detail read, never a
  public path (§5.14). A font upload is explicitly refused with its reason, not silently accepted
  and mishandled — fonts stay open. Console: a dedicated `POST /api/design-asset-upload` route
  carries the base64 body past the shared proxy's small ceiling (same reason `purchase-files` has
  its own route); a dedicated `GET /api/design-asset` route streams the download for `<img src>`
  (same reason `report-download` has its own route) with `Cache-Control: private, no-store`, a
  sandboxed CSP and no bearer token reaching the browser. `SelectionInspector`'s `IMAGE` and
  `SIGNATURE` elements gained an asset picker (choose a saved asset, or upload one) wherever a
  real `company` is open; `DocumentLayer` resolves a real `assetId` through the proxy route and
  falls back to its existing empty state everywhere a company is not open (every fixture-only
  test, unchanged). The asset list — and the download tokens on it — refreshes every 60s while
  the designer is open, so a long session never shows a token past its own expiry. Tests: Design
  `test_assets_components.py` (21, rewritten for the upload/download shape), `test_isolation_and_audit.py`
  (tenant isolation for the new storage path); Console `design-asset-upload-policy.test.ts` (11),
  `design-asset-download.test.ts` (12), `design-assets.test.ts` (7), `asset-picker.test.tsx` (5),
  `designer-asset-wiring.test.tsx` (2), plus two `DocumentLayer` cases in `invoice-designer.test.tsx`.
  **Not done in P4**: font assets (upload refuses them with a stated reason); PDF embedding of an
  uploaded asset, which is the renderer's job and unblocked by this storage existing.

## 6. Decisions

Taken by the owner on 2026-11-03: **D1 template columns**, **D2 two tables**, **D3 private VM
disk**, and order **P0 first, then P3 early** (before P1/P2 where P3 does not depend on them).
On 2026-11-04 the owner answered **D5: one language per template**, and set D4 aside: *Purchase
is the base and is made production ready first*; the order of the other kinds (P6) is decided
when that work starts. See §8.

- **D1. Where the document context lives**: columns on `invoice_template` (`voucher_kind`,
  `line_profile`; migration, filterable in the gallery) — *recommended* — or a `document` block in
  canvas `1.2.0` (no migration, but not queryable and versioned with every save).
- **D2. Mixed documents**: two tables (products, then accounts) — *recommended, matches entry* — or
  one combined table with a line-type column.
- **D3. Asset storage**: the same private VM disk as Purchase PDFs (*recommended for now*), or an
  object store.
- **D4. Kind order after Purchase**: proposed Sales → Credit/Debit note → Receipt/Payment →
  Delivery challan.
- **D5. Static text localisation** — **decided 2026-11-04: one language per template.** An
  element's text prints exactly as typed, in whatever script; a company needing two languages
  keeps two templates. Content keys resolved at print were not chosen.

## 7. Risks

- Renderer parity is the critical path: until P3, custom layouts beyond the flow profile cannot
  print, and P0 must say so plainly rather than let a published layout fail at print.
- Canvas `1.2.0` must leave stored `1.0.0`/`1.1.0` versions and their digests untouched
  ([invoice-design](invoice-design.md) §4.3).
- Field permissions must hold in previews and PDFs exactly as on screen (CLAUDE.md §6.15).

## 8. Purchase production readiness (agreed 2026-11-04)

The owner's words: *we will proceed with Purchase ... make it production ready at least for
Purchase as base.* Purchase is the only kind this section makes printable from a design; the
other kinds stay P6. Each phase ends with its suites green.

| Phase | Delivers | Exit evidence |
|---|---|---|
| **R1 — Goods on the print** | Product and Mixed Purchase bills print (the B24 bill shape, `goods_bill`); the print preview sends the bill's stock lines like calculation does. Each goods line prints its quantity, unit, rate and HSN/SAC; a bill prints its amount in words. Accounting answers HSN/SAC (preview: the calculation's tax evidence; posted: the posted supply fact) and the unit's label from Catalog's own facts, under the actor's rights. The standard layout prints goods columns when a bill has goods. | Vouchers/Accounting/Catalog tests: goods/mixed snapshot, withheld labels, posted vs preview HSN, refusal of a malformed goods bill; amount-in-words unit tests; manifest columns. |
| **R2 — Images in the PDF** | `IMAGE` and image `SIGNATURE` elements print. Design's signed print resolution carries the bytes of the assets the layout references (verified digest, bounded size); Vouchers re-checks type and size and embeds them; nothing is fetched by the browser. | Design resolution tests (cross-company asset refused, tampered bytes refused, size bound); Vouchers render tests; real-Chromium PDF with an image. |
| **R3 — Thermal rolls** | `THERMAL_80MM` and `THERMAL_58MM` print as one continuous page as long as its content. | Real-Chromium roll PDF: one page, roll width, content-length height. |
| **R4 — Designer flow (P5 for Purchase)** | *Customize* starts from a canvas of the standard Purchase layout; the designer shows where a template is used and assigns it to a Purchase type; *Preview with a saved bill* renders the real PDF of a saved version (published or not) for one saved Purchase, marked as a preview. | Design list-by-template tests; Vouchers preview permission/wrong-company/unknown-version tests; console route and component tests. |
| **R5 — Hardening (P7 for Purchase)** | 200-line performance budget; real-Chromium layout suite (standard, custom A4, mixed two-table, roll, image); designer accessibility pass; D5 recorded; operations runbook. | Suites green; budget asserted in tests; runbook in [purchase-print-todo](purchase-print-todo.md) or its own doc. |
| **R6 — Review** | `/simplify`, independent security review (§5/§6), fixes. | Findings reported, including none. |

Not in this section, and said so wherever it shows: QR codes and barcodes (no encoder), custom
fonts (no byte store), batches and expiry (a Purchase bill does not record them), shared
components, other kinds.

### Progress

- [x] **R1 Goods on the print** (2026-11-04). `voucher-execution-client` 0.5.0: Catalog's
  stock facts answer the base unit's symbol when asked (`include_labels`, under the actor's
  field rights, never a refusal); Accounting's print facts return each line's HSN/SAC and unit
  label (preview: tax evidence; posted: the supply fact) and still print a posted bill whose
  product can no longer be read. Fixed: posted goods supply facts recorded no HSN. Vouchers
  prints B24-shaped goods bills (stock lines sent like calculation), freezes quantity, rate,
  HSN/SAC and unit labels (labels re-checked at download), adds `hsn_sac`/`quantity`/`unit`/
  `rate` columns, `totals.amount_in_words`/`totals.cess` bindings and the words totals row
  (`domain/amount_words.py`), and the standard layout prints goods columns and the words
  (`purchase-a4@3`, `purchase-pdf@4`, Design bumped with it). Tests: Catalog
  `test_stock_purchase_tax_facts.py` (+2), Accounting `test_goods_purchase_print.py` (4, the
  posted-HSN regression confirmed failing first), client `test_printing.py` (+7), Vouchers
  `test_purchase_goods_print.py` (26).
- [x] **R2 Images in the PDF** (2026-11-04). Design `printable_assets` in the signed print
  resolution (bounds 512 KB / 640 KB from the 1 MiB service framing; WITHDRAWN/TOO_LARGE/
  OVER_BUDGET/MISSING reasons); Vouchers re-checks and embeds (`picture`), `IMAGE` and image
  signatures print, CSP `img-src data:` for designed layouts only. Tests: Design
  `test_print_assets_preview.py`, Vouchers `test_purchase_print_images_rolls.py`, real Chromium.
- [x] **R3 Thermal rolls** (2026-11-04). One page at the roll width, as long as its content
  (measured in `print_child`, at most 5,000 mm), bill identity at its end. Real-Chromium test.
- [x] **R4 Designer flow** (2026-11-04). Backend: `layout_preview` on print jobs with
  `design.template.read` at creation and download; Design `preview` resolution;
  `GET /assignments?template_id=`. Console: *Customize* for Purchase starts from
  `standard-purchase.ts` (per line profile; empty page only when the paper cannot hold it);
  a "Used for" panel (`TemplateUsage.tsx`) lists, adds and stops Purchase rules, gated by the
  assignment permissions; *Preview with a saved bill* saves first when needed, picks a saved
  Purchase (`SavedBillPicker.tsx`) and opens `[templateId]/preview` (`LayoutPreviewRoute.tsx`,
  `PurchasePrintPreview` with `layoutPreview`); publish checks block a picture-less image,
  a withdrawn asset and pictures over the manifest's bounds (`imageProblems`). Tests: five new
  console suites plus updated print-capabilities, policy and preview suites. Known gaps: the
  voucher list has no supplier bill number, so the picker shows it only after a bill is chosen;
  only a company's first 200 assets are judged at publish (the rest at print).
- [x] **R5 Hardening** (2026-11-04). Budget suite (`test_purchase_print_budget.py`: 200 lines,
  HTML < 1 s untraced, real browser under 45 s, about 6–7 s on an idle machine); runbook in
  [purchase-print-deployment](purchase-print-deployment.md#goods-pictures-rolls-and-previews-2026-11-04-purchase-pdf4-purchase-a43);
  D5 recorded; console labels/roles covered by the R4 suites (no separate audit tool was run).
- [x] **R6 Review** (2026-11-04). Independent security/correctness review: no critical or high
  findings. Fixed: a rate priced per more than one unit now prints its pricing unit; quantities
  and rates finer than the display places print exactly; roll copies stay on one strip;
  upper-case asset ids resolve; a preview with pictures also needs `design.asset.read`; an
  unreadable stored picture is reported as an operator fault (`UNAVAILABLE`); words round with
  the company's rounding mode. **Left open:** image pixel dimensions are not bounded (a small
  file can declare a huge image; needs `design.asset.manage` to upload) — bound them at upload.
  `/simplify` was not run as a separate pass.


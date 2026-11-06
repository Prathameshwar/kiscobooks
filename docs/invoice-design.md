# Invoice Designer (`design`)

Governs the `design` service: how a company authors the **layout** of its printed
documents, how a document about to be printed resolves the layout it prints on, and what
record is kept of what was printed.

This service decides what a document *looks* like. It never decides what a document
*says*: no amount, no tax, no number, no posting. That separation is the whole reason it
is a boundary — a design change must not be able to change a figure, and a figure must
not be able to change because somebody edited a template.

Two live checklists sit beside this doc: [invoice-design-ui-todo.md](invoice-design-ui-todo.md)
recorded the eight phases of front-end build, and
[invoice-design-delivery-todo.md](invoice-design-delivery-todo.md) tracks connecting that front
end to this service. This doc remains what governs the contract.

---

## 1. What it owns

| Concern | Table | Lifecycle |
|---|---|---|
| The design itself — page setup, code, status | `invoice_template` | `status`: `DRAFT` → `PUBLISHED` → `ARCHIVED` |
| An immutable snapshot of the canvas tree | `invoice_template_version` | append-only; `published_at` marks the live one |
| Which design a document kind prints on | `invoice_template_assignment` | `is_active` |
| Brand graphics, signatures, seals, fonts | `invoice_template_asset` | `is_active` |
| Reusable blocks (bank details, terms, signatories) | `invoice_template_component` | `is_active` |
| What was printed, and from which version | `invoice_render_snapshot` | append-only |

**Out of scope, deliberately:** rendering. This service produces no PDF and runs no
browser. It answers "which layout, and what is in it", and records "this artifact was
produced from that version". The renderer is a separate concern with a separate risk
profile (§6.2, §9).

Payroll, notification transport and voucher content are other services' concerns. The
`voucher_kind` vocabulary is the shared one from [vouchers-plan](vouchers-plan.md); this
service validates its shape and never interprets it.

---

## 2. Why a separate service

A layout is configuration with an unusually large blast radius: one row decides what
every future invoice looks like, including which fields a customer sees. It also has a
storage profile nothing else here shares — a large JSON tree per version, kept forever,
read on every print.

- Keeping it out of `vouchers` keeps a document's *content* pipeline free of its
  *presentation* pipeline. A template edit cannot touch a posted figure, because the two
  live in different databases and only one of them posts.
- Keeping it out of `reports` keeps analytical load away from the print path.
- Its own database means its own grants: the service that composes a document body has no
  access to money tables, which is what makes §6.2's injection surface survivable.

---

## 3. Scope and ownership

### 3.1 Tenant and company

Every table carries `tenant_id` and is subject to the session-level filter
(CLAUDE.md §5.3). Templates, assets and components additionally carry `company_id`, where
the `SCOPE_ALL` sentinel means **tenant-wide**.

### 3.2 The shared house style

A tenant-wide row is visible to every company in the tenant and writable only with
tenant-scoped authority (`api/authorization.py`). This is the whole reason the service
distinguishes the two scopes: a company administrator must be able to design that
company's invoice, and must not be able to redesign every company's invoice.

A company-owned row of the same kind always wins for that company, because resolution
only ever returns one layout and rules are ordered (§5.2).

### 3.3 What a tenant cannot edit

A shipped (`is_system`) template or component is read-only to every actor, including a
tenant administrator. Customising one means copying it. This is a domain rule, not a
permission — the same shape as the shipped system roles
([roles-permissions](roles-permissions.md) §1.2).

---

## 4. Data model

Conventions as elsewhere: singular table names, UUIDv7 `BINARY(16)` keys, UTC `_at`
timestamps, `VARCHAR` + application validation instead of MySQL `ENUM`
(CLAUDE.md §4). Migrations are in `dbs/design/`, one DDL statement per revision.

**One lifecycle mechanism per entity** (rule 4.12), and it is enforced by a test
(`tests/test_service_contract.py`):

- a template has `status` and no boolean. Its soft delete is `status = 'ARCHIVED'`;
- assignments, assets and components have `is_active` (via `DeactivableMixin`) and no
  status;
- a version has **neither**. It is immutable, and "this is the live layout" is
  `published_at` — a date, because the question anyone asks of a design is *since when*.

### 4.1 Codes, and reusing one

`invoice_template.live_code` is a generated column:

```sql
live_code VARCHAR(50) GENERATED ALWAYS AS
  (CASE WHEN status <> 'ARCHIVED' THEN code ELSE NULL END) STORED
```

with `UNIQUE (tenant_id, company_id, live_code)`. MySQL permits many NULLs in a unique
index, so one live code coexists with any number of archived rows that once used it. A
plain unique key on `code` would burn the code the first time a design was retired, which
is the opposite of what retiring it means. Verified against MySQL 9.6: two archived rows
plus one live row with the same code are accepted; a second live duplicate is rejected.

### 4.2 Measurements

`page_width_mm` and `page_height_mm` are `DECIMAL(19,4)` and `Decimal` end to end. Four
decimals is the platform's fixed storage scale for every amount and quantity, never
narrowed per column, because MySQL re-scales a smaller scale without erroring
(CLAUDE.md §4). The API speaks `Decimal` for them too, so a float round-trip cannot
silently change a page size.

Geometry **inside** the layout JSON (element `x`/`y`/`width`/`height`, margins, font
sizes) is `float`. It is display geometry in millimetres and points, it is not a column,
and the renderer consumes it as numbers. See the decision log.

### 4.3 Digests

A version stores `layout_digest`, the SHA-256 of its canonical layout JSON. It gives a
reprint something to verify against and makes "did this layout actually change?"
answerable without diffing two trees. An asset stores `content_digest`, the SHA-256 of the
uploaded bytes, so a swapped object in the bucket is detectable.

### 4.4 Print evidence

`invoice_render_snapshot` is append-only, and both its foreign keys are
`ON DELETE RESTRICT`: a template version a document was printed from is never removable
(CLAUDE.md invariant 12). A reprint is a new row — "this invoice was printed twice" is a
fact an auditor needs, and an update would erase it.

---

## 5. Behaviour

### 5.1 Template and version lifecycle

1. `POST /templates` creates a `DRAFT`, optionally with version 1 of its canvas. The
   response returns `initial_version_id`; `current_version_id` is null, because **creating
   a design does not make it print**.
2. `POST /templates/{id}/versions` appends the next version. Numbering is allocated under
   a row lock on the template, so two concurrent saves cannot both claim version 4.
3. `POST /templates/{id}/versions/{version_id}/publish` stamps `published_at`, points
   `current_version_id` at it and sets the template `PUBLISHED`. This is the act that
   changes what future documents look like, so it has its own permission
   (`design.template.publish`) and its own audit event.
4. `PUT /templates/{id}` changes metadata only. **`status` is not writable** — a client
   that could write it could mark a template live with no layout behind it.
5. `DELETE /templates/{id}` archives: the row stays, the code is released, and active
   assignments pointing at it are deactivated in the same transaction. Leaving them live
   would keep resolving a retired design; silently resolving a different one would be
   worse, because the operator configured *this* one.

A version is only ever reachable **through its own template**. Every lookup takes the
template id and filters on it (§6.1).

### 5.2 Resolution

`POST /resolve` answers "which layout does this document print on?" The order is fixed,
because two callers printing the same document must get the same design:

1. candidates are **active** rules for this `voucher_kind`, owned by this company or the
   tenant;
2. a rule matches only if **every criterion it pins** equals the request's value. A rule
   pinned to one branch does not apply to another, and a request that does not state a
   branch does not match a branch-pinned rule;
3. candidates are ordered by `priority` descending, then by **specificity** (how many of
   `voucher_type_id`, `branch_id`, `currency_code`, `customer_tax_category` the rule
   pins), then newest first — a tie is never resolved by luck;
4. the first candidate whose template is still publishable wins. A candidate whose
   template has been archived or never published is **skipped**, not fatal;
5. with no usable rule, the company's most recently published template is used and the
   response returns `assignment_rule_id: null` — the difference between "configured" and
   "defaulted", which an operator needs to see;
6. with nothing publishable at all, 404.

> **Decided 2026-10-30, not yet implemented.** Steps 5 and 6 are to become "the built-in
> standard layout for the kind", answered as built in. "The most recently published
> template" is arbitrary the moment a company has two, and moves whenever anyone publishes;
> 404 leaves a new company unable to print anything. See the decision log, *Printing needs no
> setup*. Until the standard layouts exist (§9 item 7) the service behaves as written above.

A rule is validated **when written**: its template must be visible to the company writing
it, and a pinned `specific_version_id` must belong to that template. Reading is the hot
path, and a renderer must not be the thing that discovers a cross-company reference.
Criteria are immutable once written — a different set of criteria is a different rule, and
editing one in place would rewrite the reason every past document resolved as it did. An
exactly duplicate active rule is a 409.

### 5.3 Permissions

Eleven keys in the code catalogue ([roles-permissions](roles-permissions.md) §2):

| Key | Authorizes |
|---|---|
| `design.template.read` | reading templates, versions, and `POST /resolve` |
| `design.template.manage` | creating and editing templates and versions |
| `design.template.publish` | making a version the live layout |
| `design.assignment.read` / `.manage` | reading / writing routing rules |
| `design.asset.read` / `.manage` | reading / registering brand assets |
| `design.component.read` / `.manage` | reading / writing reusable blocks |
| `design.render.read` | reading print evidence |
| `design.render.record` | recording that a document was printed |

`manage` and `publish` are separate for the same reason
`vouchers.configuration.manage` and `.publish` are: the act that makes a draft the one
every future document renders from is its own grant. `render.record` belongs to whoever
*issues* documents, not to whoever designs them — so a billing clerk holds it and a
designer does not.

Every route checks the key against the **object's own scope**: a company-owned row against
that company, a tenant-wide row against `ScopePath()` (CLAUDE.md §5.2). The endpoint key
alone is never sufficient.

### 5.4 Lists

Every growing list is keyset-paginated with a signed cursor (`limit` default 50, maximum
200) and returns a lean item schema ([api-conventions](api-conventions.md)). A layout tree
and a component's contents are detail reads: shipping them in a list page turns a cheap
index into an expensive one. The cursor's context binds resource, scope, actor and an
authority version derived from the actor's resolved permissions, so a cursor minted before
a revoke does not keep paging after it.

### 5.5 Invariants that do not apply here, and why

A reader arriving from CLAUDE.md §6 will look for these; their absence is deliberate, not
an oversight.

- **No idempotency keys** (invariant 2). Nothing in this service moves money. A replayed
  `POST /templates/{id}/versions` appends a second draft version, which is visible, costs
  nothing and changes no document — publishing is the act with an effect, and publishing
  the same version twice is a no-op by construction (§5.1).
- **No `assert_postable`, no `posting_date`** (invariants 3 and 4). There is no financial
  write and no fiscal period involved: a layout has no accounting date, and a document
  printed from it carries its own, owned by Vouchers.
- **No fiscal immutability ratchet** (invariant 16). The equivalent here is narrower and
  lives in the domain: a published version's layout is immutable, and an `is_system`
  template is read-only to everyone (§3.3).

---

## 6. Security

### 6.1 Object scope

The three holes this service shipped with were all the same bug — an id trusted without
its parent:

- a version fetched by id alone could be read through any template, leaking another
  company's layout;
- the same version could be **published onto** another company's template, silently
  changing what that company printed;
- an assignment could name another company's template, and resolution would then serve it.

Each is now a predicate in the domain (`tasks/versions.py`, `tasks/resolution.py`) and a
regression test. The rule for anything added later: a child row is fetched **through its
parent**, never by id alone.

### 6.2 The canvas is attacker-controlled input

A layout is stored verbatim and later compiled into a document, so every field is
`extra="forbid"` and bounded (`schemas/canvas.py`):

- **No raw markup and no raw CSS.** Styling is typed scalars — a size in points, a colour
  as a hex triple, an alignment from a fixed set — and the renderer composes the
  stylesheet from them. A free-form `style` string is how `expression(...)`,
  `url(http://169.254.169.254/...)` or `</style><script>` reaches the output.
- **No compiled document body is accepted or stored.** The previous schema took
  `compiled_html_template` and `compiled_css` straight from the client; both columns are
  gone. The renderer compiles from `layout_definition`.
- **Bindings come from an allowlist of roots** (`voucher`, `company`, `party`, `address`,
  `line`, `tax`, `totals`, `bank`, `signatory`, `custom`). The allowlist bounds what may
  be *asked* for; field-level read denies are still applied by the renderer when it
  materializes values (CLAUDE.md §6.15).
- **No open key/value bags.** There is no free-form `props` on an element and no
  `metadata` on the root. A dict with an arbitrary key set is `extra="allow"` under
  another name, and the keys a renderer may treat as structural (`src`, `style`, `href`)
  are exactly the ones an attacker would pick. Element options are typed fields —
  `symbology`, `show_value`, `image_fit` today — and a renderer that needs another one
  gets another typed field (§9).
- **Free text is text.** `content`, `label`, `title` and a component's
  `content_definition` values carry prose a tenant composes; the renderer prints them
  escaped, never as markup or as an attribute. The guarantee above is about *fields* —
  no field exists whose purpose is to carry markup, CSS or a URL.
- **Counts and lengths are capped** — 40 sections, 200 elements each — so one request
  cannot store a layout nothing can render.
- **References are checked when stored**: an asset or component a layout names must belong
  to this company (or the tenant) and be active. Discovering a dangling reference at print
  time is the worst possible moment.

A `custom.*` binding is permitted because displaying a custom field is allowed; a custom
field still never prices, taxes, posts or routes anything (CLAUDE.md §6.14).

### 6.3 Assets

Images (logo, signature, stamp/seal, watermark, header/footer banner) upload, store and
serve their bytes (plan P4, 2026-11-03, D3). Fonts remain metadata-only and a `CUSTOM_FONT`
upload is refused with that reason stated plainly — accepting one without a storage and
embedding story would be an upload that silently does nothing useful at print time.

- `POST /assets` carries the file base64 in `content_base64`. The service decodes it,
  sniffs the format signature against the declared `mime_type` (never trusts the claim
  alone), and writes it to the same private VM disk Purchase's supporting files use —
  content-addressed, atomic (tempfile, `fsync`, hardlink), read back and verified before
  the row is written. `storage_path` and `storage_backend` stay **derived**, as
  `<prefix>/assets/<tenant>/<company>/<asset-id>.<ext>`, from the same configured prefix; a
  client-supplied path can name another tenant's object, so there is no field for one;
- there is **no** `public_url` column and no public object storage (CLAUDE.md §5.14).
  `GET /assets/{id}/download` instead takes a `token` — short-lived (120 s), HMAC-signed,
  and bound to both the asset id and the requesting actor (`CursorCodec` with a context
  string naming both), minted fresh on every list or detail read of that asset and
  rejected if replayed for a different asset or actor. The console's own image route holds
  no bearer token and mints no token itself — it only ever names the one it was handed;
- `mime_type` must match the asset kind, and `image/svg+xml` is refused — SVG carries
  script and external references, the one thing a document renderer must not fetch;
- `content_digest` (SHA-256) is required and re-checked on every download before the bytes
  leave the service, and sizes are capped at 5 MiB for images (fonts, unimplemented, stay
  capped at 2 MiB in the schema for whenever that work starts).

A render snapshot's `storage_path` is derived the same way, under the same prefix:
`<prefix>/renders/<tenant>/<company>/<snapshot-id>.<ext>`. It was briefly accepted from
the request body on the theory that a trusted renderer reports where it wrote the
artifact — but `design.render.record` is deliberately held by whoever *issues* documents
(a billing clerk), so that body is user input, and a free-form key let one company's
print record name another tenant's object. The service computes the key and returns it in
the 201; the renderer writes there.

### 6.4 Transport and process

Authentication is the gateway-signed actor context, verified and never minted here. There
is **no test-header fallback**: a header that authenticates without a signature is a
bypass wherever the setting meant to gate it is missing. Support (impersonated) sessions
are read-only. Configuration has no defaults for the database URL or the signing secrets —
a default signing secret is a forged context waiting to happen (CLAUDE.md §5.9).

Writes are rate limited in-app per actor and at nginx (`design_write` zone). Bodies are
bounded before JSON parsing, with a wider ceiling for a canvas save. Every response
carries `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and
`Referrer-Policy: no-referrer`. Errors return the envelope only.

---

## 7. Audit

Every state change emits an event **in the same transaction** through the outbox
(CLAUDE.md §6.8, §6.10). `design.tasks.audit_publisher` drains it onto `platform.audit`,
with a `ServiceKey` minted from exactly the declared event set
(`events/audit_contract.py`); Audit rejects an event whose route and entity disagree
(`audit/domain/source_contract.py`, which now accepts `design` as an issuer).

Events are `design.<entity>.<action>` with `entity_type = "design.<entity>"`. Actions:
`create`, `update`, `publish`, `archive`, `deactivate`.

Payloads hold `actor_user_id` and never denormalized PII (audit §5.2). A layout tree is
never copied into an audit row: it is large, already versioned immutably, and the auditable
fact is *which version* became live, not its bytes. Template changes are category `admin`;
render snapshots are `access`, because a print is a read of a document that happened.

---

## 8. Operations

- Port 8014 locally, route `/design/`, registered in `start/win/conf/services.json` and
  `start/win/conf/bill.conf` with its own `/_design_authorize` subrequest.
- Migrations: `dbs/design/`, head `0008`. The readiness probe reports ready only when this
  service's tables exist **and** `alembic_version` equals the head this build expects.
- Environment: `DESIGN_DATABASE_URL`, `DESIGN_ACTOR_SIGNING_SECRET` and
  `DESIGN_CURSOR_SIGNING_SECRET` — the last of these is generated by
  `start/win/lib/write-envs.ps1`. The publisher additionally needs
  `DESIGN_AUDIT_BROKER_URL`, `DESIGN_AUDIT_BROKER_USER`, `DESIGN_AUDIT_EVENT_SECRET` and
  optionally `DESIGN_AUDIT_EVENT_KEY_ID`; like Identity's audit worker, those are
  operator-supplied rather than generated, so the design audit worker does not start
  locally until they exist. Audit needs a matching `AUDIT_SOURCE_CREDENTIALS` entry under
  a **design-specific `key_id`** — the consumer resolves the issuer from the key id, so
  reusing another service's key would blur the issuer boundary that
  `source_contract.py`'s entity check depends on.
- Contract: `apis/design/openapi.json`, regenerated with
  `uv run python tools/export_openapi.py`; the TypeScript client is
  `clients/api-client/src/design.d.ts`.
- Dialect check: the suites run on in-memory SQLite, so
  `DESIGN_TEST_MYSQL_SERVER_URL=... uv run python tools/mysql_smoke.py` applies the
  migrations to a throwaway MySQL schema, drives create → publish → resolve → archive →
  code reuse through it, asserts `DECIMAL(19,4)` round-trips as `Decimal`, and drops only
  the schema it made. It is the only check that proves the `live_code` generated column
  behaves — "many NULLs in a unique index" is MySQL semantics, not SQLAlchemy's.

---

## 9. Open questions

These are **not** silently answered anywhere in the code. If a task depends on one, ask.

1. **The renderer — Purchase decision accepted, 2026-10-31.** Purchase PDFs use a
   headless Chromium renderer in a Celery worker on the deployment VM. The worker has a
   dedicated service/OS/database identity and consumes frozen, permission-bound saved
   facts; it cannot post money or mint interactive user authority. Design remains the
   layout owner. A signed, company-scoped internal resolution boundary serves the worker
   pipeline; browser render-evidence writes remain closed. Other kinds and full canvas
   feature parity remain separate delivery work. See [Purchase delivery](purchase-print-todo.md).
2. **Object storage — Purchase PDF decision accepted, 2026-10-31; brand-asset images
   decided 2026-11-03 (designer plan D3/P4).** Purchase PDFs use private local VM disk,
   with content-addressed, tenant/company/voucher-scoped keys, authenticated delivery and
   expiring signed download tickets. Brand-asset **images** (logo, signature, stamp/seal,
   watermark, header/footer banner) now use the same adapter: `POST /assets` writes the
   decoded bytes to this service's own private disk under a service-derived key, measures
   size/digest/PNG dimensions from the bytes rather than trusting the request, and
   `GET /assets/{id}/download` returns them only against a signed, actor-bound, expiring
   token (CLAUDE.md §5.14) — the absence of a `public_url` column was deliberate groundwork
   for exactly this, not an omission. **Still open:** `CUSTOM_FONT` classifies an asset
   without a byte-storage path — font upload is refused with that reason until one is built.
   Embedding an uploaded image in a *rendered* Purchase PDF was built on 2026-11-04 (the
   signed print resolution carries the verified bytes; decision log 2026-11-04). See
   [production plan](invoice-designer-production-plan.md#delivered).
3. **Element options — mostly answered, 2026-10-27.** The `ITEM_TABLE` column set, the
   totals-row vocabulary, tax grouping and print options are **ratified and implemented** as
   canvas `1.1.0` (see the decision log, and
   [invoice-design-delivery-todo.md](invoice-design-delivery-todo.md) §D2).

   What stays open: what a `BARCODE` needs beyond `symbology`, and whether per-element locale
   or number formatting belongs here or in the resolved display config. Both will be typed
   fields, not a map, when the renderer states them.
4. **Thermal and label formats.** `THERMAL_80MM`, `THERMAL_58MM`, `ZPL` and `ESC_POS`
   appear in the vocabulary. Whether this canvas model (millimetre geometry, free element
   placement) is the right shape for line-mode printers is undecided.

   Partial evidence, not an answer: the designer UI reshapes an A4 invoice onto an 80mm and
   a 58mm roll and renders the result, so millimetre geometry is at least *workable* for
   roll stock — including the part that needed deciding, that a continuous roll is drawn as
   long as its content rather than at a nominal page length. Since 2026-11-04 Purchase PDFs
   print 80 and 58 mm rolls exactly so: one page as long as its content. `ZPL` and `ESC_POS`
   are untouched by that work and are the half of this question still open: both are
   line-mode command streams, and nothing has been built against either.
5. **Template export/import between tenants.** Wanted for shipping starter designs; needs
   a decision on how asset references travel.
6. **Localisation of static text — decided 2026-11-04: one language per template.** An
   element's `content` is one string and prints exactly as typed; a company needing two
   languages keeps two templates. Content keys resolved at print were not chosen.
7. **System templates, and the built-in standard layout.** The model and the domain rule exist
   (`is_system`), but no shipped designs are seeded. Seeds live in `seeds/`, never in
   migrations. The 2026-10-30 decision (*Printing needs no setup*) makes the standard layout
   the final fallback for every kind rather than something a company provisions, which
   narrows this item to: author one canvas per kind, and decide whether they ship as code
   with the renderer or as `is_system` rows. **Purchase decision accepted, 2026-10-31:**
   ship versioned `purchase-a4@N` with the renderer (currently `@4`; the version moves
   whenever the printed presentation does), without company provisioning. A
   matching published custom rule takes precedence; an unsupported custom feature must
   produce an explicit refusal, never a silently substituted standard PDF.
   Packaging for other kinds remains open. **Decided 2026-11-04 for Purchase:** *Customize
   layout* starts from a canvas copy of the standard layout (`purchase-a4@7`, with the line
   tables its line profile needs; console `standard-purchase.ts`), or from an empty page
   when the chosen paper cannot hold it. Other kinds still start empty.

---

## 10. Decision log

### 2026-11-05 — Purchase receiving references on print

The standard internal Purchase voucher now prints the saved warehouse, bin, batch and
serial references when the actor may read the entire stock block. The print freezes only
those references, not unverified display names. The same data is available to a designed
layout through `voucher.receiving_summary` (`print-capabilities@2`). This binding needs
its own non-header zone and vertical band so long serial lists can grow without clipping
another element. A later field denial
invalidates an earlier PDF download. Readable master names, batch codes, expiry and company
legal identifiers need owner contracts and field-policy decisions before printing them;
the default labels the current values as references.

### 2026-11-04 — Purchase is the base, made production ready; one language per template

The owner set D4 aside ("we will proceed with Purchase ... production ready at least for
Purchase as base") and answered D5: **one language per template**. Delivered as the production
plan's §8 R1–R5 ([plan](invoice-designer-production-plan.md#8-purchase-production-readiness-agreed-2026-11-04),
[runbook](purchase-print-deployment.md#goods-pictures-rolls-and-previews-2026-11-04-purchase-pdf4-purchase-a43)):

1. **Goods print.** Product and Mixed Purchase bills print with HSN/SAC, quantity with unit and
   rate; amount in words is a binding and a totals row. HSN/SAC comes from what Accounting
   taxed the line under; the unit symbol from Catalog's stock facts under the actor's rights.
   The standard layout moved to `purchase-a4@3`, the renderer to `purchase-pdf@4`.
2. **Pictures print from the signed resolution.** This service sends the verified bytes of
   the images a layout names (or why one cannot print) inside the signed print resolution; the
   renderer fetches nothing. Bounds: 512 KB per picture and 640 KB per layout, because the
   platform's signed service framing caps a body at 1 MiB. A deactivated picture refuses the
   print with its reason rather than vanishing from it. This closes the "embedding" half of
   §9 item 2; fonts stay open.
3. **Rolls are one continuous page** as long as their content (§9 item 4, for PDF output; the
   line-mode ESC/POS and ZPL half stays open).
4. **Previews and where-used.** The internal resolution accepts a `preview` naming one saved
   version (any status but archived, this company's or the tenant's, Purchase or any kind) and
   marks it; Vouchers requires the person's `design.template.read` to request one and again to
   download it. `GET /assignments?template_id=` lists where one design is used. The designer
   shows that list ("Used for"), assigns the design to a Purchase type, and previews a saved
   version on a chosen saved Purchase bill through the real renderer.
6. **Customize starts from the standard layout** for Purchase (§9 item 7).
5. **Static text** prints exactly as typed in whatever script (D5); a company needing two
   languages keeps two templates. Generated words (amount in words, copy marks, "Restricted")
   are English. The print VM must carry fonts for the scripts its templates use.

### 2026-11-03 — A designed layout prints as drawn

Purchase's custom-layout *flow profile* (full-width blocks, no styles, eleven fields) is retired.
A custom layout is printed by a canvas renderer at its own millimetres, paper and margins, and
what it may use is one published manifest per kind that the renderer enforces and the designer
reads. Renderer `purchase-pdf@3`; queued `@2` jobs fail as `SOURCE_INTEGRITY` and are re-requested,
as every renderer change requires. Details and limits:
[production plan](invoice-designer-production-plan.md#delivered). This partly answers §9.1 for
Purchase: the renderer now consumes the canvas, not a subset of it.

### 2026-11-03 — Placing objects and leaving the editor

The owner could not tell how to put anything on the page and found no way out of the
full-bleed editor. Changed in the console only; the canvas contract (1.1.0) is unchanged.

- **Always somewhere to place.** A palette click goes into the selected zone, or the zone of
  the selected element, and into the page's first zone when nothing is selected, so the
  palette is never a column of disabled rows. The rail says where a click will land.
- **Plain objects beside fields.** *Add to the page* offers Text, Line (`DIVIDER`), Box
  (`SHAPE`, ruled 0.3 mm) and Signature, each added like a field and selected on arrival.
- **Drag and drop.** Any palette row can be dragged onto the page; it lands in the zone
  under the pointer at that point, clamped inside the zone. The canvas accepts only the
  palette's own drag types, so a dragged file or link is never taken for content. Outside
  every zone it lands below the destination's content instead.
- **Keyboard.** The field list is one tab stop with the arrow keys, Home and End inside it,
  so the canvas is not fifty presses from the rail.
- **Back.** *Back to templates* is the first control in the toolbar; leaving with edits
  since the last save or publish asks first, and a reload or close warns. The gallery has
  *Back to home* and *Voucher print*.

Voucher-type-aware design (which controls and tables a Product, Account or Mixed voucher can
print) is planned in [invoice-designer-production-plan](invoice-designer-production-plan.md)
(agreed 2026-11-03: template columns for kind and line profile, two tables for Mixed, private VM
disk for assets).

### 2026-11-03 — A template says what it is for; `1.1.0` widened for `ACCOUNT_TABLE`

Plan phases P1/P2. `invoice_template` gains `voucher_kind` and `line_profile` (migration
`0009`, nullable: an unstated template stays routable by any kind, as before). Routing and
resolution honour it — a rule cannot name a template designed for another kind, resolution
never falls back across kinds, a template is not re-purposed while active rules still print the
old kind on it.

A Mixed document's lines print in two tables (D2): `ACCOUNT_TABLE` joins `ITEM_TABLE` in canvas
`1.1.0` itself, **not** a new `1.2.0`. This looks like the move the 2026-10-27 entry calls
wrong, so the distinction is worth stating: that entry froze `1.0.0`'s *behaviour*, because a
restriction 1.1.0 needed (the page-fit rule) could reject a layout `1.0.0` had already accepted,
and a stored row re-validating on every read would then fail to reprint a document already
issued. Adding `ACCOUNT_TABLE` restricts nothing — it is one more allowed value in a `Literal`
and one more type two existing option checks (`columns`, `row_options`) already named, so every
layout that validated under 1.1.0 before this change still validates, byte for byte, after it.
Nothing stored is re-normalized and no digest changes. The freeze is for a rule that would
*narrow* what validates; this widens it, on the schema version still being written to, before
any successor exists to freeze it against.

### 2026-10-31 — Purchase PDF runtime, private disk and standard-layout packaging

The user selected Chromium/Celery on their VM with private local disk, and selected a
versioned standard A4 layout shipped in renderer code. The Vouchers pipeline freezes
saved revision facts, Accounting-owned exact amounts, signed Identity display formats,
Design resolution and the requesting user's disclosure fingerprint before queueing.
Posted invoices read immutable Accounting facts instead of calculating against changed
masters. Browser requests name a saved revision/version only. Generation allocates no
number and has no approval, posting or settlement effects. Worker environment files
must be separate from API credentials: no actor signing secret belongs in a renderer.

This decision closes runtime/storage/packaging questions for Purchase only. General
asset storage, other voucher renderers, unsupported custom-canvas features and Design
render-evidence synchronization are not implied by the standard Purchase implementation.

**2026-10-27 — Canvas `1.1.0` is ratified, and `1.0.0` is frozen beside it rather than
widened.** The proposal recorded in §9.3 is now the schema: item-table columns, row options,
a totals-row vocabulary, `TOTALS_BLOCK`, tax grouping and print options, all typed fields.

The mechanism is the decision. `CanvasV10` keeps its exact shape, `CanvasV11` sits beside it,
and the two are a union discriminated on `schema_version`, parsed through one `TypeAdapter`.
Widening the existing model was the obvious move and is wrong: a version row stores its tree
verbatim with a `layout_digest` over **those exact bytes** (§4.3), so widening would
re-validate every stored layout against a shape it was not written against, and *normalising*
one on read would change its digest and silently invalidate a published document's print
evidence. A request now names its own contract and a stored row re-validates against the one
it was written against.

**1.0.0 is therefore frozen in behaviour too, not only in shape.** The new page-fit rule
applies to 1.1.0 only. A stored version is re-read on every resolve, so a new rejection applied
to the old shape would not merely block new saves — it would break reprints of documents
already issued.

Three rules arrive with the fields that need them, each from a failure rather than a taste:
visible column widths may not exceed their table (the 204mm-in-190mm set the front end found
by printing a real invoice, which on paper is a clipped last column); an option is refused on
an element type that cannot act on it (`totals_rows` on a `DIVIDER` makes a layout's meaning
depend on which fields the renderer happens to read — an open map by another route); and
section and element ids are unique across the tree (the editor addresses selection, undo and
z-order by id; a renderer takes whichever duplicate it saw last).

Crowding a margin is **not** refused. The editor lists warnings at the moment of publication,
where a person can weigh them; that is not a judgement a 422 can make on their behalf. Only a
box off the edge of the sheet is rejected, because nothing can print it.

**2026-10-27 — Page geometry has one home: the template row.** `CanvasPage` restated
`size` and `orientation` inside the layout tree, *in the opposite case* to the row's
(`"portrait"` against `PORTRAIT`), while the row additionally owned `page_width_mm` and
`page_height_mm` as `DECIMAL(19,4)` with a validator requiring both for `CUSTOM` — which the
canvas had no way to express at all, despite offering `CUSTOM` in its own enum. One document,
two answers to "what paper is this?", in two cases, with nothing to resolve them: the renderer
would have had to guess, and a wrong guess is a wrong-sized PDF.

`CanvasPageV11` therefore carries margins and the editor's grid only. Paper size and
orientation are the row's, where they are already `Decimal` and already validated. `grid_size`
became `grid_step_mm` in the same change, because it never said what it was measured in and
the editor had already decided it was millimetres.

This is what makes `assert_layout_fits` live in `tasks/` rather than in the canvas model: the
only thing that knows how big the sheet is, is the row being saved against.

**2026-10-26 — The front end leads the canvas schema, and says so.** Eight phases of
designer UI ([invoice-design-ui-todo.md](invoice-design-ui-todo.md)) were built against a
client-side layout model, with static fixtures and no call to this service. That ordering
was deliberate — the interface is reviewable before a schema is committed to a migration —
and it has already paid: building a real editor found layout errors (an overflowing column
set), accessibility defects (every editor input drawn at 1.26:1 contrast) and a rendering
decision (a continuous roll has no page length) that reading a schema would not have
surfaced. The model is a **proposal**, recorded in open question §9.3. This service accepts
nothing from it yet, and wiring the two together is a change of data source for the UI and
a schema decision for the service — not a merge of two things that already agree.


**2026-10-25 — The service is a documented boundary.** `design` existed in the tree with
no doc, no decision-log entry, no row in CLAUDE.md's table, no migration tree, no
permissions and no audit emission. It is now the platform's eighth service, with this doc
governing it. The alternative — folding it into `vouchers` — was rejected: a template edit
would then share a database and a deploy with money execution.

**2026-10-25 — Status is the only lifecycle mechanism on a template.** It previously had
`status` *and* `is_deleted`, which rule 4.12 forbids. Archiving is now
`status = 'ARCHIVED'`, and the code it held is released through the `live_code` generated
column rather than being burnt forever.

**2026-10-25 — A version's liveness is a date.** `is_locked` was a boolean that said a
version was published without saying when. It is now `published_at`/`published_by`.

**2026-10-25 — No client-supplied compiled HTML or CSS.** The columns and the request
fields are gone. Accepting a precompiled document body makes every template an injection
vector into whatever renders it, and nothing legitimate needed it: the designer produces a
layout tree, and the renderer compiles it.

**2026-10-25 — Typed styling instead of CSS strings.** `CanvasStyle` was
`extra="allow"` with free-form `border`, `padding` and `color` strings. It is now a closed
set of typed scalars. This narrows what a designer can express; the trade is deliberate,
and widening it means adding a typed field, not reopening the model.

**2026-10-25 — Layout geometry stays `float`; page geometry is `Decimal`.** The platform
rule is about money and quantity *columns*. A template's page size is a column, so it is
`DECIMAL(19,4)`. Element coordinates live inside a JSON tree the renderer consumes as
numbers; forcing them through `Decimal` would store `"10.0"` strings in the layout and buy
nothing, since no total is ever computed from them. The digest therefore uses
`json.dumps(sort_keys=True)` rather than the platform's canonical encoder, which refuses
floats by design.

**2026-10-25 — Dedicated `design.*` permissions rather than reusing
`vouchers.template.manage`.** An interim fix had gated every design route, reads included,
on one voucher key. Reusing another service's key makes a grant mean two things and makes
revocation imprecise.

**2026-10-25 — Actor context only, with in-service company-scope checks.** Requiring a
signed *company* context would 401 every request, because Identity signs one only for the
accounting, vouchers and reports routes; accepting one optionally — the state this service
was in — meant the scope check could be skipped by omitting a header. Scope is now checked
against the object's own company on every route. If design later needs resolved company
facts or field policies, `CompanyContext.policy_namespaces` has to gain `design` first, and
that is a change to Identity's contract.

**2026-10-25 — Resolution skips unusable candidates.** It previously took the single
newest published template and failed if that one had no version, so one bad candidate
could make a company unable to print at all.

**2026-10-25 — Assets are metadata-only until a storage adapter exists.** The alternative
(inventing an S3 client here) would have shipped an unverifiable upload path. The
boundary is explicit instead: derived path, required digest, no public URL.

**2026-11-03 — Images are no longer metadata-only (D3, plan P4); fonts still are.**
Superseding the above for images only: the same private-VM-disk pattern Purchase's
supporting files already use removed the "unverifiable upload path" objection, so images
upload, store and serve for real now (§6.3). Fonts are unimplemented rather than
half-built — a `CUSTOM_FONT` upload is refused with its reason, not silently accepted and
then unusable at print time, which would have been worse than refusing it plainly.

**2026-10-25 — A shared layout may reference only shared assets.** A security review of
this change found that `assert_layout_references` was called with the *path* company
rather than the row's owner, so a tenant-wide template could embed one company's private
logo, signature or seal — and resolution then served it to every company in the tenant.
Both call sites now pass the owner (`SCOPE_ALL` for a shared row, `template.company_id`
for a version), with regression tests.

**2026-10-25 — Render snapshots derive their artifact key.** Accepting `storage_path`
from the body assumed the caller was a trusted renderer; the permission that reaches that
route is held by a billing clerk, so the field was user input into the one record meant to
be trustworthy, and its pattern allowed `..` and any prefix. The key is now derived and
returned.

**2026-10-25 — No open key/value bags in the canvas.** `CanvasElement.props` and
`CanvasDefinition.metadata` accepted any key matching `[a-z][a-z0-9_]*` with free text,
which is `extra="allow"` renamed and defeats §6.2's own claim. Both are removed in favour
of typed options. Nothing consumed them — there is no renderer yet — so this costs
nothing today and keeps the promise true; the cost is that adding an option is a schema
change with a migrationless deploy, which is the intended trade.

**2026-10-29 - Restore native published versions on demand.** The Console editor
reads the selected historical version through the existing scoped version API.
Company/template identity, published state and editable canvas format must match
before the layout replaces current work as one undoable edit. Loading disables
concurrent edits and writes; failures preserve work and offer retry. Shipped and
legacy layouts remain protected. This changes no publication history, rendering
or financial effect. See [tenant-admin batch evidence](tenant-admin-business-fixes-2026-10-29.md).

**2026-10-30 - The Console starts from the voucher, not the rule.** *Voucher print* gives every
kind in the vouchers service's registry (22, not the 16 the routing select carried) a card, and a
page for the templates routed to it with a way to start or put one to work. No service change: it
reads and writes the existing `assignments` and `templates` routes, and the `voucher_kind` list
filter the service already had. The rail entry is now *Print templates*. See
[delivery D8](invoice-design-delivery-todo.md).

**2026-10-30 - Printing needs no setup: the standard layout is the fallback, and customizing is
one step.** A person who creates a company should not have to author a template or write a
routing rule before a voucher prints — Tally, Zoho Books and QuickBooks print every document
type on a built-in layout from the first day and make customizing optional (stated from
general knowledge of those products, not verified here). Decided with the Console owner:

1. **Every kind prints on a built-in standard layout** when no rule resolves and nothing is
   published. This replaces §5.2 steps 5–6. **Not implemented**: it needs the standard
   layouts (§9 item 7), a resolve answer that says the layout is built in rather than a row,
   and a renderer (§9.1). The Console describes the standard layout now because nothing
   prints yet, and the wording is the contract the service is to meet.
2. **Nothing is provisioned when a company or tenant is created.** No seed per company, no
   company-created consumer in `design`, no cross-service call from `identity`. A company
   that never opens Voucher print is to be fully served by the fallback. The alternatives were weighed and
   dropped: per-company starter templates would copy a layout that then drifts from the
   shipped one, and a tenant-wide default rule would need the Console to explain a rule the
   company cannot edit.
3. **Customizing is one action.** *Customize layout* on a voucher's print page creates a
   template and, in the same step, that kind's default rule (priority 100, no conditions)
   on it. The service accepts a rule on a template with no published version and skips it
   when a document resolves (§5.2 step 4), so the rule can be written first and starts to
   apply the moment the template is published; until then the page says the standard layout
   is still in use. *Back to standard layout* retires the rule and keeps the template.
4. **Routing is advanced.** Rules, priorities, conditions and the picker of existing
   templates stay, under *Advanced* on each voucher's page and on the routing page, which the
   rail marks "(advanced)". The routing page's wording no longer calls the fallback "the
   only published template" — it is the most recently published one.
5. **A company's own default coexists with one set for the whole organisation.** The
   duplicate check in `create_assignment` is per company, so a tenant-wide default does not
   stop a company having its own. Which of the two *prints* is decided by §5.2 step 3 —
   priority first, then specificity, then the newer rule — so an organisation default with a
   higher priority outranks the company's own. The Console reads that order (`layoutInUse`)
   rather than assuming the company's rule wins, shows an organisation default as such, and
   writes a company's new default at the winning default's priority so being newer is enough.
   Separately, the duplicate check runs on create but **not** when a retired rule is switched
   back on, so two identical rules can end up active; that is a service gap this decision does
   not close.

Answered 2026-11-04 for Purchase: *Customize layout* starts from a copy of the standard
layout (§9 item 7). Open: what resolve returns for a built-in layout (a sentinel template id, or a flag beside no
template at all) — both belong with the renderer contract.

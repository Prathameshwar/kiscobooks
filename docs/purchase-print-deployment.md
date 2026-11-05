# Purchase PDF deployment and verification

This slice implements standard Purchase PDFs and a restricted A4 custom flow profile.
It does not enable every Invoice Designer element. A matching published rule is resolved
first and its immutable version is frozen into the job. Unsupported features return an
explicit error; the renderer does not silently replace that layout with the standard.

## Runtime and private identities

Run the API, print dispatcher and Celery worker as separate processes. The renderer
worker must have its own environment file, OS account and database credential. Its
`PrintRuntime` configuration deliberately contains no actor/artifact signing secret.
Do not reuse the API environment file for the renderer.

- API: needs the existing Vouchers configuration plus `VOUCHERS_PRINT_FILE_ROOT`,
  `VOUCHERS_PRINT_BROKER_URL`, `VOUCHERS_PRINT_SCOPES` and `VOUCHERS_PRINT_LAYOUT_OWNER`.
  The existing scoped `VOUCHERS_EXECUTION_OWNER` supplies Accounting print facts.
- Design: set `DESIGN_PRINT_SOURCE` to the private Vouchers-to-Design HMAC secret and
  an explicit tenant/company scope list. It must match `VOUCHERS_PRINT_LAYOUT_OWNER`.
  Secrets are runtime configuration only; use independently generated keys of at least
  32 characters. Neither ingress is a public/browser-authorized print evidence writer.
- Worker/dispatcher: `VOUCHERS_DATABASE_URL`, `VOUCHERS_PRINT_FILE_ROOT`,
  `VOUCHERS_PRINT_BROKER_URL`, `VOUCHERS_PRINT_SCOPES`, optionally
  `VOUCHERS_PRINT_TIMEOUT_SECONDS` (15–120, default 90) and
  `VOUCHERS_PRINT_BROWSER_EXECUTABLE` (absolute trusted executable path).
- A scope is `{"tenant_id":"<tenant UUID>","company_id":"<company UUID>"}`. Both
  Design service keys and the worker require explicitly configured scopes.
- A layout owner has `origin`, `secret`, `scopes`. Origins must be HTTPS; literal
  loopback HTTP is permitted for local verification. No user-supplied origin is accepted.

The private root must be an absolute path outside web/public roots, mounted at the
same location for API and worker. The worker writes it; the API reads it. Restrict
permissions to those service accounts. Back it up with the database so retained
hashes, frozen source and PDF bytes can be recovered together. Filenames come from
content hashes and server UUIDs, never browser paths. Links/junctions are refused.

The renderer does not need financial write privileges. Grant its database account
SELECT on `voucher_print_job`, updates only to job state/lease/attempt/hash/size/failure/
audit timestamp/version columns, and the INSERT/SELECT access required to append its
outbox events. The dispatcher additionally needs the outbox publishing/retry columns.
It needs no Accounting database access or Vouchers document write privilege. Verify
the actual runtime grants separately from the application API database account.

Use a dedicated RabbitMQ identity/vhost with only the `vouchers.purchase.print`
direct exchange/queue permissions required by the dispatcher and worker. Configure
the existing audit publisher/consumer contract to include the print-job events: four
lifecycle events (`create`, `started`, `failed`, `ready`) and `vouchers.print_job.download`
(category `access`, written when a PDF is redeemed; see *Download audit* below). The
`vouchers.print_job.execute` dispatch event is consumed only by the print
dispatcher. The Console audit entity catalogue is generated with the existing helper.

## Start and deploy

Install the locked Vouchers dependencies. On the VM, install Chromium and its OS
dependencies using the Vouchers interpreter:

```text
python -m playwright install --with-deps chromium
```

Run the browser sandbox under an unprivileged OS user. The sandbox is on everywhere;
the only way to turn it off is the local-only switch described under *Local-only sandbox
switch* below, which is refused in every environment but `development`. A Windows
development machine can instead explicitly configure its installed Edge executable. External requests, service workers and tenant JavaScript are disabled.
The child receives only frozen JSON over stdin and a restricted OS environment, with
no database/broker/API credentials. Its parent enforces the render deadline and stops
only that renderer's process tree on timeout, including under Celery's solo pool. On
Windows the renderer runs in a kill-on-close Job Object, so one call ends the child, the
Playwright driver and the browser; `taskkill` is only a bounded fallback. Stopping the
renderer never raises or waits without a bound, so a stuck render fails its job with
`RENDER_TIMEOUT` instead of blocking the single worker. The child bounds each browser step
itself and ends before the parent's deadline. Once the PDF exists the child hands it to
its parent first and only then tears the browser and driver down: the deadline watchdog is
disarmed before the write, and a teardown that hangs ends with exit 0 after ten seconds, so
a finished PDF is never lost to a slow browser exit.

The renderer version (`purchase-pdf@4` since 2026-11-04) and the standard layout version (`purchase-a4@3`)
are frozen into every snapshot, and a job whose snapshot carries another version fails as
`SOURCE_INTEGRITY` (the renderer version, checked by the worker) or is refused when frozen
(the layout version, checked by `validate_snapshot`). Both moved from `@1` on 2026-11-01
because the printed output changed under the old strings: the per-page footer, the voucher
number, a ledger line under each particular, the credit period and the settlement rows. The
layout digest is `sha256` of the version string, not of the CSS or the HTML, so it does **not**
change by itself when the body changes: the version is the only guard, and the stylesheet's
header comment states the rule (change the version whenever the printed presentation
changes). Design owns the standard layout's version (`design/api/printing.py`), so Design and
Vouchers must be deployed together for this bump; until then Vouchers refuses Design's older
`@1` layout with "Purchase standard layout version is unavailable". Likewise deploy Vouchers
before Accounting: `voucher-execution-client` 0.3.9 added optional `voucher_number` and `ledgers`
to the print facts, an older Accounting reply still validates, but an older Vouchers refuses a
newer reply because the wire models forbid unknown fields.

Any job created under `@1` fails as `SOURCE_INTEGRITY` by design. Printing has not been
activated on any stack, so there are no `PENDING`, `RUNNING` or retained `READY` jobs to
migrate; if one exists on a stack that was activated by hand, recreate it after the bump.

### Local-only sandbox switch

On a Windows development machine the sandboxed Edge/Chrome launched by Playwright can
fail to return from `new_page`; this was seen on a managed corporate image. The sandbox
stays on by default and in every deployment. For a developer machine only
([purchase-e2e-review](purchase-e2e-review.md), D5):

- `VOUCHERS_ENVIRONMENT` declares the process environment: `development`, `staging` or
  `production`. It defaults to `production`, so an undeclared environment is production;
  any other value (including `local` and `dev`) is refused at start-up.
- `VOUCHERS_PRINT_CHROMIUM_SANDBOX` is `true` by default. Setting it to `false` is accepted
  **only** when `VOUCHERS_ENVIRONMENT=development`; in any other environment the settings
  fail validation and the API, dispatcher and worker refuse to start. The refusal names the
  setting, never a value.
- The decision is made in one function (`vouchers.config.chromium_sandbox`) that re-checks
  the rule where the browser starts, because settings can be mutated after validation. The
  worker passes the result to the renderer child as an explicit boolean; the child keeps the
  sandbox for anything other than a literal `false`.
- The dispatcher and the worker log a WARNING at start-up, and the worker logs it again for
  every render, while the sandbox is off ("Chromium sandbox is DISABLED ..."). Run the worker
  at a log level that shows warnings (the shipped start command uses `WARNING`).
- Neither setting is read from or returned by any request, response, OpenAPI document or
  health probe; there is no per-company or per-user override.

Rehearse the real deployment on the VM (Linux, unprivileged user, sandbox on), not with the
switch. The real-browser tests (`-k real_chromium`) honour the same two settings, so on such
a machine set both before running them; they cannot pass there with the sandbox on.

Rehearse and apply migration `0111` using the existing Vouchers migration procedure
before starting updated API code. It is a single CREATE TABLE DDL with scoped foreign
keys and queue/deduplication indexes. A downgrade refuses to discard retained jobs.
It was rehearsed against a disposable loopback MySQL schema. During the subsequent
company-defaults review on 2026-10-31, the local company database was backed up and only
`0111` was applied; original document/type row counts were retained. The Vouchers API was
restarted and is ready. VM migration, private print configuration and renderer/worker
activation still require their own deployment checks.

Start the processes with separate service environment files:

```text
python -m vouchers.tasks.print_dispatcher --env-file <private dispatcher env file>
python -m vouchers.tasks.print_dispatcher --env-file <private worker env file> --worker
```

For Windows local verification add `--pool solo` to the worker command. The API
does not publish directly: creation and its dispatch event commit together, confirmed
outbox publishing hands off the UUID-only task, and repair requeues pending or expired
leases. Duplicate task delivery preserves a completed PDF. A failed render exposes only
a safe failure code; the preview's retry creates a new job after a terminal failure.

## Contract and supported output

The entry UI is owned by the user's parallel work. Its helper is
`mfes/apps/console/app/lib/purchase-print.ts:purchasePrintHref`. Pass the last confirmed
save's voucher ID, revision ID and row version. Disable the action while edits or an
uncertain save/post command are outstanding. Require company-scoped `vouchers.read`,
`vouchers.artifact.create` and `vouchers.artifact.read`.

The separate preview route is `/vouchers/{voucherId}/print?revision={revisionId}&version={rowVersion}`.
Its proxy accepts only create/status/download. Create accepts identities/version only,
never HTML, a template ID, amounts or a storage path. Download tickets last 120 seconds;
the server rechecks native and owner authority and the saved calculation before reading
the content-addressed PDF. Permission changes invalidate the disclosure fingerprint.
Changed saved revision/status produces a conflict and requires a new copy. The browser
also verifies the SHA-256/size before exposing its ephemeral PDF URL.

Standard `purchase-a4@3` is an internal Purchase voucher, not a replacement for the
supplier's tax invoice. It carries supplier/bill references, document/posting/due dates,
exact owner-produced amounts, components, totals, status, revision and page numbers.
Every page footer repeats the voucher number (or "Not allocated"), supplier, supplier
invoice reference and date, so a loose continuation page still identifies its bill.
Company number/date formatting is signed by Identity. Posted invoices reuse immutable
Accounting records rather than calculate against changed masters. Printing does not
allocate a number, approve, post, reverse or settle a document.

Content of `purchase-a4@3` (everything below is read from the frozen job snapshot, escaped,
covered by its integrity hash and unchanged by a retry or re-render):

- **Voucher no.** A posted bill shows Accounting's journal number (`PURCHASE/<FY>/<seq>`),
  read by Accounting under the actor's journal field rights and carried in the print facts. A
  draft, an approval in progress or a preview, and a posted bill whose number the actor may not
  read, show "Not allocated". A number Vouchers itself issues, if it ever does, takes
  precedence. Numbers are still allocated on posting only.
- **Particulars.** Each line shows its description and, under it, "Ledger: <expense account
  name>" (Accounting reads each name under the account's own field policy; a name the actor
  may not read prints "Ledger restricted" and never another ledger's name).
- **Terms.** Supplier invoice no., supplier invoice date, posting date, payment due, and a
  credit period in days (due date minus invoice date) when the due date is not before the
  invoice date. The bill does not store credit days, so this is derived and labelled as such.
- **Settlement.** When the bill carries tenders or advances: one row per tender (mode, the
  cash/bank ledger name, reference, instrument date), one row for advances and credits, and the
  balance payable after them. Wording is "Paid at posting" for a posted bill and "To be paid
  at posting" otherwise. Amounts are exact decimals from the saved bill (Accounting already
  refused settlements above the payable and in another currency; the print refuses them too).
- **Currency.** Base currency only. Accounting calculates and posts base-currency invoices
  only (a foreign-currency bill cannot be previewed or posted), so there are no authoritative
  amounts to print for one. Vouchers refuses it before asking Accounting, with a message that
  names both currencies. Printing foreign-currency bills first needs foreign-currency invoice
  calculation and posting in Accounting.
- **Company identity.** The header names the company by its display name only. The signed
  company context Identity sends carries the display name and formats but not the legal name,
  address, PAN or GSTIN (its registrations list holds jurisdiction and validity, not numbers),
  and a synchronous call to Identity inside the print path is not allowed. Adding them needs
  Identity to extend its signed context; see [purchase-print-todo](purchase-print-todo.md).
- **Formats.** The company's number, date, precision, rounding and grouping configuration is
  frozen in the snapshot (`display`) at job creation, so a later change to the company's
  formats never changes a retried or re-rendered copy.

### Download audit

Redeeming a download ticket writes `vouchers.print_job.download` (category `access`) through
the outbox before the first byte is sent: the audit transaction commits after the PDF's
integrity check passes, and if it cannot be written the PDF is not delivered. The event holds
the job id, the actor and company ids, the content hash and the size. It never holds names,
amounts or the file. Issuing a ticket is not audited: every status poll of a ready job carries
a fresh ticket, and nothing is disclosed until it is redeemed. A refused, expired, tampered or
integrity-failed redemption writes no event.

A designed layout prints as drawn (canvas `1.1.0`, `canvas_print.py`): zones and elements at
their millimetres on A4, A5, Letter, a custom page or an 80/58 mm roll, in either orientation,
with typed styles, copies and marks, pre-printed stationery, text, fields, lines, boxes,
pictures, signatures (with or without a picture), a product table and/or an accounts table,
totals rows (amount in words included) and a tax summary by rate. One manifest per kind
(`domain/print_capabilities.py`, published at `GET /print-capabilities` and frozen in
`contracts/print-capabilities-v1.json`) lists what prints; anything else is refused before a
browser starts, with the same sentence the designer shows when it blocks publishing. Still
refused and named: QR codes and barcodes (no encoder), custom fonts (no byte store), batch,
expiry and MRP columns (a Purchase bill records none), a tax summary grouped by HSN, the
outstanding-balance total and shared components.

## Goods, pictures, rolls and previews (2026-11-04, `purchase-pdf@4`, `purchase-a4@3`)

Designer plan §8 R1–R5 ([production plan](invoice-designer-production-plan.md#8-purchase-production-readiness-agreed-2026-11-04)).

**What changed in the output.** Product and Mixed bills print (the B24 shape: every goods
line is the stock line it brings in; any other goods shape is refused before the owner is
asked). A goods line prints its HSN, quantity with its unit and rate; services print their
SAC. A rate priced per more than one unit prints with its pricing unit ("5.00 / 100"), and a
quantity or rate finer than the company's display places prints exactly rather than rounded.
The standard layout swaps its *Base amount* column for HSN/SAC, Qty and Rate when a bill
has goods, and every bill prints its amount in words (English, Indian or Western grouping by
the company's digit grouping). Both versions moved for that, so **deploy Design and Vouchers
together** (Design names `purchase-a4@3`; an older Design's `@2` is refused with "Purchase
standard layout version is unavailable", and jobs frozen under `purchase-pdf@3` fail as
`SOURCE_INTEGRITY` and are generated again).

**Where each fact comes from.** Quantity and rate are the saved bill's own (the accepted
calculation hash covers them). HSN/SAC is what the line was taxed under: the calculation's tax
evidence for an unposted bill, the posted supply fact for a posted one. The unit's symbol is
read from Catalog's stock facts with the actor's own rights, and only when the print asks
(`include_labels`); a symbol the actor may not read prints nothing, and a symbol withheld after
generation stops the old PDF from being delivered, like every other label. For a posted bill
whose product can no longer be read, the bill still prints without unit symbols. Fixed with
this: a posted goods supply fact now records its HSN in `classification_code` (it recorded
none before, because goods evidence names it `hsn`, not `sac`); bills posted earlier keep the
empty value.

**Contract order.** `voucher-execution-client` is 0.5.0: optional `include_labels` and
`base_unit_label` on the stock facts, optional `lines` on the print facts. Deploy Catalog, then
Accounting, then Vouchers; an older reply still validates (no labels, no lines), so a
Vouchers deployed first prints goods without HSN or unit symbols until Accounting follows.

**Pictures.** Design's signed print resolution carries the bytes of every image the layout
names (its own or the tenant's assets only, read by the service-derived key and checked
against the digest measured at upload), or the reason an image cannot print: withdrawn
(deactivated), larger than 512 KB, all pictures together larger than 640 KB, or missing (an
unreadable or digest-mismatched stored file is reported as an operator fault). The
bounds exist because the resolution travels in the platform's signed service framing, which
caps a body at 1 MiB. Vouchers checks each picture again (strict base64, size, digest, PNG/
JPEG/WebP signature) and embeds it as a `data:` URI; the page's CSP allows `img-src data:` for
designed layouts only and the browser still has no network. A withdrawn picture refuses the
print with its reason rather than printing the bill without it: publish a version without it,
or re-activate it.

**Rolls.** `THERMAL_80MM` and `THERMAL_58MM` print as one continuous PDF page: the child lays
the page out at the roll width in print media, measures it, and sets the page length to the
content (whole millimetres, at most 5,000 mm). A roll has no page footer, so it names its bill
(status, number, supplier) at its end. ESC/POS and ZPL output are not built.

**Layout previews.** `POST /vouchers/{id}/print-jobs` accepts `layout_preview: {template_id,
version_id}`. The PDF uses that saved design version, published or not, and says "Layout
preview · not for use" on every copy and in every page footer. It needs
`design.template.read` for the company besides the print permissions, and `design.asset.read`
too when the previewed layout carries pictures (they may appear on no published version),
each checked when the job is created and again on every download. Design resolves only a version of a non-archived template
of this company or the tenant, designed for Purchase or for any kind; anything else is 404 to
Vouchers and "this design version cannot be previewed" to the person.

**Budgets** (`tests/test_purchase_print_budget.py`). A 200-line bill builds its HTML in under
a second on every layout, and the real browser renders a 200-line mixed bill on the standard
and on a designed two-table layout well inside the 60 s render deadline (asserted under 45 s; 6–7 s on an idle machine, browser
start included), with every line, the totals and the words present and the header repeated.

**Operations runbook.**

| Symptom | Cause | Action |
|---|---|---|
| "this Purchase's goods lines do not match its stock lines" | A goods line without its stock line (an older draft shape) | Open the bill and save its goods again; it then calculates and prints. |
| "Purchase standard layout version is unavailable" | Design and Vouchers deployed out of step | Deploy both at the same release. |
| "an image on this layout has been withdrawn / is larger than …" | Asset deactivated, or over the print bounds | Choose another picture or a smaller one in the designer and publish. |
| "Purchase print layout service is unavailable" | Design down, signature/scope mismatch, or a resolution over 1 MiB | Check Design health and the shared print secret/scopes; then the layout's pictures. |
| Job `FAILED` with `RENDER_TIMEOUT` | Browser start or render over the deadline | Check VM load and Chromium; a 200-line bill renders in seconds. |
| Unit symbols missing on goods | Older Accounting/Catalog, or the actor may not read unit symbols | Deploy the 0.5.0 contract order; check field policies on units. |
| Non-Latin text prints as boxes | The VM lacks fonts for that script | Install the script's fonts (for Indian scripts, the Noto Sans families) on the print VM; templates are one language each (D5) and print text exactly as typed. |

## Release checks still required

- Connect and review the entry button after the parallel UI work settles.
- Complete the combined Console build and authenticated browser-to-broker-worker test
  under the deployment configuration. Unit/native API tests are not that deployment test.
- Review OS/database/RabbitMQ grants, sandbox launch and private-volume backup/recovery
  on the VM. No VM deployment has been performed by the local implementation work.
- Full custom-canvas parity and signed Design render-evidence synchronization remain
  pending; browser `/renders` writes stay closed.

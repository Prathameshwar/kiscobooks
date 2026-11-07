# Product serial configuration, masters and create/edit review

Repair update: all 12 findings and three workflow gaps have implemented fixes.
See [serial repair status and verification](serial-fixes-todo.md) for current
evidence and the outstanding standard Vitest gate. The sections below preserve
the original review findings and their before-repair evidence.

Reviewed 2026-11-07 against the current local working tree, including the batch
repairs already present and concurrent product-management restoration. This is a
review: application code, existing repair status and VM deployment were not changed.

Scope: company serial capability, inventory-template/identifier-profile policy,
product activation, identifier master creation/edit, Simple and Advanced product
serial opening, product-linked/company serial registration and hold/lifecycle edit,
and the Purchase handoff to prepared serials.

## Consolidated findings

Twelve findings: five high priority and seven medium priority. High priority means
unrecoverable/uncertain command identity, incomplete published configuration, or
an opening failure after product creation/activation. Native validation generally
rejects bad identities; the client defects below do not demonstrate corrupted stock.

| ID | Priority | Area | Finding |
| --- | --- | --- | --- |
| S01 | High | Config/master | Serial tracking can be authored and published without an identifier profile |
| S02 | High | Advanced create | Serial validation omits IMEI checksum, configured slots/types and printable length |
| S03 | Medium | All create flows | Client normalization differs from native Unicode casefold and length rules |
| S04 | Medium | Advanced create | Duplicate detection omits native whitespace trimming |
| S05 | High | Advanced multi-SKU | Company-namespace duplicates are checked separately for each SKU |
| S06 | High | Advanced batch serials | Native field errors can disappear from the editable form |
| S07 | Medium | Advanced final review | Review shows counts without the entered identifiers or unit/batch mapping |
| S08 | Medium | Advanced optional slots | Optional identifier slots become required and have no individual removal action |
| S09 | Medium | Config/create | All-optional profiles and zero-identifier physical units have inconsistent contracts |
| S10 | Medium | Standalone create | Required markers force early slots even when any allowed slot satisfies the minimum |
| S11 | High | Standalone create/edit recovery | Uncertain save identity survives retries only while the component remains mounted |
| S12 | Medium | Identifier-profile edit | UI and field metadata offer code changes which native validation always rejects |

### S01 — Serial tracking without an identifier profile

`InventoryRules` validates that an identifier profile requires serial tracking,
but does not validate the inverse. `InventoryRevisionInput(serial_tracking=True)`
with no profile succeeds, and `inventory_templates.requirements()` returns it
unchanged. Inventory revision publication calls this same validation before setting
`published_at`; `invalid_identifier()` also excludes null profile IDs. Product
requirements check the serial base quantity without adding a missing-identifier
requirement. Simple options and Advanced/native serial preparation subsequently
reject the incomplete configuration.

Reproduction: the native probe calls inventory authoring validation with
`{"serial_tracking": true}` and receives `identifier_profile_id=None`.

Impact: an apparently valid published stock policy can block Simple creation,
or leave an Advanced/activated product unable to register physical serial units.

Repair direction: require an active, complete, supported identifier profile at
publication and activation when serial tracking is enabled. If incomplete draft
templates remain allowed, expose their missing requirements explicitly.

Sources: [inventory rules](../apis/catalog/src/catalog/domain/profiles.py:108),
[template validation](../apis/catalog/src/catalog/tasks/inventory_templates.py:48),
[publication](../apis/catalog/src/catalog/tasks/commercial_history.py:763),
[activation requirements](../apis/catalog/src/catalog/tasks/product_requirements.py:220),
[Simple admission](../apis/catalog/src/catalog/tasks/simple_serial_preparation.py:31).

### S02 — Advanced serial validation is substantially weaker than native validation

`openingErrors()` checks identifier counts, nonempty values and duplicate text.
It does not enforce IMEI checksum/digit format, printable/normalized length,
allowed identifier types, unique type/slot pairs, or configured slot bounds.
For example, IMEI `123456789012345` passes the Advanced check but fails native
checksum validation. Two serial values `A` and `B` both in slot 1 also pass the
Advanced check under a two-slot requirement and fail native validation.

The editable controls provide some length/slot restrictions for normal typing,
but restored draft values and IMEI entry still reach these gaps. Advanced opening
preflight runs against the created/activated SKU, so failure can occur after the
product definition has already been created.

Repair direction: use one complete client validator aligned with the shared native
identifier contract before starting creation, and retain native admission checks.

Sources: [Advanced validator](../mfes/apps/console/app/lib/advanced-product-opening.ts:69),
[native validator](../clients/voucher-execution/src/voucher_execution/identifiers.py:48),
[Advanced native preflight](../apis/catalog/src/catalog/tasks/advanced_creation_opening.py:198).

### S03 — Unicode normalization differs across UI and native identity

Simple and standalone validators use NFKC plus lowercase; Advanced additionally
uses locale-default lowercase. Native identity uses NFKC, trim and Unicode
`casefold()`, followed by a second length check. `SS` and `ß` are accepted as
distinct by the clients but are the same native identity. Simple checks the raw
length: 41 `ﬃ` ligatures fit its 120-character limit but expand to 123 characters
under NFKC and fail native validation. JavaScript UTF-16 length also does not
exactly represent the native character-count contract.

Impact: late rejection, confusing duplicate messages and inconsistent behavior
between otherwise identical create paths. Native uniqueness remains enforced.

Repair direction: define and test the same normalization/version/length contract
for all clients; include casefold expansion and Unicode length examples.

Sources: [Simple validator](../mfes/apps/console/app/components/SimpleProductSerials.tsx:24),
[standalone validator](../mfes/apps/console/app/lib/stock-tracking-command.ts:159),
[Advanced validator](../mfes/apps/console/app/lib/advanced-product-opening.ts:75),
[native normalization](../clients/voucher-execution/src/voucher_execution/identifiers.py:29).

### S04 — Advanced whitespace duplicates escape the pre-create check

The Advanced duplicate key normalizes and lowercases the value without trimming
it. ` ABC ` and `abc` pass `openingErrors()`, while native normalization makes
both `abc` and rejects them. Simple and standalone already trim for this check.

Repair direction: normalize the exact identity submitted to the owner before
testing uniqueness. Preserve the display value separately if needed.

Sources: [Advanced identity key](../mfes/apps/console/app/lib/advanced-product-opening.ts:75),
[native normalization](../clients/voucher-execution/src/voucher_execution/identifiers.py:30).

### S05 — Advanced misses company-scoped duplicates across SKU openings

The Advanced `identifiers` set is created inside the per-SKU loop. Two SKU
openings can therefore each contain the same COMPANY serial/IMEI and pass the
review. Native opening validation and collision checks are also performed one
SKU opening at a time, rather than validating the entire proposed opening set
before creating/activating the product. Native database uniqueness rejects the
later registration; an earlier SKU can already have completed its opening.

Reproduction: two SKU openings, each with COMPANY serial `SAME`, produce no
client validation errors. The underlying unique constraint includes company,
identifier type, namespace and normalized value.

Repair direction: validate the complete draft across SKU openings using the
configured namespace. COMPANY rules span SKUs; MANUFACTURER_SKU rules retain
their SKU scope. Preflight the complete set before creation/physical effects.

Sources: [per-SKU validator](../mfes/apps/console/app/lib/advanced-product-opening.ts:29),
[native per-opening check](../apis/catalog/src/catalog/tasks/advanced_creation_opening.py:196),
[physical uniqueness](../apis/accounting/src/accounting/models/stock_tracking.py:112).

### S06 — Advanced batch-serial errors are not shown where they can be fixed

`AdvancedOpeningSerials` accepts no error prop and renders no inline field errors.
The parent review excludes every path containing `.batches.` from its error
notices. A native error such as
`opening.skus.0.batches.0.serials.0.identifiers` consequently appears neither
beside the identifier nor in the parent notice area. Client serial errors also
flatten batch serial rows into a generic `serials.<index>` path, losing the batch
and original physical-row association.

Reproduction: render the real batch serial review with a native field error;
the error text is absent. This compounds the previously recorded Advanced
recovery field-error loss (U08); the form omission remains even if the error map
reaches the component correctly.

Repair direction: retain SKU/batch/unit/type/slot paths throughout validation and
recovery; render/focus the matching control and provide an accessible fallback
summary for errors which have no control.

Sources: [serial control](../mfes/apps/console/app/components/AdvancedOpeningSerials.tsx:7),
[parent error filtering](../mfes/apps/console/app/components/AdvancedOpeningReviewStep.tsx:29),
[flattened errors](../mfes/apps/console/app/lib/advanced-product-opening.ts:68).

### S07 — Final Advanced review does not expose serial identities

The final review's opening section shows quantity, cost and a total serial count.
It omits the identifiers and their physical-unit/batch association, including
identifiers on other SKU tabs. The editable section elsewhere still contains the
values, but the final review summary does not allow verification of the actual
identities being committed.

Repair direction: include a bounded readable identity summary for each SKU,
batch and unit, with an edit link to the exact row. Respect field visibility.

Source: [opening review](../mfes/apps/console/app/components/AdvancedOpeningReviewStep.tsx:65).

### S08 — Optional Advanced slots are presented as mandatory

For min=1/max=2, adding the optional second slot renders it with `required`.
There is no remove-slot action, only removal of the entire physical unit. The
validator also treats every added blank slot as an invalid identifier. A user
cannot easily return to the valid one-identifier state without removing/re-entering
the unit. Profiles allowing a minimum in any permitted slot are not fully
expressible through this UI, which initially creates the first `min_count` slots.

Repair direction: distinguish minimum count from specific mandatory slots;
allow empty optional slots to be omitted and optional slots to be removed without
discarding the physical unit.

Source: [Advanced slot controls](../mfes/apps/console/app/components/AdvancedOpeningSerials.tsx:8).

### S09 — All-optional profiles have inconsistent zero-identifier behavior

Identifier-profile creation accepts requirements with min_count=0 for every
type. Advanced can add a physical unit with an empty identifier list and
`openingErrors()` accepts it. `SimpleSerialInput` and native `SerialPrepare`
require at least one identifier; Simple UI explicitly rejects the same empty
unit. The profile minimum and the physical registration minimum are therefore
different without an adequate UI explanation or aligned Advanced validation.

Repair direction: make the physical-unit identity requirement explicit across
configuration and clients. Decide whether to forbid profiles with no mandatory
type, or retain optional types while clearly enforcing at least one identifier
overall. Do not silently change the published meaning of existing profiles.

Sources: [profile rule](../apis/catalog/src/catalog/domain/profiles.py:42),
[Advanced validation](../mfes/apps/console/app/lib/advanced-product-opening.ts:70),
[Simple schema](../apis/catalog/src/catalog/schemas/simple_product_creation.py:42),
[native registration](../apis/accounting/src/accounting/schemas/stock_tracking.py:89).

### S10 — Standalone required markers contradict allowed slot selection

Standalone creation sets `required={slot <= rule.min_count}`. Under min=1/max=2,
slot 1 is marked mandatory, although slot 2 alone satisfies the native count
rule and standalone body validation. The form uses `noValidate`, so this is an
incorrect required/a11y indication rather than a proven save rejection.
Simple already handles this count-vs-slot distinction better.

Repair direction: mark individual fields required only when all slots are
required; otherwise display the minimum count for the type and validate the
group, allowing any configured slot to satisfy it.

Source: [standalone slot marker](../mfes/apps/console/app/components/StockTrackingPage.tsx:875).

### S11 — Uncertain save recovery is lost on reload/unmount

Standalone serial registration and lifecycle edits retain body/key only in
`useServiceCommand` component refs. An uncertain response locks the current
form and same-mount retry correctly reuses the key. A reload/unmount discards
that receipt; entering the same registration again generates a different key.
Neither a durable recovery record nor an owner status-reconciliation path is
exposed by this screen.

Reproduction: first registration returns 503; unmount/remount and re-enter the
same values; the second body is identical but the idempotency key differs.

Impact: the first registration may have committed and later attempts conflict,
or the first Identity capability reservation may remain pending while a new
operation is started. The newly added first-use reservation logic preserves an
uncertain operation deliberately, making exact-key recovery particularly important.
The same volatile hook is used for serial hold/lifecycle edits; this probe
reproduced registration, not every lifecycle transition.

Repair direction: retain a scoped recoverable operation before sending and
reconcile/replay its exact body/key after reload. Account for sign-out/company
changes and avoid persisting sensitive identifiers without an appropriate policy.

Sources: [volatile command receipt](../mfes/apps/console/app/lib/service-resource.ts:34),
[serial editor retry](../mfes/apps/console/app/components/StockTrackingPage.tsx:574),
[first-use protection](../apis/accounting/src/accounting/tasks/tracking_features.py).

### S12 — Identifier-profile code edit is offered but always rejected

Identifier-profile update metadata leaves `code` writable; the editor and
`identifierBody()` submit changed codes. Native `validate_identifier_header()`
rejects a changed code whenever requirement rows exist. Valid profile creation
always creates those rows, so a normally created profile cannot use the code
edit the form offers. The editor explains immutable requirements but does not
explain/lock the profile's immutable code.

Reproduction: the real editor renders an enabled Code input using saved native
field metadata; the native header guard rejects a changed code for a profile
with saved requirements.

Repair direction: mark profile code readonly for update and omit it from changed
requests, keeping the replacement-profile guidance consistent with native policy.

Sources: [update metadata](../apis/catalog/src/catalog/api/field_metadata.py:197),
[editor editable keys](../mfes/apps/console/app/components/UnitsIdentifiersEditor.tsx:98),
[native header guard](../apis/catalog/src/catalog/tasks/identifier_policy.py:101).

## Workflow gaps, distinct from confirmed defects

1. **Unused identity correction.** Serial edit intentionally permits only hold,
   release, retire and reactivate. Identifier values and batch assignment are
   immutable. There is no controlled correction/replacement workflow for a
   never-received unit entered with the wrong serial or batch. Retiring a unit
   does not remove its identifier uniqueness reservation. This is an intentional
   native rule and a workflow gap, not permission to edit used identities directly.
2. **Bulk/scanner entry in the current management screen.** The restored
   `StockTrackingPage` creates one physical unit at a time and has no bulk paste
   or explicit scanner queue/review flow. Simple/Advanced support multiple opening
   units, but that does not address repeated standalone registration after product
   creation. Generic scanner-as-keyboard input is not equivalent to a managed queue.
3. **Purchase serial creation handoff.** Live `PurchaseStockDetails` selects
   existing prepared units. Unlike its batch chooser, it has no serial create action
   in that flow. Users must register units in another screen and return/select them.
   This is a usability gap; native receipt still requires prepared identities.

These gaps need a concrete workflow decision before implementation, particularly
any correction of immutable identifiers or retention of uncertain commands.

## Verified controls and limitations

- Catalog serial validation/creation suites: **13 passed**.
- Accounting tracking-domain, identifier-check and tracking suites: **21 passed**.
- New real React/JSDOM observation runner: **12 checks passed**, reproducing the
  client defects and comparing the allowed slot-count behavior. Remote calls and
  product-mode/Next integration are mocked; UI controls and local policy functions
  are real. These are bad-behavior observations, not fixed-behavior regression tests.
- Native observation runner: **6 groups passed**, covering incomplete serial
  configuration, all-optional profile/schema mismatch, native slot-2 acceptance,
  Unicode/trim/length rejection, checksum/duplicate-slot rejection and immutable
  profile-code enforcement. Authoring/header probes exercise validation functions;
  they do not claim a newly executed database publication or migration rehearsal.
- The native probe passes Ruff; the UI probe passes Node syntax checking.
- Existing tests cover permission/field denial, company context, native duplicate
  identity, serial registration, hold/lifecycle version checks and replay. The
  native owner remains the authority for stock, uniqueness, audit and receipt.
- Serial-only and batch+serial modes, integer base quantities and product-linked
  management navigation are present. No extra serial selling-price dimension is
  expected by the governing design; product/batch prices remain appropriate.
- Native serial identifiers/batch assignment are intentionally immutable after
  registration. Absence of arbitrary PATCH is consistent with the approved design.
- Manual security/correctness review found no additional demonstrated tenant
  isolation bypass in the inspected paths. This is scoped evidence, not a complete
  security audit, global coverage measurement or deployed-VM verification.
- Native database uniqueness remains enforced when UI normalization misses a
  collision. Separate first-use capability fixes already recorded in the batch
  repair ledger were not counted again as open serial findings.

Reproduce from repository root:

```powershell
node docs/testing/serial-review/ui-probes.cjs
& apis/catalog/.venv/Scripts/python.exe docs/testing/serial-review/native-probes.py
```

The original batch repair todo remains unchanged. This review introduces no claim
that the serial findings have been fixed and no VM update.

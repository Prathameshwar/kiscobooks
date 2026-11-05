# Product commercial note removal review

The product creation "Tax and price source / reason" was a free-text authoring
note, not an input to tax or price calculations. It is removed from the shared
simple/family UI, client state/validation/payload, native assignment/draft and
bulk adjustment and coordinated release binding contracts, detail schemas, field
registry and three ORM columns.
Catalog OpenAPI and the generated client are synchronized.

Catalog migrations 0211, 0212 and 0213 each execute one column DROP. Their
downgrades recreate the non-null column shape with empty defaults;
deleted text needs backup recovery. Native tests cover the complete Catalog
upgrade/downgrade/re-upgrade chain and populated fixtures retaining IDs, exact
amounts and selections. The schema parser now understands explicit column drops
and MySQL's implicit nullable declarations in existing revisions.

An old API still validates non-empty price notes when reconstructing definitions.
Reverting to that release therefore also needs the backed-up note text restored;
the empty-default column downgrade alone is not full application recovery.

## Local database execution

The configured local `catalog` database was at 0210. A private native dump of all
three affected tables was created before changing it. The dump retains binary
introducers for UUID values and contains all three table definitions. It stays
in ignored `.test_artifacts`, outside published documentation.

The application account correctly refused ALTER. The existing configured root
default had no password; the owner's previously supplied local root credential
was then used only for the Alembic DDL process. No application grant, database
credential file or application data row was changed manually.

Upgrade through 0213 succeeded. Read-only inspection using the application
account verified the note absent from `catalog_tax_binding`, `item_price_draft`
and `item_price`, while official `tax_rate` evidence remains.

## Verification

- Fail-first UI regression: omission of the note blocked a valid native price
  setup before the implementation. It passes after removal.
- Final targeted backend checks: 32 distinct cases across retired-contract,
  initial family setup and simple-product suites; one command-budget timeout
  during concurrent testing passed on isolated rerun with the normal budget.
- UI: 151 distinct affected cases across creation, group/type drawers, pricing
  masters and statutory tax UI, plus two simple setup cases. The six tax-release
  timing failures in a parallel run all passed in the isolated 11-case suite with
  one worker. Reusable commands select one worker to avoid test-run contention.
- Native MySQL: two migration cases passed; four static migration checks passed.
- Catalog OpenAPI and generated client consistency, console TypeScript, strict
  mypy for 12 changed modules and three review modules, Ruff and scoped whitespace
  checks passed. Contracts and console types were checked again after correcting
  coordinated bindings.
- Wider pricing/tax/import/audit regression run: 264 passed, six failed. All six
  failing cases subsequently passed after the fixes or isolated normal-budget
  reruns described below. The final 32-case review suite passed, including all
  master usage, registry, coordinated publication, mixed-kind default and tax
  activation cases selected for review. These collections overlap; their counts
  must not be summed as distinct coverage.

## Regression findings and fixes

The wider backend run completed with 264 passes and six failures. Review found
two implementation defects: coordinated tax release bindings still required the
retired note, and master usage raised an AttributeError while scanning five
registered promotion models missing from the Catalog model exports. Removed the
obsolete coordinated field and exported those existing native models. Strict
note rejection covers ordinary rule bindings and newly created classification
references. Existing master-usage tests cover the full supported master registry,
pagination, reference field denies and lifecycle access.

The pricing read fixture also omitted verified customer membership. Its corrected
test seeds active company-owned membership, including a verified default customer,
and verifies that an unverified other-company buyer is rejected. Runtime customer
authorization stays unchanged; all three pricing-read suite cases passed.

The two remaining failures were command-budget contention. The exact tier DELTA
case passed in isolation with its normal budget. The activation case passed
in the final tax review run. These results are recorded separately from the first
wider run rather than describing that run as an uninterrupted pass.

## Final manual reviews

The simplify/security-review commands are not installed in this session. Manual
equivalents checked CLAUDE.md sections 5 and 6 and the actual changes.

Simplify findings: no replacement defaults, hidden inputs, duplicated storage or
unused note state remain. Native handlers, forms, templates and serializers derive
from the updated contracts. Removed the old field from relevant test fixtures
without deleting official tax, reference-cost, MRP or guard evidence.

Security/correctness findings: tenant/company filters, object-level access,
native field denies, publication permissions, source-version/fingerprint review,
exact Decimal quantities/rates, predecessor history, audit/outbox atomicity and
idempotent replay remain in their existing paths. No authorisation was widened.
The retained official evidence uses existing event schemas and consumers; those
contracts are unaffected. Historical audit records and already committed bulk
effects remain retained; uncommitted staged inputs with the retired field need
a fresh corrected preview.

No further implementation defect was found in these manual reviews. Identity,
Catalog and the gateway are offline after the VM shutdown. Authenticated live UI
acceptance remains pending service startup; local UI/API tests and the database
migration are complete. This is not a claim of logged-in live acceptance.

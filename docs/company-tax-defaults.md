# Automatic company tax starter masters

## 2026-10-31 generic defaults: decision and phases

The user authorized generic business-neutral tax choices and complete India GST
starter rates, including exemption where appropriate. Replace the commodity
examples with a version-two pack. Keep the original pack as historical evidence.

1. Verify the current notified rate schedules and write failing regressions for
   generic choices, distinct nil/exempt/non-GST treatments and safe existing data.
2. Add an explicit native `classification_scope` (`SPECIFIC` by default, `ANY` for
   manually selected generic templates), its additive migration, field contract
   and resolver guard. Classification and product-kind checks remain mandatory;
   an empty specific applicability list must still block completion.
3. Provision version-two generic goods/service choices through the existing
   enrollment/bootstrap transaction. Rename only untouched version-one starter
   labels to rate plus HSN/SAC; preserve IDs, applicability, rates and user edits.
   Generic choices never assign themselves to products or establish eligibility
   for an exemption, concession, input credit or reverse charge.
4. Verify provisioning, exact CGST/SGST/UTGST/IGST components, resolution,
   permissions, isolation, migration rollback guard, generated contracts and the
   running local company. Record checks and manual simplify/security review.

Rate sources include Notification 9/2025-Integrated Tax (Rate), its 19/2025
amendment effective 2026-02-01 (removing the 28% goods schedule), service rate
Notification 8/2017 and its amendments, and goods/service exemption notifications.
October 2026 amendments were checked for their 2026-11-01 effective date. A starter
pack supplies selectable rates, not a universal statutory classification engine.
Zero-rated export/SEZ treatment is not equivalent to nil-rated or exempt supplies.

## Scope and delivery plan

1. Verify official source documents and commit a versioned India GST starter
   manifest under seeds/. Include common HSN/SAC classifications, treatment
   categories, explicitly applicable rules, and exact dated rates for intra-state,
   intra-UT and inter-state supplies. Do not use the legacy lookup's undated rate
   suggestions or assign a global product tax rule.
2. Add bounded, company-scoped Catalog provisioning triggered by verified Identity
   enrollment/source refresh. Company tax configuration determines applicability.
   Reuse the company policy lock, native tax schema/domain validators, audit and
   Accounting publication outboxes. Existing records, edits and retirements are
   preserved; repeats and concurrent runs are safe. Cover future companies,
   configuration changes, and an explicit operator backfill for existing companies.
3. Integrate the company wizard/readiness feedback using existing UI components.
   Verify creation and retry behavior, permissions, disabled/non-India companies,
   official evidence, exact components, existing edits and cross-company isolation.
   Keep schemas, migrations (if needed), generated contracts and scripts synchronized.
4. Review correctness/security and UX twice, fix findings, then verify live company
   creation plus existing-company provisioning and record actual results.

Only the implemented India GST adapter is included. Other jurisdictions are not
given Indian tax records. A common HSN/SAC classification does not establish a
product's statutory treatment; users choose the applicable prepared rule explicitly.
Published tax history continues to use the existing replacement/withdrawal workflow.

## Implementation

The canonical packaged manifest is
`apis/catalog/src/catalog/seeds/tax_defaults_v2.json`. It contains 5 categories,
13 classifications (8 HSN headings and 5 SAC codes), 20 generic goods/service rules
and 48 rate publications with 80 exact components. The immutable version-one pack
is retained for evidence and safe legacy label comparison. The evidence identifies the
downloaded official documents by reference, URL and SHA-256. No runtime government
website dependency or undated lookup recommendation is used.

Automatic provisioning runs after the existing source worker has authenticated and
activated a complete enrolled-company snapshot. It runs again on refresh, including
after taxation is enabled later. It requires an active Indian company configured
with `default_tax_system=gst_in`; GST is not a separate invented feature flag.
Source activation commits independently, so a failed seed cannot discard a valid
Identity lease. Provisioning uses one company lock and transaction. It batches
existing-record discovery, creates only missing identities, preserves entire
existing rule/rate graphs and stages native audit and Accounting publication
outboxes atomically. System writes are attributed to the Catalog system provisioner;
they do not manufacture a user or permission grant.

`POST /v1/companies/{company_id}/tax-defaults/bootstrap` is a closed empty-body,
idempotent user command requiring company-scoped tax read/manage/publish authority
and native field-write checks. Results identify the company. The Console wizard
waits for this step before opening the company, reuses the generated response type,
and preserves the company ID and request key when retrying remaining steps.
Both Console proxy boundaries allow only the exact bootstrap route and method.

Company setup now waits up to 30 attempts for the specific Catalog 503
`source_unavailable` response while enrollment/feature changes synchronize. It
reuses the single shared replay-safety rule, freezes request bodies and keys, and
retries only reads or keyed writes. Permission failures, other outages and keyless
creates are not automatically retried. Exhaustion retains the normal retry action.

The operator backfill command and deployment notes are in [seeds/tax](../seeds/tax/README.md).
Masters hides the GST cards when the verified company tax setting is disabled or
belongs to another jurisdiction. Existing tax screens retain their ordinary
creation, name/status editing, dated revision and withdrawal controls. The legacy
lookup's `gst_rate_default` remains as a deprecated null field rather than exposing
obsolete undated values.

The initial delivery added no tables. The generic-template refinement adds Catalog
0215 and `tax_rule.classification_scope`, with default `SPECIFIC` for existing rows,
a native enum check and an online downgrade guard. This selection policy belongs
to Catalog; the existing Accounting publication payload is unchanged. Rule scope
cannot be patched after creation. Native field-read/write policy applies, and the
safe audit vocabulary records the selected scope. OpenAPI, the generated Catalog
SDK and audit matrix are regenerated. The permission catalogue is unchanged.

The generic goods rates are 0.1%, 0.25%, 1.5%, 3%, 5%, 12%, 18% and 40%; service
rates are 1.5%, 5%, 7.5%, 12%, 18% and 40%. Conditional entries are labelled;
0.1% is the merchant-exporter procurement concession, not zero-rated exports.
Special valuation, ITC restrictions, cess and reverse charge remain reviewed
configuration, not inferred from a chosen rate. Nil-rated goods/services have
zero-valued GST components; exempt/non-GST choices carry no rate rows and retain
the native exemption-reason requirement on treatment binding.

For existing companies, only exact unedited version-one rules with unchanged
applicability and unrevised three-context history receive generic rate plus HSN/SAC
labels. Updated names increment rule versions and emit audit/publication events in
the provisioning transaction. Existing IDs, bindings, classifications and rate
history are retained; user changes and revisions are preserved. New generic rules
are added separately, never substituted into existing bindings. Repeats do not
change audit counts or company policy generation.

## Reviews and verification

Review 1 covered official evidence, applicability, exact component arithmetic,
history preservation, configuration gates, tenant/company isolation and atomic
audit/publication. Fixed findings: obsolete lookup recommendations, a nonexistent
GST feature assumption, and unnecessary repeated database lookups. Components use
stable ordering across worker processes and never round an invalid storage scale.

Review 2 covered the real company wizard, proxy allowlists, response ownership,
source freshness, replay safety and deployment. Fixed findings: the missing
company-setup proxy entry, company identity verification on bootstrap responses,
review conflicts retaining successful receipts, and the new-company source
synchronization race. Manual simplify/security/correctness reviews were performed
because the slash commands are unavailable. No unresolved findings remain for this
starter-pack scope.

- Native tax/source regressions: 46 passed; the expanded/current defaults suite
  passed 9 tests, including later enabling of GST and browser-independent enrollment.
- Final Console regression run: 277 passed. Console TypeScript, generated Catalog
  SDK freshness, Catalog OpenAPI/field/audit contract freshness, Ruff and strict
  typing of the seven changed tax/source modules passed. Whole-Catalog typing has
  one unrelated existing `no-any-return` error in `tasks/definition_revisions.py:58`.
- Live Catalog model/database verification passed at migration 0208: 180 model
  tables, no missing/extra tables or native column differences; Alembic check passed.
  No migration is required for this data-provisioning change. The operator backfill
  command also completed successfully against the configured installation.
- Live tenant3 verification created a fresh company through the full UI, loaded all
  four master tables immediately, and verified repeated bootstrap and same-key replay.
- Existing enrolled companies were automatically provisioned. The first verification
  company exposed the source race; its remaining setup was completed with the same
  keys, and the second full creation completed after the wait fix.
- Browser checks covered all four directories and Masters navigation, plus 18
  category/classification/rule theme/viewport combinations without overflow or errors.
- A native rule-name edit succeeded, and subsequent provisioning preserved both
  the edited value and its row version without creating additional rules or rates.
- The live Company Administrator seed was missing four current shipped permission
  rows and correctly blocked creation. The existing deployment seed was dry-run,
  applied and checked again with zero further changes. Custom roles were preserved.

Private test reports, synthetic fixture IDs, screenshots and downloaded evidence
are under ignored `.tools/extension-masters/tax-defaults-*` paths.

## 2026-10-31 generic-pack verification and review

The historical verification above describes the original pack. The current
generic-pack delivery uses Catalog migration 0215 and pack `IN_GST_STARTER_2`.

- Failing regressions first reproduced the old commodity pack, missing native
  template scope and missing UI guidance. The initial corrected backend batch
  passed 15 tests; the tax UI/policy/page batch passed all 76 tests.
- Native MySQL verification passed the new scope/default/guard and complete
  schema provisioning checks. The final native batch passed three tests, including
  the earlier adoption-marker rollback guard against its own revision.
- Migration 0215 was applied to the local Catalog database; the managed Catalog
  service and enrollment source worker were restarted. Verified enrollment
  backfill added the 20 generic choices and renamed the nine untouched old labels.
  All 27 old rate rows retained their IDs, dates and versions. Repeated bootstrap
  produced no additional audit records or policy-generation changes.
- Whole-Catalog strict typing passed for 358 source files; full Console TypeScript
  checking passed. Ruff and whitespace checks passed for this change. OpenAPI,
  audit-matrix and generated Catalog client freshness checks passed.
- Final directory regressions passed all four directory cases, including the
  scope column and guidance. Rule authoring passed separately with the explicit
  `SPECIFIC` default in its command. Its deadline was increased from 15 to 30
  seconds after a host-load timeout; assertions were retained. A malformed Windows
  wrapper invocation that collected unrelated files was stopped and replaced with
  a direct invocation of the same installed Vitest runner.
- The two added API cases passed: an explicit classification remains mandatory
  when a generic rule is selected, and later classification restrictions on a
  generic rule are rejected. The full migration-structure checker also passed.
  An additional slow coverage-instrumented rerun was stopped in favor of these
  focused checks; no new coverage percentage is claimed.
- Authenticated browser verification passed against the running tax-rules table:
  all 20 generic choices, the scope column and treatment guidance were visible;
  representative current taxable, nil-rated, exempt and non-GST labels matched,
  and no commodity-specific starter names remained. Cold development compilation
  and temporary Catalog timeouts required retries. The final check waited for
  login hydration before entering credentials and used the live company data.

Manual equivalents of `/simplify` and `/security-review` were completed because
those slash commands are unavailable. Reviewed the company lock and transaction,
tenant/company filters, native field authorization, immutable scope, explicit
classification and treatment requirements, exact decimal components, source
evidence, audited legacy-label updates and guarded downgrade. An oversized rate
history fails closed during legacy detection. The migration test's SQL-prefix
assertion now uses literal expected strings. No unresolved correctness or security
findings remain within this scope. Conditional eligibility, cess, reverse charge
and zero-rated exports continue to require their own reviewed configuration.

### Database/model/script synchronization recheck

The follow-up check compared the running local Catalog database with the complete
service metadata, including types and server defaults: all 182 tables matched,
with zero Alembic schema differences. The database, model readiness constant and
migration tree all reported `0215`. The native scope column's length, nullability,
default and named check were also inspected directly. Three generated-expression
warnings were reviewed: the database adds parentheses, identifier quoting and
character-set introducers to equivalent expressions; no corrective DDL is needed.

Permanent schema regressions now include the scope default and constraint name.
The schema-default, constraint and non-container migration checks passed 16 tests
(one container test deselected). Ruff and whitespace checks passed. OpenAPI, audit
matrix and generated Catalog client freshness checks passed, and the normal
`python -m seeds.tax --env-file start/win/env/catalog.env` command completed against
the configured installation using the canonical version-two pack. Manual sync and
security review found no additional application changes required.

# Product and party edit experience

## Phases

1. Review live product/SKU, product-family, party and supplier edit screens and
   existing native update/field contracts. Identify layout, identity context,
   validation, recovery and return-navigation gaps.
2. Reuse FormLayout, shared sections, field controls and guarded navigation for
   focused edit screens. Preserve immutable/read-denied values, update only changed
   fields and retain exact requests for uncertain retries. Keep stock, lifecycle,
   tax/pricing and related-record management in their existing native workflows.
3. Exercise edit validation, saves, unchanged values, field restrictions, errors,
   recovery and dirty navigation. Review desktop/mobile in the shared themes and
   verify authorised live edits/readback using the isolated tenant3 test records.
   Finish correctness/security and presentation reviews with fixes.

No new service, model, migration, permission key or financial behavior is planned.

## Delivered behavior

All three phases are complete. Product/SKU edits group identity, sales/purchase
flags and unit/quantity controls. Family edits group identity, brand/model and
description; company custom fields retain their native conditional validation.
Unrelated classification tabs are hidden on product edit pages. The base unit is
displayed read-only and never added to a patch. Saved-record summaries and the
header identify the current record without disclosing fields denied by metadata.
Configuration loading/failure and protected controls retain explicit explanations.

Party and supplier edit pages identify the saved shared party, show edit guidance,
and preserve customer/supplier identity rather than restarting creation. Back and
Cancel return to the current detail with its original directory context. Supplier
edit saves retain their supplier detail destination and never restart supplier setup.
The existing guarded navigation still requires discarding unsaved work before leaving.

Save is disabled initially. Normalized unchanged product/party edits produce a
No changes message without sending a version-only mutation. Corrected 422 field
errors clear as editing resumes. Uncertain results retain the existing frozen input,
request and idempotency key; 403/version-conflict recovery remains guarded. Product
updates also permit a metadata-authorised custom-only edit, without resending denied
native fields. This does not change creation eligibility or native update authority.

## Review findings and fixes

The first correctness review produced seven failing regression cases before fixes:
unstructured product sections/context, custom-only edit eligibility, stale product
and party validation errors, supplier edit guidance/return navigation and whitespace
party saves. These now pass. Native status-dependent controls, scope/field metadata,
exact decimal quantities, version checks and receipt verification remain authoritative.
Unreachable legacy family-creation markup was removed from the non-creation branch.

Presentation review found long names squeezed by the default ReviewList label column
inside a narrow sidebar. Its shared stacked variant now uses the full panel width.
The final browser review waited for reference/configuration loading, checked readable
summary widths and confirmed no horizontal overflow. No app-specific CSS was added.

Manual simplification and security reviews covered CLAUDE.md sections 5 and 6;
the slash-command tools are unavailable. No auth, company scope, lifecycle, posting,
audit, pricing or stock boundary was widened, and no remaining issue was found within
this edit scope. Backend contracts/models are unchanged, so regeneration and database
migrations are unnecessary.

## Verification

The broad focused Console run passed 252 tests across ten suites. The additional
configuration-loading regression passed in the 13-case edit suite; final targeted
checks cover that suite and the 30-case creation wizard. Shared wizard/review,
primitives and tokens passed 46 tests. TypeScript and whitespace checks passed.

Live tenant3 verification used the existing isolated Catalog enrollment verification
company and synthetic records. Four native saves/readbacks checked SKU name, family
multiline description, party multiline notes and supplier legal name. Every request
contained only expected_version and the changed field. Product client validation
focused the required field without a write; confirmed saves reached the proper detail
and reload never resubmitted them. No stock, price, balance or financial document was
created or posted. There were no browser errors in the successful end-to-end run.

Twenty-four final read-only captures covered all four edit screens in light, dark
and ledger themes at 1440px and 390px. They confirmed full-width stacked summaries,
disabled unchanged saves, no overflow and no writes. Private evidence remains in
ignored .tools/extension-masters; no credentials are recorded in this document.

# Serial repairs

Authorized 2026-11-07: implement fixes from the serial review. VM updates remain
deferred. Preserve concurrent work and the separate batch repair ledger.

## Phases

1. S01: enforce complete serial identifier policy in publication/activation.
2. S02–S05 and S09: one canonical client identifier validator; complete-draft
   namespace checks before creation, with native owner guards retained.
3. S06–S08 and S10: exact field errors, readable final review and optional slots.
4. S12: align immutable profile-code metadata and edit controls.
5. S11: retain scoped uncertain command identity through reload and reconcile exact
   retries; verify create and lifecycle recovery and tenant/company separation.
6. Review the three workflow gaps using the existing immutable identity rules;
   deliver concrete supported handoffs without weakening native stock authority.

Each phase starts with failing fixed-behavior regressions and finishes with
affected tests/checks green. Update contracts/consumers when affected. No database
model, permission or monetary effect is changed without matching native checks.

| Finding | Repair | Status |
| --- | --- | --- |
| S01 | Complete serial policy on publication/activation | Complete |
| S02 | Complete IMEI/type/slot/printable validation | Implemented; local checks pass |
| S03 | Canonical Unicode normalization and length | Implemented; local checks pass |
| S04 | Trim identities before duplicate detection | Implemented; local checks pass |
| S05 | Whole-draft namespace uniqueness before creation | Implemented; local checks pass |
| S06 | Preserve and display exact serial field errors | Implemented; local checks pass |
| S07 | Show unit identifiers and associations in final review | Implemented; local checks pass |
| S08 | Allow optional slots to be omitted/removed | Implemented; local checks pass |
| S09 | Require at least one identity across optional types | Implemented; local checks pass |
| S10 | Align minimum-count markers with native slot rules | Implemented; local checks pass |
| S11 | Recover exact uncertain command after reload | Implemented; local checks pass |
| S12 | Keep identifier-profile code immutable in edit | Implemented; local checks pass |
| Gap 1 | Audited unused-identity replacement workflow | Implemented; local checks pass |
| Gap 2 | Standalone bulk/scanner registration | Implemented; local checks pass |
| Gap 3 | Purchase serial creation handoff | Implemented; local checks pass |

## Evidence

Record failed-before and passed-after verification here. Original observation
probes assert defects; convert their assertions as repairs are delivered.

### Phase 1

- Three regressions failed before repair, including a real incomplete-policy
  publication. After repair all three plus affected policy/publication/product
  requirements suites pass: 18 tests. Valid serial and nonserial policy paths pass.
- Authoring/publication require an identifier profile for serial tracking. Retained
  incomplete references fail closed, and lifecycle validity includes null-profile
  serial revisions. No model/schema migration or response shape changed.

### Phases 2–4

- Simple, Advanced and standalone creation use one canonical validator: native
  whitespace, NFKC/casefold, Unicode character limits, printable characters,
  IMEI checksum, configured type/slot/counts, and namespace uniqueness across
  the whole draft. Generated casefold/category tables use Python's Unicode
  version; newer browser Unicode assignments cannot bypass native validation.
- Optional slots can be omitted and individually removed. All-optional profiles
  still require an identifier for each physical unit. Minimum counts can use any
  allowed slot. Final review lists identifiers with SKU/batch/unit associations.
- Native opening errors include the physical unit path; progress/recovery retain
  that map and return to the right SKU and opening form. Unmapped errors remain
  visible. Identifier-profile codes are read-only in metadata and editor requests.
- Regression groups failed before repair and pass afterward. Affected Catalog
  opening/Simple serial suites passed 22 tests; the two new exact-field tests
  passed after correcting their test assertion to use the error envelope. The
  identifier/metadata/field-path group passed 7 tests. The six new Catalog repair
  tests passed together. These runs overlap; do not add their counts.

### Phase 5

- Tab-session recovery retains the exact request/body/key before transmission,
  scoped by tenant, actor, company, resource and record. Corrupt or unavailable
  storage blocks dispatch. Unknown outcomes cannot be cleared or replaced by a
  changed body. Recovery keeps its identity through authorization loss and busy
  conflicts; a verified receipt clears it.
- Reload tests cover registration and lifecycle changes, including the old action
  and expected version after native state has advanced. Retrying does not depend
  on metadata completing its load. Read-denied retained values are masked.
- Closing the browser tab ends session storage. Recovery is not a server-side
  operation-status service; native history and uniqueness remain authoritative.

### Phase 6 and agreed decisions

- User explicitly selected preservation of old identity and an audited
  replacement. The later nonproduction-data clarification permits routine
  implementation choices; it does not change that selected identity policy.
- Replacement is a strict, paired option on native serial registration. Accounting
  locks and checks the original unit/version/SKU/batch, rejects held, retired or
  ever-received units, and retires the original atomically with creation. Both
  histories and audit outboxes link the old/new opaque IDs. Original identifiers
  stay reserved; superseded units cannot be reactivated. Conflict rollback leaves
  the original unchanged. Current object and field authority is rechecked on replay.
- Inventory → Serials → Register or scan units provides a queue of at most 200
  units. Scanning uses Enter; additional configured slots remain editable before
  submission. Each unit has a retained key, exact body and progress checkpoint.
  Lost responses and crashes before checkpoints replay the original unit key.
  Known rejected units can be reviewed/corrected with new keys, preserving units
  already registered. Unknown outcomes remain locked.
- Purchase exposes the same registration UI to serial read/manage users with
  editable stock fields. It appends selected references without changing the
  destination or existing selections. A native ID/receipt-eligibility query
  rechecks each unit before handoff, preventing reuse of already-received queues.
  Registration itself creates no quantity, value or receipt.
- Native DTO/query changes are reflected in Accounting OpenAPI and its generated
  TypeScript client. No database model, migration, permission key or audit event
  type was introduced; existing tracking events carry the linked IDs.

### Verification and remaining release gates

- `docs/testing/serial-fixes/regressions.cjs`: 21 passing groups using real React,
  JSDOM and shared UI controls. `workflows.cjs`: 10 passing workflow groups covering
  scanner queues, partial reload, checkpoint failure, duplicate validation,
  malformed scope, deterministic correction, replacement, lifecycle recovery,
  Purchase permissions/handoff and already-received rejection.
- The Purchase ID eligibility filter is allowlisted and UUID-validated at the
  browser proxy as well as typed and scoped at the native owner.
- Final Accounting replacement/tracking/identifier suites: **30 tests passed**.
  Native review probes now assert repaired behavior and pass. Catalog checks,
  scoped Ruff/mypy, Console TypeScript, Accounting OpenAPI and generated-client
  checks pass.
- Added CI Vitest regressions for identity normalization, command recovery and
  registration. **Vitest startup is blocked locally by `spawn EPERM` in esbuild**;
  the standard Vitest run remains an outstanding release gate. The standalone
  React runners provide local verification but do not claim that Vitest ran.
- `/simplify` and `/security-review` commands are unavailable here. Manual review
  against CLAUDE.md sections 5 and 6 checked native scope, field denies, idempotency,
  concurrent stock locks, immutable identity, atomic audit/rollback, bounded
  storage/queries and owner boundaries. Findings from that pass were fixed; no
  remaining finding was identified in these changed paths.
- VM updates remain deferred. No deployment, commit or publication performed.


Latest deployment status: the fixes were built and deployed on 2026-11-07. See [VM deployment verification](vm-latest-build-2026-11-07.md). Earlier deferred/local-only statements above record the prior implementation stage.

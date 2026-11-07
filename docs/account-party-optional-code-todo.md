# Optional Account and Party codes

Authorized by the user: Code is optional in Masters and Purchase creation. Blank
codes receive a unique value of 6–8 characters. Existing codes remain unchanged.
VM updates remain deferred.

1. Native regressions and repair: optional/blank create inputs, eight-character
   generated codes under the existing company transaction lock, collisions,
   mandatory party ledger defaults, exact retries and field authority.
2. Masters and Purchase UI: optional code fields, no name-based automatic entry,
   omit blank values, and clear field-specific validation for manual values.
3. Contract/client updates, affected checks and security/correctness review.

| Task | Status |
| --- | --- |
| Native optional code and generation | Done |
| Masters Account/Party forms | Done |
| Purchase supplier/expense-account forms | Done |
| Clear code validation and duplicate messages | Done |
| Contracts, regression checks and final review | Done |
| Follow-up review: generation boundaries, rollback, API/UI parity | Done |

Decision: generate eight uppercase letters/digits at the native owner, never in
the browser or from the name. Keep manual codes as trimmed printable text up to
40 characters, preserving leading zeros, case, spaces and punctuation. Generated
Party codes must also be available for their default ledger Account. The native
changed-field policy applies to generated Code exactly as to a manual Code.

Verification:
- Fifteen native regressions cover blank/omitted codes, Account and Party exact
  replay, default ledger collisions, manual identities, specific validation and
  duplicate errors, optional metadata and generated-code write authority.
- The affected native suites passed 82 cases initially; one ledger-validation
  regression was corrected and passed its targeted rerun.
- Eight local React/JSDOM groups passed, using the actual shared form controls
  and Purchase drawers. They cover optional Masters fields, blank-code requests,
  immutable edit display and inline `code`, `party.code`, `ledger.code` recovery.
- Accounting mypy/Ruff, Console TypeScript and OpenAPI/generated-client checks
  passed. Vitest cannot start locally because esbuild returns `spawn EPERM`;
  the Vitest tests were updated and local UI evidence uses the standalone runner.

Run local UI evidence: `node docs/testing/account-party-code/regressions.cjs`.
No database migration or VM update was performed.

Follow-up review findings:
- Fixed: manual Unicode codes were counted as UTF-16 units in the UI, while
  Accounting counts Unicode characters. Masters and Purchase now accept the
  same 40-character limit, including supplementary characters, and cap input
  without splitting characters. Confirmed the UI regression failed before the fix.
- Confirmed: retired codes are reserved; repeated allocation collisions stop
  after 20 candidates; failed allocation can be retried safely with the same key.
- Confirmed: generated Party codes avoid both existing Party identities and
  Account codes, and a blank custom ledger code defaults to the Party code.
- Confirmed: Code field write denies on Party or Account cannot be bypassed by
  generation, and rejected creation leaves no partial records or audit events.
- No further functional or security defects found in the reviewed changes.

Follow-up evidence: 18 backend cases passed across the main review run and the
Unicode API regression; eight React/JSDOM groups passed with Unicode form and
input checks added. TypeScript, Ruff/mypy, OpenAPI/client checks and whitespace
checks passed. Vitest was retried and remains blocked at startup by `spawn EPERM`.


Latest deployment status: the fixes were built and deployed on 2026-11-07. See [VM deployment verification](vm-latest-build-2026-11-07.md). Earlier deferred/local-only statements above record the prior implementation stage.

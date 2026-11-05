# Non-party account creation review

## Scope and phases

The requested enhancement covers GENERAL, CASH, BANK, TAX, INVENTORY_CONTROL
and ASSET_CONTROL. PARTY continues to use the existing linked-party flow.

1. Verify native kind rules, shared creation routes and supporting profile routes.
   Add regressions for filtered creation and visible profile guidance, then fix
   those gaps using existing shared components and current native permissions.
2. Exercise every non-party kind through native lifecycle tests and the live
   tenant3 company scope, including bank/tax profile prerequisites. Preserve
   company references, field permissions, exact amounts and command retry rules.
3. Review navigation, validation, permissions and responsive presentation twice;
   apply any findings and record the resulting checks here.

All account kinds share `/accounting/accounts/new`. Bank and tax profiles are
separate supporting forms, not independent ledger identities. This work does
not change storage, public schemas, permission definitions or account balances.

## Findings

- Starting a new account from a kind/group-filtered directory discarded those
  selections. Preserve permitted native selections without overriding the
  linked-party account kind.
- Bank/tax draft prerequisites were explained in the editor but their profile
  navigation was buried among general detail actions. Surface the matching
  permitted profile area beside the draft guidance.
- Live review found company-bank creation had a native API but no Console form.
  Add a scoped supporting form linked from bank-profile setup. Keep account
  numbers write-only in the UI and use the existing Identity schema. Identity's
  bank-create API does not deduplicate commands: do not replay an uncertain
  create; direct the user back to review available company banks first.
- The live installation also lacked Identity's bank-encryption settings. The
  development env generator now initializes a durable AES key for fresh and
  existing env files that have neither setting. It preserves configured keys and
  refuses incomplete/invalid settings. Production secret management is unchanged.
  Explicit development env regeneration also retains bank data keys; rotation
  remains an audited native operation.

## Verification and review result

- All six non-party kinds were created from their filtered Accounts directory,
  edited and activated through the real tenant3 browser session in the isolated
  Catalog enrollment verification company. The saved native records retain their
  selected kind and group with no party attributes.
- Bank and tax activation were rejected before their profiles existed. The bank
  flow created a fictional company bank through the new form, returned to profile
  setup, selected that bank, saved the profile and activated the ledger. The tax
  flow used an explicit OTHER duty/scheme/component and OUTPUT_PAYABLE purpose;
  no statutory registration or tax rate was fabricated.
- The supporting company bank is encrypted at rest: one encrypted row and zero
  plaintext account-number/IBAN values in the verification company. Identity was
  restarted through its owned launcher; `/health/ready` returned 200.
- Nine native Accounting account-completion tests passed, including all six
  non-party lifecycle cases, incompatible heads, required profiles, presentation
  edits, active structural protection, retirement, all supported duties and exact
  rounding checks. No financial documents or balances were posted.
- The 431-test focused UI/policy suite passed before the final additional locked
  bank-profile regression; all 37 affected account-kind, related-action and bank
  tests then passed. TypeScript and Ruff checks passed. Launcher/encryption tests:
  35 passed, including fresh/legacy env initialization, repeated setup, explicit
  regeneration preserving existing data keys, and rejection of partial settings.
- Live visual/interaction review passed 54 combinations: all six account-kind
  forms, bank/tax profile details and the supporting company-bank form, across
  light/dark/ledger themes at desktop/mobile sizes. No document overflow or browser
  runtime errors; mobile currency-menu bounds, Escape focus return and footer
  reachability passed. All six active-account forms protect kind while allowing
  name edits. Active bank-profile edits do not offer company-bank creation.

Review one corrected lost kind/group context and incomplete bank setup navigation.
Review two checked field and company authority, key retention, return-path safety,
ambiguous-write recovery, protected profiles, and responsive presentation; its
findings were fixed and covered by regressions. Manual simplify/security reviews
found no remaining issue in this change. Dedicated slash-command review tools were
not available. Native scope, permissions, validation and audit remain authoritative.

The existing Identity and Accounting public schemas/models/migrations are unchanged;
the new form consumes the existing generated BankWrite/BankItem types. No schema or
client regeneration is required. Test credentials and live evidence stay ignored
under `.tools`; no generated encryption key is tracked.

## Decision log

- 2026-10-27: Retain one Accounts creation screen with native kind-specific fields;
  bank/tax profiles remain supporting forms. Provide company-bank creation within
  bank setup using independent company read/update authority. Do not replay a
  company-bank create when its result is uncertain because the existing native
  API has no command receipt. Preserve bank data keys even during dev-env rebuilds.

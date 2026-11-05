# Purchase type invoice defaults

User report, 2026-10-31: creating an ordinary Purchase voucher type and opening
`/vouchers/new/purchase` reports that account purchase bills are not configured.

The type creator omits policy for a new type, producing the generic policy with
no invoice configuration. The connected Purchase entry requires a typed invoice
policy. For a new STANDARD Purchase type with no submitted policy, initialize
the native InvoicePolicy defaults. Keep explicit policies and clones unchanged.
Company configuration still intersects these defaults and can restrict access.

Delivery: reproduce the missing-policy defect; implement and test defaults,
replay, field-set projection and explicit-policy/clone preservation; repair the
reported existing local type through the authorized revision API; verify real
Purchase entry. No execution flags or immutable revisions are changed in place.

The user's existing `PUR` type had no invoice policy at revision 2. The normal
revision API added it as revision 3. The user clarified that this type is for
account/expense bills; revision 4 removes the incompatible mandatory ITEMS and
CHARGES sections, preserving required PARTIES/REFERENCES/TAX and other rules.

Purchase entry now lists specific mode, supplier, party-limit, section, invoice
and field-write problems. It keeps the type selector available, links to the
selected type and its rules (editing requires type.manage), and explains
incompatible required item lines or disabled mandatory charges. The rules editor
now supports invoice entry and account supply selection, preserving other invoice
limits. Existing current/historical revisions and company restrictions remain.

Verification: fail-first default-policy test; 20 Vouchers type/default/lifecycle
tests passed. The final connected/contract/rules/manage UI suite passed all 93
tests. Full Console TypeScript, Vouchers Ruff and strict mypy passed. A live
browser opened the revised PUR type at /vouchers/new/purchase: Save draft was
available and the configuration warning was absent. The local Vouchers database
was upgraded from 0109 to the current 0110 before restarting the service; no
execution flags were enabled and no financial documents were posted.

Manual CLAUDE.md sections 5/6 review completed in lieu of unavailable review
skills: scoped permission gates and normal audited revision/idempotency APIs
remain; no execution flags enabled, no historical revision overwritten, no
financial floats or new cross-service calls inside financial transactions.

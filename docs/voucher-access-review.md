# Voucher and configuration access review

Requested on 2026-11-01: review tenant administrators, company administrators and
other company users; show or hide menus, cards and voucher actions according to
their current permissions, and allow or deny direct pages consistently.
This continues the agreed navigation plan's company-scoped permission review.
Status: all three phases completed locally on 2026-11-01.

## Phases

1. Trace the canonical role catalogue and documented policies to menu, card,
   list, entry, review, import and configuration checks. Record concrete mismatches.
2. Add failing regression tests, then align presentation and server-page checks
   with existing company grants. Preserve saved-bill review, separation of duties,
   owner authorization, field policies and capability gates.
3. Run affected role and UI checks, TypeScript and live read-only verification;
   review security and simplification, and record results here.

## Policy

Role names and user classification confer no implicit permissions. Live, dated
tenant grants cover company operations; company grants cover their assigned
company. Department grants do not confer company-wide list/configuration access.
Unknown, future and expired grants are denied. Financial admission and company
feature settings remain separate from authorization and preserve historical reads.

| Surface | Required access in target company |
| --- | --- |
| Income, Expense, Inventory, family cards, voucher lists/review | `vouchers.read` |
| New menu and new entry pages | `vouchers.read` and `vouchers.create` |
| Saved Purchase workspace | `vouchers.read`; each action needs its own grant |
| Draft edit | `vouchers.read` and `vouchers.edit` |
| Import page/results | `vouchers.read` and `vouchers.import.read` |
| Import template, staging, validation | `vouchers.import.manage` and `vouchers.create`, in addition to page read access |
| Import commit | `vouchers.import.commit` and `vouchers.create`, in addition to page read access |
| Voucher type directory/detail | `vouchers.read` |
| Create/copy/edit/retire voucher types | `vouchers.read` and `vouchers.type.manage` |
| Print settings/templates | `design.template.read`; manage/routing/publish use their dedicated grants |
| Company configuration | `company.read`; writes require `company.update` and native lifecycle/immutability checks |
| Audit history on a company record | `audit.read` in that record's company |
| Export that record's audit history | `audit.export` in that record's company, in addition to read access |
| Create a company from the empty-company screen | Current tenant-scoped `company.create`; company-scoped grants do not qualify |

Tenant/company administrators manage voucher and print configuration without
receiving implicit voucher creation, approval or posting. Company creators may
also have `stock_operator`; their combined current grants determine actions.
Clerks prepare vouchers, approvers approve/reject, and viewers/auditors read.
Existing Tenant Administrator native finance/opening authority is preserved.

## Findings and verification

Fixed the ungated top-bar New menu, flat Voucher drafts navigation, legacy New
pages mounting without read/create authority, saved Purchase's New link surviving
creation revocation, company-record audit read/export hints borrowing another
company's grants, Import mounting below a denied voucher page, and empty-company
creation borrowing a company-scoped grant. Direct denied pages render the shared
403 state before mounting business components. Saved Purchase review is the
bounded exception to new-page creation authority: only the Purchase route accepts
its verified resume identifier; adding that parameter to another kind cannot
bypass creation access.

The CompanyAccess context carries request-resolved grants for object-level
presentation; it does not replace API enforcement. Company record history applies
its own scoped read/export hints. Existing platform/tenant directories retain
their separate presentation context. No role catalogue or live assignment was
changed. One stale role test was corrected to reflect the documented, previously
approved Tenant Administrator zero-opening authority.

Verification:

- **518 distinct Console tests across 25 suites passed**, including all 22 direct
  kind-list denies, administrator/clerk/approver/viewer/auditor bundles, current
  tenant/company grants, wrong-company/department/missing/expired/future grants,
  creation revocation, imports, print settings and company configuration. The final
  focused run passed **158 tests**. Regression tests reproduced each fixed defect
  before its application change.
- The changed permission modules, provider and voucher pages have **100% lines,
  statements and functions; 94.02% branches** in the focused coverage run. The
  unchanged synthetic Purchase preview route is outside that coverage scope;
  repository thresholds were not changed.
- **111 backend tests passed**: 56 Identity role/assignment checks and 55 Vouchers
  import/configuration/isolation checks, using isolated test fixtures.
- Final Console **TypeScript check passed**; task-file whitespace checks passed.
- **Six live read-only browser checks passed** with the supplied QA account:
  top-bar/family actions, list actions, legacy and generic receipt entry, import
  controls, and company-settings cards. The account has current tenant and
  company grants that permit creation, import and configuration. Other permission
  bundles and denied scopes were verified through automated page/API tests.
  Screenshots were inspected; no live vouchers were created or imported.

The first live audit stopped on an ambiguous test selector matching Purchase's
H1 and H2; selecting the page H1 corrected the harness and the complete run passed.
One broad test run exposed provider-mock coupling and resource-related timeouts;
the grant context was separated from the provider module and affected suites
passed with one worker. Existing company-configuration tests emit React `act`
warnings while passing; no permission or configuration assertion remains failing.

Manual equivalents of `/simplify` and `/security-review` were performed because
those commands are unavailable here. Reviewed CLAUDE.md sections 5 and 6, dated
object scope, classification versus authority, direct-route checks, bounded
Purchase resume, owner reauthorization, import authority and field-policy/export
denies. Existing separation of duties, financial admission, immutable posted facts,
audit/outbox and idempotency contracts are preserved. **No unresolved findings
within this access-review scope.**

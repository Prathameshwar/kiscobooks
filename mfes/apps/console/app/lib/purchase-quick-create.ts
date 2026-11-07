import { accountingRequest } from './accounting-configuration';
import { masterCodeLength } from './accounting-master-code';
import { trackingId } from './stock-tracking-resources';
import type { ServicePage } from './service-resource';
import { cleanGstin } from './gstin';
export { cleanGstin } from './gstin';

/**
 * What the purchase bill needs to create a supplier or an expense account without leaving the page.
 * The rules here are Accounting's own, mirrored only far enough to give a person an answer before the
 * round trip; Accounting still validates and is the authority (CLAUDE.md §5.6).
 */
export const QUICK_CREATE_LIMITS = { code: 40, name: 160, description: 500 } as const;

/** What a successful quick create hands back: enough to select the record, which is then re-verified like any pick. */
export type QuickCreated = { id: string; label: string; meta?: string };
/** Which bill line asked for an account. `apply` fills a staged editor instead of the bill (the mobile line editor). */
export type QuickCreateTarget = { lineKey: string; apply?: (created: QuickCreated) => void };
/** What the connected bill offers its fields; an absent entry means the actor cannot create that record, so no icon. */
export type PurchaseQuickCreate = { supplier?: () => void; account?: (target: QuickCreateTarget) => void; product?: boolean };

/** A starting point for the code, never a rule: "Sharma & Sons Traders" → "SHARMA-SONS-TRADERS". */
export function suggestCode(name: string, max = 24): string {
  const code = name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  if (code.length > max) {
    // Keep a distinguishing numeric suffix when a long name would otherwise suggest the
    // same code for every numbered supplier or account in a series.
    const suffix = code.match(/-([A-Z0-9]*\d[A-Z0-9]*)$/)?.[1];
    if (suffix && suffix.length < max - 1) {
      const prefix = code.slice(0, max - suffix.length - 1).replace(/-+$/, '');
      if (prefix) return `${prefix}-${suffix}`;
    }
  }
  return code.slice(0, max).replace(/-+$/, '');
}

const printable = (value: string) => !/[\u0000-\u001f\u007f]/.test(value);
function text(label: string, value: string, max: number, errors: Record<string, string>, key: string) {
  const trimmed = value.trim();
  if (!trimmed) errors[key] = `Enter ${label}.`;
  else if (trimmed.length > max) errors[key] = `Use at most ${max} characters.`;
  else if (!printable(trimmed)) errors[key] = 'Remove the control characters.';
  return trimmed;
}

function optionalCode(value: string, errors: Record<string, string>) {
  const code = value.trim();
  if (masterCodeLength(code) > QUICK_CREATE_LIMITS.code || !printable(code))
    errors.code = 'Use printable text up to 40 characters; remove control characters.';
  return code;
}

/** The GST status a supplier can be given here; "NONE" leaves the registration for the full supplier form. */
export type GstStatus = 'NONE' | 'REGULAR' | 'COMPOSITION' | 'UNREGISTERED';
export const GST_STATUS_OPTIONS: readonly { value: GstStatus; label: string }[] = [
  { value: 'REGULAR', label: 'Regular' }, { value: 'COMPOSITION', label: 'Composition' }, { value: 'UNREGISTERED', label: 'Unregistered' }, { value: 'NONE', label: 'Add later' },
];
/** Regular and composition suppliers hold a GSTIN; an unregistered one records only the state. */
export const gstinRequired = (status: GstStatus) => status === 'REGULAR' || status === 'COMPOSITION';

export type SupplierDraft = { name: string; code: string; countryCode: string; gstStatus: GstStatus; stateCode: string; gstin: string };
export type SupplierRequestBody = {
  code?: string; name: string; legal_name: string; party_type: 'ORGANISATION'; country_code: string;
  role: 'SUPPLIER'; ledger: Record<string, never>;
  tax_registration?: { scheme: 'GST_IN'; registration_type: Exclude<GstStatus, 'NONE'>; country_code: 'IN'; state_code: string; registration_number?: string };
};

/**
 * One command creates the supplier, its supplier role, its payable account (`ledger: {}` takes Accounting's
 * defaults: Sundry Creditors, company currency) and, for an Indian supplier, its GST registration. Accounting
 * never creates a party without its account, and a supplier without one cannot be billed. The legal name is
 * the name: the full supplier form is where they are told apart.
 *
 * `tax` is whether the actor may record registrations; without it the GST fields are not offered and none is sent.
 */
export function supplierRequest(draft: SupplierDraft, options: { tax: boolean }): { body?: SupplierRequestBody; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const name = text('the supplier name', draft.name, QUICK_CREATE_LIMITS.name, errors, 'name');
  const code = optionalCode(draft.code, errors);
  if (!/^[A-Z]{2}$/.test(draft.countryCode)) errors.country_code = 'Choose the supplier’s country.';
  const registered = options.tax && draft.countryCode === 'IN' && draft.gstStatus !== 'NONE';
  const gstin = cleanGstin(draft.gstin);
  if (registered) {
    if (!draft.stateCode.trim()) errors.state_code = 'Choose the supplier’s state; GST is charged by state.';
    if (gstinRequired(draft.gstStatus) && !/^[0-9]{2}[0-9A-Z]{13}$/.test(gstin)) errors.registration_number = gstin ? 'A GSTIN has 15 characters: 2 digits for the state, then the PAN and a check code.' : 'Enter the supplier’s GSTIN.';
  }
  if (Object.keys(errors).length) return { errors };
  return {
    errors,
    body: {
      ...(code ? { code } : {}), name, legal_name: name, party_type: 'ORGANISATION', country_code: draft.countryCode, role: 'SUPPLIER', ledger: {},
      ...(registered ? { tax_registration: {
        scheme: 'GST_IN' as const, registration_type: draft.gstStatus as Exclude<GstStatus, 'NONE'>, country_code: 'IN' as const, state_code: draft.stateCode.trim(),
        ...(gstinRequired(draft.gstStatus) ? { registration_number: gstin } : {}),
      } } : {}),
    },
  };
}

export type ExpenseAccountDraft = { name: string; code: string; groupId: string; description: string };
export type ExpenseAccountRequestBody = {
  code?: string; name: string; group_id: string; kind: 'GENERAL'; currency_mode: 'BASE';
  posting_policy: 'MANUAL_ALLOWED'; inventory_affected: false; description?: string;
};

/** Exactly what an account bill accepts as an expense line: general, postable, not stock, under an expense head. */
export function expenseAccountRequest(draft: ExpenseAccountDraft, groups: readonly ExpenseGroup[]): { body?: ExpenseAccountRequestBody; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const name = text('the account name', draft.name, QUICK_CREATE_LIMITS.name, errors, 'name');
  const code = optionalCode(draft.code, errors);
  const description = draft.description.trim();
  if (description.length > QUICK_CREATE_LIMITS.description) errors.description = `Use at most ${QUICK_CREATE_LIMITS.description} characters.`;
  else if (!printable(description.replace(/[\r\n\t]/g, ' '))) errors.description = 'Remove the control characters.';
  if (!groups.some(group => group.id === draft.groupId)) errors.group_id = 'Choose the group this expense belongs to.';
  if (Object.keys(errors).length) return { errors };
  return {
    errors,
    body: {
      ...(code ? { code } : {}), name, group_id: draft.groupId, kind: 'GENERAL', currency_mode: 'BASE', posting_policy: 'MANUAL_ALLOWED', inventory_affected: false,
      ...(description ? { description } : {}),
    },
  };
}

export type ExpenseGroup = { id: string; name: string; head: string };
type Row = { id: string; company_id?: string; name?: string | null; nature?: string | null; head_id?: string | null };

async function every(company: string, resource: 'account-heads' | 'account-groups', signal?: AbortSignal): Promise<Row[]> {
  const rows: Row[] = [];
  let cursor: string | null = null;
  // Two hundred a page, three pages: a chart of accounts with more than 600 groups has stopped being a picker.
  for (let page = 0; page < 3; page += 1) {
    // Heads have no lifecycle, so Accounting refuses a status filter on them (422); groups do, and only active ones are offered.
    const params = new URLSearchParams({ ...(resource === 'account-groups' ? { status: 'ACTIVE' } : {}), limit: '200', ...(cursor ? { cursor } : {}) });
    const result: ServicePage<Row> = await accountingRequest<ServicePage<Row>>({ path: `/v1/companies/${company}/${resource}?${params}`, signal });
    if (!Array.isArray(result.items) || !result.page || result.items.length > 200
      || result.items.some(row => !trackingId.test(row.id) || (row.company_id && row.company_id !== company)))
      throw { status: 502, message: 'The account groups could not be verified for this company. Try again.' };
    rows.push(...result.items);
    cursor = result.page.has_more ? result.page.next_cursor : null;
    if (!cursor) break;
  }
  return rows;
}

/**
 * The heads of the EXPENSE nature, by id. A head's list row is lean — it does not carry the nature — so each head is
 * read once; a chart has a handful (assets, liabilities, equity, income, expenses), and a long list is not a chart.
 */
async function expenseHeads(company: string, signal?: AbortSignal): Promise<Map<string, string>> {
  const listed = await every(company, 'account-heads', signal);
  if (listed.length > 50) throw { status: 502, message: 'The account heads could not be verified for this company. Try again.' };
  const heads = await Promise.all(listed.map(async row => {
    const head = await accountingRequest<Row>({ path: `/v1/companies/${company}/account-heads/${row.id}`, signal });
    if (head.id !== row.id || (head.company_id && head.company_id !== company)) throw { status: 502, message: 'The account heads could not be verified for this company. Try again.' };
    return head;
  }));
  return new Map(heads.filter(head => head.nature === 'EXPENSE').map(head => [head.id, head.name ?? '']));
}

/** The groups an expense account can sit under: active groups whose head has the EXPENSE nature, A–Z. */
export async function loadExpenseGroups(company: string, signal?: AbortSignal): Promise<ExpenseGroup[]> {
  // Heads and groups are independent reads: asked together, the drawer is ready after the slower, not after both.
  const [heads, listed] = await Promise.all([expenseHeads(company, signal), every(company, 'account-groups', signal)]);
  const groups = listed
    .filter(group => group.name && group.head_id && heads.has(group.head_id))
    .map(group => ({ id: group.id, name: group.name!, head: heads.get(group.head_id!)! }));
  return groups.sort((a, b) => a.name.localeCompare(b.name));
}

/** Indirect Expenses is where service and overhead bills belong; anything else is the person's call. */
export function defaultExpenseGroup(groups: readonly ExpenseGroup[]): string {
  return groups.find(group => /^indirect expenses?$/i.test(group.name.trim()))?.id ?? (groups.length === 1 ? groups[0]!.id : '');
}

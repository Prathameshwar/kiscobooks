import { vi } from 'vitest';
import { allowedProductRequest } from '../app/lib/product-request-policy';

/**
 * A stand-in for the Vouchers and Accounting services that answers with the shapes and the query
 * rules of the real ones, and is reached through the Console's real proxy allowlist.
 *
 * The Purchase page's other tests mock `serviceCall`, so they cannot notice a path the proxy refuses,
 * a query the service has no parameter for, or a response with a different shape from the one the page
 * expects. This is the one place those are checked together. Where it encodes a service rule, the
 * source it was read from is named, so a change there shows up as a failing test here.
 */
export const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
export const COMPANY = id(1), TYPE = id(2), TYPE_REVISION = id(3);
export const SUPPLIERS = [
  { id: id(10), name: 'Sharma Office Supplies', code: 'SUP-0007' },
  { id: id(11), name: 'Bright Lights Electricals', code: 'SUP-0012' },
];
// A supplier's accounts are numbered from its own id so a test can name them: its payable, a second payable (older data that
// a repair is for) and, for a party that is also a customer, its receivable.
export const payableOf = (supplier: string) => id(Number(supplier.slice(-12)) + 1000);
export const secondPayableOf = (supplier: string) => id(Number(supplier.slice(-12)) + 2000);
export const receivableOf = (supplier: string) => id(Number(supplier.slice(-12)) + 3000);
export const EXPENSES = [{ id: id(20), name: 'Office expenses', code: 'EXP-101' }, { id: id(21), name: 'Printing and stationery', code: 'EXP-131' }];
const GROUP = id(900), HEAD = id(901), ADVANCE = id(950);

// apis/accounting/src/accounting/schemas/query.py MasterQuery (+ ListQuery, AccountQuery) and subledger.py FinanceQuery.
const LIST = ['limit', 'cursor', 'q', 'sort'];
// MasterQuery: `role` is one of these four and `status` one of these three (a pattern); ListQuery: `limit` is 1 to 200. Anything else is a 422.
const ROLES = ['CUSTOMER', 'SUPPLIER', 'OTHER', 'BROKER'], STATUSES = ['DRAFT', 'ACTIVE', 'INACTIVE'];
// apis/accounting schemas/lists.py AccountListItem: the lean projection of an account in a list. Nothing outside it is returned (the detail has more).
export const ACCOUNT_LIST_KEYS = ['id', 'company_id', 'code', 'name', 'group_id', 'kind', 'party_id', 'party_role', 'currency', 'currency_mode', 'system_key', 'status', 'sort_order'];
const MASTER = [...LIST, 'code', 'status', 'role', 'party_id', 'group_id', 'parent_id', 'account_id', 'head_id', 'payment_term_id', 'address_id', 'registration_id', 'as_of', 'alias', 'kind', 'purpose', 'direction', 'section_id', 'deductee_type'];
const QUERY_KEYS: Record<string, string[]> = {
  parties: MASTER, 'party-roles': MASTER, accounts: [...MASTER, 'currency', 'currency_mode'],
  'open-items': [...MASTER, 'period_id', 'journal_id', 'journal_line_id', 'debt_item_id', 'credit_item_id', 'posting_date'],
};

// apis/accounting schemas/ledger.py BalanceQuery: exactly these query keys (extra='forbid').
const BALANCE_KEYS = ['basis', 'as_of', 'account_id', 'party_id', 'currency'];

// apis/vouchers api/duplicate_bills.py: exactly these query keys; anything else is 422.
const DUPLICATE_KEYS = ['party_id', 'party_account_id', 'bill_reference', 'document_date', 'exclude_voucher_id'];
const reference = (text: string) => text.trim().replace(/\s+/g, ' ').toLowerCase();

type Json = Record<string, any>;
export type FakeServices = {
  requests: { service: string; method: string; path: string; body?: any; key?: string }[];
  vouchers: Map<string, Json>;
  /** What the next `invoice-acceptance` does: accept (default) or refuse as the owner would. */
  failNext(match: (method: string, path: string) => boolean, status: number, message: string): void;
  completeExecution(): void;
  /** The company revises the voucher type: new writes are validated against this revision. */
  reviseType(revisionId: string): void;
  /** Another bill already recorded for a supplier, as the duplicate check sees it. */
  seedBill(input: { supplier?: string; ledger?: string; billReference: string; status?: string; documentDate?: string }): string;
  /**
   * A supplier as Accounting holds it: `payables` active party accounts in the SUPPLIER role (the rule is exactly one; 0 and 2 are the
   * older data the party ledger repair exists for), and, when `alsoCustomer`, the CUSTOMER role and its receivable account too.
   */
  seedSupplier(input: { name: string; code: string; payables?: 0 | 1 | 2; alsoCustomer?: boolean }): { id: string; name: string; code: string; payables: string[]; receivable: string | null };
  /** Hold every ledger-balance answer until the returned function is called; a request abandoned meanwhile is recorded in `cancelled`. */
  holdBalances(): () => void;
  /** Paths of ledger-balance requests the page abandoned while they were held. */
  cancelled: string[];
};

/** A 64-hex digest of the calculated content, so a preview of one bill is not accepted for another. */
export function digest(text: string): string {
  let state = 0x811c9dc5, out = '';
  for (let round = 0; round < 8; round++) {
    for (const ch of text) state = Math.imul(state ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    out += state.toString(16).padStart(8, '0'); state = (state + round + 1) >>> 0;
  }
  return out;
}

const page = (items: unknown[]) => ({ items, page: { next_cursor: null } });
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const refuse = (status: number, message: string) => reply({ error: { code: status === 422 ? 'validation_failed' : 'error', message } }, status);

function metadata(typeRevision: string, approvalRequired = true): Json {
  const props = ['party_line_key', 'party_account_id', 'party_account_version', 'bill_reference', 'due_date', 'tax', 'supplier_declared_total', 'supplier_difference_reason', 'rounding_account_id', 'rounding_account_version', 'allocations', 'tenders', 'components'];
  return {
    native: { properties: {
      invoice: { anyOf: [{ properties: { ...Object.fromEntries(props.map(key => [key, {}])), supplies: { items: { properties: Object.fromEntries(['line_key', 'account_id', 'account_version', 'description', 'amount', 'supply_kind'].map(key => [key, {}])) } } } }] },
      ...Object.fromEntries(['parties', 'references', 'posting_date', 'document_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields', 'credit_terms_date'].map(key => [key, {}])),
    } },
    custom: [], layouts: [],
    configuration: { kind: 'PURCHASE', profile: 'STANDARD', type_revision_id: typeRevision, policy: { schema_version: 2, approval_required: approvalRequired, allowed_modes: ['ACCOUNTS'], allowed_party_roles: ['SUPPLIER'], invoice: { allowed_supply_kinds: ['ACCOUNT'], manual_discounts_allowed: false, charges_allowed: false, supplier_difference_limit: '0.0000' } } },
  };
}

/** `balances` seeds what each supplier's payable account has posted; an account without an entry has none. */
export function installFakeServices(options: { typeRevision?: string; approvalRequired?: boolean; balances?: Record<string, { debit: string; credit: string }> } = {}): FakeServices {
  const approvalRequired = options.approvalRequired ?? true;
  let balanceGate: Promise<void> | null = null;
  const cancelled: string[] = [];
  let typeRevision = options.typeRevision ?? TYPE_REVISION;
  const vouchers = new Map<string, Json>(), operations = new Map<string, Json>(), history = new Map<string, Json[]>(), replays = new Map<string, Response>();
  const requests: FakeServices['requests'] = [];
  // The parties and their party accounts. Every base supplier has one payable; `seedSupplier` adds others.
  const parties: Json[] = SUPPLIERS.map(row => ({ ...row, customer: false })), partyAccounts = new Map<string, Json>();
  const rolesOf = (party: Json) => ['SUPPLIER', ...(party.customer ? ['CUSTOMER'] : [])];
  const addAccount = (party: Json, accountId: string, role: 'SUPPLIER' | 'CUSTOMER', label: string) => partyAccounts.set(accountId, { id: accountId, party_id: party.id, party_role: role, name: party.name + ' · ' + label, code: party.code });
  SUPPLIERS.forEach(row => addAccount(row, payableOf(row.id), 'SUPPLIER', 'payable'));
  let seeded = 0;
  const keyed = new Map<string, string>();
  const failures: { match: (method: string, path: string) => boolean; status: number; message: string }[] = [];
  let sequence = 100, executionDone = false;
  const base = `/v1/companies/${COMPANY}`;
  const calc = (voucher: Json) => {
    const total = voucher.invoice.supplies.reduce((sum: number, row: Json) => sum + Math.round(Number(row.amount) * 10000), 0);
    const money = (n: number) => (n / 10000).toFixed(4);
    const { accepted_calculation_hash: _accepted, ...content } = voucher.invoice;
    return { calculation_version: 1, calculation_hash: digest(JSON.stringify([voucher.parties, content])), currency: 'INR', commercial_total: money(total), tax_total: '0.0000', charged_tax_total: '0.0000', rounding: '0.0000', payable: money(total), supplier_difference: null, lines: [], tax_evidence: [] };
  };
  // Same supplier, same reference once trimmed and case-folded, and a bill that still counts (not cancelled, rejected or reversed).
  const matching = (supplier: string | null | undefined, ledger: string | null | undefined, billReference: string, exclude?: string | null) => [...vouchers.values()].filter(row => row.id !== exclude
    && (!!supplier && row.parties?.some((party: Json) => party.role === 'SUPPLIER' && party.party_id === supplier) || !!ledger && row.invoice?.party_account_id === ledger)
    && reference(row.invoice?.bill_reference ?? '') === reference(billReference) && ['DRAFT', 'SUBMITTED', 'APPROVED', 'ISSUED', 'POSTED'].includes(row.status)).reverse();
  const next = (voucher: Json, patch: Json): Json => { const value: Json = { ...voucher, ...patch, row_version: voucher.row_version + 1 }; vouchers.set(value.id, value); return value; };

  function serve(service: string, method: string, path: string, body: any, key?: string): Response {
    const [route, queryText = ''] = path.split('?'), query = new URLSearchParams(queryText);
    const resource = route.slice(base.length + 1).split('/')[0]!;
    // The service takes only the parameters its query schema declares (extra='forbid' → 422), and enum values as declared.
    if (method === 'GET' && QUERY_KEYS[resource] && route === `${base}/${resource}`) {
      const unknown = [...query.keys()].filter(name => !QUERY_KEYS[resource]!.includes(name));
      if (unknown.length) return refuse(422, 'Extra inputs are not permitted: ' + unknown.join(', '));
      if (['parties', 'party-roles', 'accounts'].includes(resource)) {
        const limit = query.get('limit');
        if (limit !== null && !(/^\d+$/.test(limit) && Number(limit) >= 1 && Number(limit) <= 200)) return refuse(422, 'limit must be between 1 and 200');
        if (query.has('role') && !ROLES.includes(query.get('role')!)) return refuse(422, 'role must be CUSTOMER, SUPPLIER, OTHER or BROKER');
        if (query.has('status') && !STATUSES.includes(query.get('status')!)) return refuse(422, 'status must be DRAFT, ACTIVE or INACTIVE');
      }
      if (resource === 'open-items' && query.has('direction') && !['DEBT', 'CREDIT'].includes(query.get('direction')!)) return refuse(422, 'direction must be DEBT or CREDIT');
    }
    // Every money-mutating command takes an Idempotency-Key; a preview only reads (apis/vouchers api/invoices.py).
    if (['POST', 'PUT'].includes(method) && !route.endsWith('/invoice-preview') && !route.endsWith('/recover') && !key) return refuse(422, 'Idempotency-Key header is required');
    // A key is bound to the request it first carried; reusing it for another is refused (platform idempotency, 422 idempotency_key_reused).
    const fingerprint = JSON.stringify([method, route, body ?? null]);
    if (key && keyed.has(key) && keyed.get(key) !== fingerprint) return reply({ error: { code: 'idempotency_key_reused', message: 'This Idempotency-Key was used for a different request' } }, 422);
    if (key) keyed.set(key, fingerprint);
    const replayKey = key && method + ' ' + route + ' ' + key;
    if (replayKey && replays.has(replayKey)) return replays.get(replayKey)!.clone();
    const answer = (response: Response) => { if (replayKey && response.ok) replays.set(replayKey, response.clone()); return response; };
    const failure = failures.findIndex(row => row.match(method, route));
    if (failure >= 0) { const [row] = failures.splice(failure, 1); return refuse(row!.status, row!.message); }

    if (route === `${base}/voucher-types`) return reply(page([{ id: TYPE, company_id: COMPANY, kind: 'PURCHASE', profile: 'STANDARD', name: 'Account purchases' }]));
    if (route === `${base}/voucher-capabilities`) return reply({ financial_execution: false, invoice_execution: true, purchase_supporting_files: false, kinds: [{ kind: 'PURCHASE', execution_ready: true }] });
    if (route === `${base}/voucher-types/${TYPE}/field-set`) return reply(metadata(typeRevision, approvalRequired));
    // A party list takes `role` as an active role of the party (tasks/reads.py `listing`: active_party_role).
    if (route === `${base}/parties`) return reply(page(parties.filter(row => (!query.get('q') || row.name.toLowerCase().includes(query.get('q')!.toLowerCase())) && (!query.get('role') || rolesOf(row).includes(query.get('role')!))).map(row => ({ id: row.id, name: row.name, code: row.code, company_id: COMPANY }))));
    const party = parties.find(row => route === `${base}/parties/${row.id}`);
    if (party) return reply({ id: party.id, name: party.name, code: party.code, company_id: COMPANY, status: 'ACTIVE', row_version: 2 });
    if (route === `${base}/party-roles`) return reply(page(parties.filter(row => !query.get('party_id') || row.id === query.get('party_id')).flatMap(row => rolesOf(row).filter(role => !query.get('role') || role === query.get('role')).map(role => ({ id: id(role === 'SUPPLIER' ? 555 : 556), company_id: COMPANY, party_id: row.id, role, status: 'ACTIVE' })))));
    if (route === `${base}/accounts`) {
      if (query.get('kind') === 'PARTY') {
        // tasks/reads.py `listing`: the party's accounts. `role` is the ACCOUNT's own party role (a party that is both a supplier and a
        // customer holds a payable and a receivable), and a BROKER's account role is OTHER. Items are schemas/lists.py AccountListItem,
        // which carries party_role so a caller can check what it was given.
        const role = query.get('role'), wanted = role === 'BROKER' ? 'OTHER' : role;
        return reply(page([...partyAccounts.values()].filter(row => (!query.get('party_id') || row.party_id === query.get('party_id')) && (!wanted || row.party_role === wanted) && (!query.get('status') || query.get('status') === 'ACTIVE'))
          .map(row => ({ id: row.id, company_id: COMPANY, kind: 'PARTY', party_id: row.party_id, party_role: row.party_role, status: 'ACTIVE', name: row.name, code: row.code }))));
      }
      return reply(page(EXPENSES.filter(row => !query.get('q') || row.name.toLowerCase().includes(query.get('q')!.toLowerCase())).map(row => ({ ...row, company_id: COMPANY }))));
    }
    const held = partyAccounts.get(route.slice(`${base}/accounts/`.length));
    if (route.startsWith(`${base}/accounts/`) && held) return reply({ id: held.id, company_id: COMPANY, status: 'ACTIVE', row_version: 3, kind: 'PARTY', party_id: held.party_id, party_role: held.party_role, name: held.name, code: held.code });
    const expense = EXPENSES.find(row => route === `${base}/accounts/${row.id}`);
    if (expense) return reply({ ...expense, company_id: COMPANY, status: 'ACTIVE', row_version: 4, kind: 'GENERAL', inventory_affected: false, group_id: GROUP, posting_policy: 'MANUAL_ALLOWED' });
    if (route === `${base}/account-groups/${GROUP}`) return reply({ id: GROUP, company_id: COMPANY, head_id: HEAD });
    if (route === `${base}/account-heads/${HEAD}`) return reply({ id: HEAD, company_id: COMPANY, nature: 'EXPENSE' });
    if (route === `${base}/open-items`) return reply(page([{ id: ADVANCE, company_id: COMPANY, party_id: query.get('party_id'), role: 'SUPPLIER', direction: 'CREDIT', account_id: query.get('account_id'), currency: 'INR', reference: 'ADV-1', posting_date: '2026-10-01', reversal_date: null }]));
    if (route === `${base}/open-items/${ADVANCE}/balance`) return reply({ item_id: ADVANCE, as_of: query.get('as_of'), currency: 'INR', remaining: '500.0000' });
    // apis/accounting api/ledger.py balance: posted journals up to as_of, debit minus credit; basis BASE needs the company base currency;
    // the party and the account must be the company's own (an unknown one is a 404, as company_object raises).
    if (route === `${base}/ledger/balance` && method === 'GET') {
      const asOf = query.get('as_of'), currency = query.get('currency'), supplier = parties.find(row => row.id === query.get('party_id'));
      if ([...query.keys()].some(name => !BALANCE_KEYS.includes(name)) || !asOf || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !/^[A-Z]{3}$/.test(currency ?? '') || !['BASE', 'ORIGINAL', null].includes(query.get('basis'))) return refuse(422, 'request validation failed');
      if ((query.get('basis') ?? 'BASE') === 'BASE' && currency !== 'INR') return refuse(422, 'base balance requires the company base currency');
      const account = partyAccounts.get(query.get('account_id') ?? '');
      if (query.has('party_id') && !supplier || query.has('account_id') && !account) return refuse(404, 'not found');
      // `balances` seeds what a supplier's first payable has posted; any other account of the company has posted nothing.
      const posted = (account && account.id === payableOf(account.party_id) && options.balances?.[account.party_id]) || { debit: '0.0000', credit: '0.0000' };
      const cents = (text: string) => Math.round(Number(text) * 10000);
      return reply({ as_of: asOf, currency, debit: posted.debit, credit: posted.credit, balance: ((cents(posted.debit) - cents(posted.credit)) / 10000).toFixed(4) });
    }

    if (route === `${base}/vouchers/duplicate-bills` && method === 'GET') {
      const unknown = [...query.keys()].filter(name => !DUPLICATE_KEYS.includes(name));
      if (unknown.length || !(query.get('party_id') || query.get('party_account_id')) || !query.get('bill_reference')?.trim() || !query.get('document_date')) return refuse(422, 'request validation failed');
      return reply({ items: matching(query.get('party_id'), query.get('party_account_id'), query.get('bill_reference')!, query.get('exclude_voucher_id')).slice(0, 5).map(row => ({ id: row.id, status: row.status, document_date: row.document_date, bill_reference: row.invoice.bill_reference, revision_number: row.revision_number })) });
    }
    if (route === `${base}/vouchers` && method === 'GET') return reply(page([...vouchers.values()].filter(row => !query.get('status') || row.status === query.get('status')).map(row => ({ id: row.id, company_id: COMPANY, kind: 'PURCHASE', status: row.status, document_date: row.document_date }))));
    if (route === `${base}/vouchers` && method === 'POST') {
      if (!body?.type_revision_id || !body.invoice) return refuse(422, 'type_revision_id and invoice are required');
      if (body.type_revision_id !== typeRevision) return refuse(409, 'voucher type revision is retired or superseded');
      const n = ++sequence;
      const voucher = { ...body, id: id(n), company_id: COMPANY, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', row_version: 1, revision_number: 1, revision_id: id(n + 500), lines: [], stock: null, fulfillment_terms: null, attachments: [], links: [], custom_fields: {}, invoice: { ...body.invoice, allocations: body.invoice.allocations ?? [], tenders: body.invoice.tenders ?? [], components: body.invoice.components ?? [], accepted_calculation_hash: null } };
      vouchers.set(voucher.id, voucher); history.set(voucher.id, []);
      return answer(reply(voucher, 201));
    }
    const match = route.match(new RegExp(`^${base}/vouchers/([0-9a-f-]{36})(?:/(.*))?$`));
    if (match) {
      const voucher = vouchers.get(match[1]!); if (!voucher) return refuse(404, 'voucher not found');
      const tail = match[2] ?? '';
      if (tail === '' && method === 'GET') return reply(voucher);
      // The saved voucher's field-set: the pinned custom definitions AND the edit view (apis/vouchers api/routes.py voucher_field_set).
      if (tail === 'field-set') return reply({ voucher_id: voucher.id, revision_id: voucher.revision_id, header: [], items: {}, ...metadata(typeRevision, approvalRequired) });
      if (tail === 'history') return reply(page(history.get(voucher.id)!));
      if (tail.startsWith('revisions/')) return reply(voucher);
      if (tail === 'invoice-preview') return reply(calc(voucher));
      if (tail === '' && method === 'PUT') {
        if (body.expected_version !== voucher.row_version) return refuse(409, 'voucher version changed; reload before retrying');
        const content = body.content;
        if (content?.type_revision_id !== typeRevision) return refuse(409, 'voucher type revision is retired or superseded');
        return answer(reply(next(voucher, { ...content, id: voucher.id, status: 'DRAFT', revision_number: voucher.revision_number + 1, revision_id: id(++sequence + 500), invoice: { ...content.invoice, allocations: content.invoice.allocations ?? [], tenders: content.invoice.tenders ?? [], components: content.invoice.components ?? [], accepted_calculation_hash: null } })));
      }
      if (tail === 'invoice-acceptance') {
        if (body.expected_version !== voucher.row_version) return refuse(409, 'voucher version changed; reload before retrying');
        if (body.calculation_hash !== calc(voucher).calculation_hash) return refuse(409, 'the calculation is stale; calculate the saved bill again');
        return answer(reply(next(voucher, { revision_number: voucher.revision_number + 1, revision_id: id(++sequence + 500), invoice: { ...voucher.invoice, accepted_calculation_hash: body.calculation_hash } })));
      }
      const transitions: Record<string, [string[], string]> = { submit: [['DRAFT', 'REJECTED'], 'SUBMITTED'], approve: [['SUBMITTED'], 'APPROVED'], reject: [['SUBMITTED'], 'REJECTED'], cancel: [['DRAFT', 'SUBMITTED', 'REJECTED', 'APPROVED'], 'CANCELLED'] };
      if (body && 'acknowledge_duplicate_bill' in body && tail !== 'submit') return refuse(422, 'request validation failed');
      if (transitions[tail]) {
        const [from, to] = transitions[tail]!;
        if (body.expected_version !== voucher.row_version) return refuse(409, 'voucher version changed; reload before retrying');
        if (!from.includes(voucher.status)) return refuse(409, 'voucher action is not allowed in its current state');
        if (tail === 'submit' && !voucher.invoice.accepted_calculation_hash) return refuse(409, 'an accepted invoice calculation is required');
        // A submit that repeats the supplier's bill is refused until it is acknowledged (apis/vouchers tasks/duplicate_bills.py).
        if (tail === 'submit' && body.acknowledge_duplicate_bill !== true) {
          const hits = matching(voucher.parties?.find((party: Json) => party.role === 'SUPPLIER')?.party_id, voucher.invoice.party_account_id, voucher.invoice.bill_reference ?? '', voucher.id);
          if (hits.length) return reply({ error: { code: 'duplicate_supplier_bill', message: `supplier bill ${voucher.invoice.bill_reference} is already recorded for this supplier (voucher ${hits[0]!.id}, ${hits[0]!.status}); acknowledge the duplicate to submit it anyway`,
            fields: Object.fromEntries(hits.slice(0, 5).flatMap((row, index) => [['id', row.id], ['status', row.status], ['document_date', row.document_date], ['bill_reference', row.invoice.bill_reference], ['revision_number', String(row.revision_number)]].map(([name, value]) => [`matches.${index}.${name}`, value]))) } }, 409);
        }
        // Where the type needs no approval, submitting approves (apis/vouchers domain/documents.py transition).
        const target = tail === 'submit' && !approvalRequired ? 'APPROVED' : to;
        history.get(voucher.id)!.push({ id: id(++sequence + 700), action: tail.toUpperCase(), from_status: voucher.status, to_status: target, revision_id: voucher.revision_id });
        return answer(reply(next(voucher, { status: target })));
      }
      if (tail === 'post') {
        if (voucher.status !== 'APPROVED') return refuse(409, 'voucher action is not allowed in its current state');
        const operation = { id: id(++sequence + 800), voucher_id: voucher.id, revision_id: voucher.revision_id, status: 'PENDING', row_version: 1 };
        operations.set(operation.id, operation); executionDone = false;
        return answer(reply({ operation_id: operation.id, ...operation }, 202));
      }
    }
    const operation = [...operations.values()].find(row => route === `${base}/voucher-operations/${row.id}`);
    if (operation) { if (executionDone) { operation.status = 'COMMITTED'; const voucher = vouchers.get(operation.voucher_id)!; if (voucher.status !== 'POSTED') next(voucher, { status: 'POSTED' }); } return reply(operation); }
    return refuse(404, `The fake services have no route for ${method} ${route}`);
  }

  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
    if (!url.endsWith('/api/product-fields')) return reply({ error: { message: 'unexpected request ' + url } }, 404);
    const payload = JSON.parse(String(init?.body ?? '{}'));
    const { service, path, body, key } = payload, method = payload.method ?? 'GET';
    requests.push({ service, method, path, body, key });
    // The proxy: the browser may only name allowlisted requests (app/api/product-fields/route.ts).
    if (!allowedProductRequest(service, method, path)) return refuse(422, 'Unsupported product field request');
    // A held balance read stays open until released, and ends the way a real fetch does when the page abandons it.
    if (balanceGate && path.split('?')[0]!.endsWith('/ledger/balance')) {
      const gate = balanceGate;
      await new Promise<void>((resolve, reject) => {
        void gate.then(resolve);
        init?.signal?.addEventListener('abort', () => { cancelled.push(path); reject(new DOMException('The operation was aborted.', 'AbortError')); });
      });
    }
    return serve(service, method, path, body, key);
  }));
  return {
    requests, vouchers, cancelled,
    seedSupplier: ({ name, code, payables = 1, alsoCustomer = false }) => {
      const party: Json = { id: id(40 + seeded++), name, code, customer: alsoCustomer };
      parties.push(party);
      const accounts = [payableOf(party.id), secondPayableOf(party.id)].slice(0, payables);
      accounts.forEach((accountId, index) => addAccount(party, accountId, 'SUPPLIER', index ? 'payable (second)' : 'payable'));
      if (alsoCustomer) addAccount(party, receivableOf(party.id), 'CUSTOMER', 'receivable');
      return { id: party.id, name, code, payables: accounts, receivable: alsoCustomer ? receivableOf(party.id) : null };
    },
    holdBalances: () => { let release!: () => void; balanceGate = new Promise<void>(resolve => { release = () => { balanceGate = null; resolve(); }; }); return release; },
    failNext: (match, status, message) => { failures.push({ match, status, message }); },
    completeExecution: () => { executionDone = true; },
    reviseType: revisionId => { typeRevision = revisionId; },
    seedBill: ({ supplier, ledger, billReference, status = 'POSTED', documentDate = '2026-09-12' }) => {
      const n = ++sequence;
      vouchers.set(id(n), { id: id(n), company_id: COMPANY, kind: 'PURCHASE', profile: 'STANDARD', status, row_version: 1, revision_number: 1, revision_id: id(n + 500), document_date: documentDate, parties: supplier ? [{ role: 'SUPPLIER', party_id: supplier, source_version: 2 }] : [], invoice: { bill_reference: billReference, ...(ledger ? { party_account_id: ledger } : {}), supplies: [], allocations: [], tenders: [], components: [], accepted_calculation_hash: null } });
      return id(n);
    },
  };
}

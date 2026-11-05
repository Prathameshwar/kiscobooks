import { entryError, newEntry, previousDate, sum, type Declaration, type Entry, type Metadata } from './financial-opening';

export type OpeningCategory = 'BUYER' | 'SUPPLIER' | 'OTHER';
export type OpeningAccount = {
  id: string; company_id: string; name?: string | null; code?: string | null;
  kind?: string | null; party_role?: string | null; status?: string | null;
  currency_mode?: string | null; currency?: string | null;
};
export function accountFilters(category: OpeningCategory, group: string | null, query: string) {
  const params = new URLSearchParams({ status: 'ACTIVE', sort: 'name' });
  if (category === 'OTHER') { if (group) params.set('group_id', group); }
  else { params.set('kind', 'PARTY'); params.set('role', category === 'BUYER' ? 'CUSTOMER' : 'SUPPLIER'); }
  if (query.trim().length >= 2) params.set('q', query.trim());
  return params.toString();
}
export function canCaptureOpening(metadata: Metadata, party: boolean) {
  const fields = metadata.capture.$defs?.OpeningEntry?.properties;
  if (!fields || !['account_id', 'side', 'amount', 'currency', 'exchange_rate', 'base_amount', 'source_key'].every(key => fields[key]) ||
      !['account_id', 'side', 'amount', 'currency', 'exchange_rate', 'opening_base_amount'].every(key => metadata.capture_permissions.journal_lines[key])) return false;
  return !party || !!fields.documents && ['account_id', 'party_id', 'role', 'direction', 'reference', 'currency', 'amount', 'base_currency', 'base_amount', 'document_date', 'due_date', 'posting_date', 'terms'].every(key => metadata.capture_permissions.open_items[key]);
}
export function changeAccountOpening(value: Declaration, account: OpeningAccount, change: Pick<Partial<Entry>, 'amount' | 'side'>): Entry[] {
  const matches = value.entries.filter(row => row.account_id === account.id);
  if (matches.length > 1) return value.entries; // Detailed lines must be edited individually.
  if (change.amount !== undefined && (change.amount === '' || /^0(?:\.0{1,4})?$/.test(change.amount))) return value.entries.filter(row => row.account_id !== account.id);
  const previous = matches[0];
  const currency = account.currency_mode === 'FIXED' ? account.currency ?? value.currency : value.currency;
  const row: Entry = { ...(previous ?? { ...newEntry(currency, account.id), side: account.party_role === 'SUPPLIER' ? 'CREDIT' : 'DEBIT' }), ...change };
  if (row.currency === value.currency) { row.base_amount = row.amount; row.exchange_rate = '1'; }
  const documents = row.documents ?? [];
  if (account.kind === 'PARTY' && !documents.length) {
    row.documents = [{ line_sequence: 1, document_kind: 'ON_ACCOUNT', reference: 'Opening-' + row.source_key,
      source_key: row.source_key + ':on-account', amount: row.amount, base_amount: row.base_amount,
      document_date: null, due_date: null }];
  } else if (documents.length === 1 && documents[0].document_kind === 'ON_ACCOUNT' && documents[0].source_key === row.source_key + ':on-account') {
    row.documents = [{ ...documents[0], amount: row.amount, base_amount: row.base_amount }];
  }
  return previous ? value.entries.map(item => item === previous ? row : item) : [...value.entries, row];
}
export function editedOpeningError(value: Declaration, metadata: Metadata): string | null {
  const entries = value.entries.filter(row => row.source_key !== OFFSET_SOURCE);
  if (!entries.length) return 'Enter at least one opening balance before continuing.';
  for (const row of entries) {
    const problem = entryError(row, value);
    if (problem) return problem;
  }
  if (!metadata.capture.properties?.posting_date) return 'Opening date access is required to review this worksheet.';
  return null;
}
export function automaticSource(value: Declaration): Declaration {
  return { ...value, source_system: value.source_system || 'manual', source_id: value.source_id || crypto.randomUUID(),
    covered_through: value.covered_through || previousDate(value.posting_date),
    reason: value.reason.trim() || 'Opening balances entered in the account opening worksheet.' };
}
export function needsClearing(value: Declaration) {
  return value.entries.length > 200 || value.entries.reduce((count, row) => count + (row.documents?.length ?? 0), 0) > 1000;
}
export const OFFSET_SOURCE = 'automatic-opening-offset';
export function withOpeningOffset(value: Declaration, account: string | null): Declaration {
  const entries = value.entries.filter(row => row.source_key !== OFFSET_SOURCE);
  if (!account) return { ...value, entries };
  if (entries.some(row => row.account_id === account)) throw new Error('The opening offset account cannot also have an entered opening balance.');
  const debit = BigInt(sum(entries.filter(row => row.side === 'DEBIT').map(row => row.base_amount ?? '')).replace('.', ''));
  const credit = BigInt(sum(entries.filter(row => row.side === 'CREDIT').map(row => row.base_amount ?? '')).replace('.', ''));
  const difference = debit - credit;
  if (!difference) return { ...value, entries };
  const units = (difference < 0n ? -difference : difference).toString().padStart(5, '0');
  const amount = units.slice(0, -4) + '.' + units.slice(-4);
  return { ...value, entries: [...entries, { source_key: OFFSET_SOURCE, account_id: account,
    side: difference > 0n ? 'CREDIT' : 'DEBIT', currency: value.currency, exchange_rate: '1', amount, base_amount: amount,
    description: 'Reviewed opening-balance offset', documents: [] }] };
}

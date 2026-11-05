import { accountingRequest } from './accounting-configuration';
import { owned } from './financial-opening';
import type { ServiceRequest } from './service-call';
import type { OpeningAccount } from './financial-opening-worksheet';

export type OpeningDefaultAccount = OpeningAccount & { group_id?: string | null; posting_policy?: string | null };
export type OpeningDefaults = { offset: OpeningDefaultAccount | null; clearing: OpeningDefaultAccount | null };
export async function verifyOpeningDefault(root: string, account: OpeningDefaultAccount, kind: 'offset' | 'clearing', signal?: AbortSignal) {
  const company = root.split('/').at(-1)!;
  owned(company)(account);
  if (account.status !== 'ACTIVE' || account.kind !== 'GENERAL' || account.currency_mode !== 'BASE' || account.posting_policy !== 'MANUAL_ALLOWED' || !account.group_id)
    throw { status: 422, message: 'Opening defaults require an active general account in company base currency that allows manual posting.' };
  const group = await accountingRequest<{ id: string; company_id: string; head_id?: string }>({ path: root + '/account-groups/' + account.group_id, signal });
  owned(company)(group);
  if (group.id !== account.group_id || !group.head_id) throw { status: 502, message: 'Opening account group could not be verified.' };
  const head = await accountingRequest<{ id: string; company_id: string; nature?: string }>({ path: root + '/account-heads/' + group.head_id, signal });
  owned(company)(head);
  if (head.id !== group.head_id || !(kind === 'offset' ? ['EQUITY'] : ['ASSET', 'LIABILITY']).includes(head.nature ?? ''))
    throw { status: 422, message: kind === 'offset' ? 'Choose an equity account for the opening-balance offset.' : 'Choose an asset or liability account for migration clearing.' };
}
export async function openingDefaultsRequest<T>({ path: root, signal }: ServiceRequest): Promise<T> {
  async function find(code: string, kind: 'offset' | 'clearing') {
    const page = await accountingRequest<{ items: OpeningDefaultAccount[] }>({ path: root + '/accounts?' + new URLSearchParams({ code, status: 'ACTIVE', limit: '2' }), signal });
    if (!Array.isArray(page.items) || page.items.length > 1) throw { status: 502, message: 'Opening account defaults could not be verified.' };
    const account = page.items[0];
    if (!account) return null;
    if (account.code !== code) throw { status: 502, message: 'Opening account default does not match its configured code.' };
    await verifyOpeningDefault(root, account, kind, signal);
    return account;
  }
  const [offset, clearing] = await Promise.all([find('OPENING_BALANCE_OFFSET', 'offset'), find('MIGRATION_CLEARING', 'clearing')]);
  return { offset, clearing } as T;
}

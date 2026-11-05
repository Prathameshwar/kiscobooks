import { beforeEach, expect, it, vi } from 'vitest';
import { openingDefaultsRequest, verifyOpeningDefault } from '../app/lib/financial-opening-defaults';
import { accountingRequest } from '../app/lib/accounting-configuration';
import { ACCOUNT, COMPANY, OTHER } from './financial-opening-fixtures';
vi.mock('../app/lib/accounting-configuration', () => ({ accountingRequest: vi.fn() }));
const api = vi.mocked(accountingRequest), root = `/v1/companies/${COMPANY}`;
const account = { id: ACCOUNT, company_id: COMPANY, status: 'ACTIVE', kind: 'GENERAL', currency_mode: 'BASE', posting_policy: 'MANUAL_ALLOWED', group_id: OTHER };
beforeEach(() => { api.mockReset(); api.mockImplementation(async req => req.path.includes('/account-groups/') ? { id: OTHER, company_id: COMPANY, head_id: ACCOUNT } as never : { id: ACCOUNT, company_id: COMPANY, nature: 'EQUITY' } as never); });
it('requires an equity offset and distinguishes it from asset/liability clearing', async () => {
  await expect(verifyOpeningDefault(root, account, 'offset')).resolves.toBeUndefined();
  await expect(verifyOpeningDefault(root, account, 'clearing')).rejects.toMatchObject({ status: 422 });
});
it('fails closed for another company, inactive accounts, or restricted classification', async () => {
  await expect(verifyOpeningDefault(root, { ...account, company_id: OTHER }, 'offset')).rejects.toMatchObject({ status: 502 });
  await expect(verifyOpeningDefault(root, { ...account, status: 'INACTIVE' }, 'offset')).rejects.toMatchObject({ status: 422 });
  await expect(verifyOpeningDefault(root, { ...account, group_id: null }, 'offset')).rejects.toMatchObject({ status: 422 });
});
it('does not substitute an arbitrary returned account for an absent configured default', async () => {
  api.mockResolvedValue({ items: [{ ...account, code: 'RETAINED_EARNINGS' }] } as never);
  await expect(openingDefaultsRequest({ path: root })).rejects.toMatchObject({ status: 502 });
});

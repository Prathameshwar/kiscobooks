import { beforeEach, expect, it, vi } from 'vitest';
import { loadSalesTypes } from '../app/lib/sales-entry-lookups';
import { salesCall } from '../app/lib/sales-entry-api';
vi.mock('../app/lib/sales-entry-api', async original => ({ ...await original<typeof import('../app/lib/sales-entry-api')>(), salesCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', typeId = '10000000-0000-7000-8000-000000000002';
const row = { id: typeId, company_id: company, kind: 'SALES', profile: 'STANDARD', status: 'ACTIVE', name: 'Specific sales' };
beforeEach(() => { vi.mocked(salesCall).mockReset(); vi.mocked(salesCall).mockResolvedValue(row); });
it('reads the exact sales type without truncating a large company type list', async () => {
  expect(await loadSalesTypes(company, typeId)).toEqual([row]);
  expect(vi.mocked(salesCall)).toHaveBeenCalledWith('vouchers', { path: '/v1/companies/' + company + '/voucher-types/' + typeId });
});
it.each([{ company_id: typeId }, { id: company }, { kind: 'PURCHASE' }, null])('refuses mismatched sales type %j', async override => {
  vi.mocked(salesCall).mockResolvedValue(override === null ? null : { ...row, ...override });
  await expect(loadSalesTypes(company, typeId)).rejects.toMatchObject({ status: 502 });
});
it.each([{ status: 'RETIRED' }, { profile: 'PRO_FORMA' }])('preserves the invoice editor capability gate %j', async override => {
  vi.mocked(salesCall).mockResolvedValue({ ...row, ...override });
  await expect(loadSalesTypes(company, typeId)).rejects.toMatchObject({ status: 422 });
});
it('rejects an invalid type ID before requesting it', async () => {
  await expect(loadSalesTypes(company, '../escape')).rejects.toMatchObject({ status: 502 });
  expect(salesCall).not.toHaveBeenCalled();
});
it('retains the normal sales picker when no specific type is selected', async () => {
  vi.mocked(salesCall).mockResolvedValue({ items: [row, { ...row, id: company, profile: 'PRO_FORMA' }] });
  expect(await loadSalesTypes(company)).toEqual([row]);
  expect(vi.mocked(salesCall).mock.calls[0][1].path).toContain('kind=SALES');
});

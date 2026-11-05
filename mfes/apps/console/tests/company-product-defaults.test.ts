import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { components as CatalogComponents } from '@janso/api-client/catalog';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';
import { companyProductDefaults } from '../app/lib/company-product-defaults';
import { companyCall } from '../app/lib/company-api';
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001';
const type = { id: '10000000-0000-7000-8000-000000000002', code: 'DEFAULT', name: 'Default', kind: 'BOTH', is_active: true } satisfies CatalogComponents['schemas']['ProductTypeListItem'];
const group = { id: '10000000-0000-7000-8000-000000000003', code: 'DEFAULT', name: 'Default', is_active: true, allowed_kind: 'BOTH' } satisfies CatalogComponents['schemas']['GroupListItem'];
const revision = { id: '10000000-0000-7000-8000-000000000004', product_type_id: type.id, kind: 'BOTH', published_at: '2026-10-30T00:00:00Z' };
beforeEach(() => {
  vi.mocked(companyCall).mockReset();
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: [path.includes('/revisions') ? revision : path.includes('product-types') ? type : group] }));
});
afterEach(() => vi.useRealTimers());
it.each(['product-types', 'item-groups'])('permits only bounded Default readiness reads for %s', resource => {
  const path = `/v1/companies/${company}/${resource}`;
  expect(allowedCompanyRequest('catalog', 'GET', path + '?code=DEFAULT&limit=1')).toBe(true);
  expect(allowedCompanyRequest('catalog', 'GET', path + '?q=Default&limit=50')).toBe(true);
  for (const query of ['?code=PRIVATE&limit=1', '?q=Default&limit=200', '?q=Default&limit=50&cursor=extra']) {
    expect(allowedCompanyRequest('catalog', 'GET', path + query)).toBe(false);
  }
  expect(allowedCompanyRequest('catalog', 'POST', path)).toBe(false);
});
it('checks both scoped records without attempting any master write', async () => {
  expect(await companyProductDefaults(company)).toEqual({ type, group });
  expect(vi.mocked(companyCall).mock.calls).toHaveLength(3);
  expect(vi.mocked(companyCall).mock.calls.every(call => call[2]?.method === undefined && call[2]?.signal instanceof AbortSignal)).toBe(true);
});
it('reuses named Default records with existing alternative codes', async () => {
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: path.includes('/revisions') ? [revision] : path.includes('code=') ? [] : [{ ...(path.includes('product-types') ? type : group), code: 'MY_DEFAULT' }] }));
  const result = await companyProductDefaults(company);
  expect(result.type.code).toBe('MY_DEFAULT');
  expect(result.group.code).toBe('MY_DEFAULT');
});
it.each([{ ...type, company_id: 'foreign' }, { ...type, id: '../foreign' }])('refuses unverifiable default identity', async wrong => {
  vi.mocked(companyCall).mockResolvedValue({ items: [wrong] });
  await expect(companyProductDefaults(company)).rejects.toMatchObject({ status: 502 });
});
it.each([{ ...group, is_active: false }, { ...group, allowed_kind: 'GOODS' }])('preserves incompatible existing defaults and reports review', async wrong => {
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: [path.includes('product-types') ? type : wrong] }));
  await expect(companyProductDefaults(company)).rejects.toMatchObject({ status: 409 });
});
it('waits for provisioning to finish and rechecks without creating masters', async () => {
  vi.useFakeTimers();
  let reads = 0;
  vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path.includes('/revisions')) return { items: [revision] };
    if (path.includes('product-types')) return { items: [type] };
    if (path.includes('code=')) reads++;
    return { items: reads < 2 ? [] : [group] };
  });
  const result = companyProductDefaults(company);
  await vi.advanceTimersByTimeAsync(1000);
  expect((await result).group.id).toBe(group.id);
  expect(reads).toBe(2);
});
it('bounds missing-default waits and leaves the remaining setup retryable', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValue({ items: [] });
  const result = companyProductDefaults(company).catch(error => error);
  await vi.advanceTimersByTimeAsync(30_000);
  expect(await result).toMatchObject({ status: 503, code: 'product_defaults_pending' });
  expect(vi.mocked(companyCall).mock.calls).toHaveLength(120);
});

it('requires a published Default type revision before marking setup ready', async () => {
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: path.includes('/revisions') ? [] : [path.includes('product-types') ? type : group] }));
  await expect(companyProductDefaults(company)).rejects.toMatchObject({ status: 409 });
});
it.each([{ ...revision, product_type_id: group.id }, { ...revision, published_at: null }])('refuses unverifiable published revision evidence', async wrong => {
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: [path.includes('/revisions') ? wrong : path.includes('product-types') ? type : group] }));
  await expect(companyProductDefaults(company)).rejects.toMatchObject({ status: 502 });
});
it('permits only a bounded published revision read through the setup boundary', () => {
  const path = `/v1/companies/${company}/product-types/${type.id}/revisions`;
  expect(allowedCompanyRequest('catalog', 'GET', path + '?published=true&limit=1')).toBe(true);
  for (const query of ['?published=false&limit=1', '?published=true&limit=50', '?published=true&limit=1&cursor=extra']) {
    expect(allowedCompanyRequest('catalog', 'GET', path + query)).toBe(false);
  }
  expect(allowedCompanyRequest('catalog', 'POST', path)).toBe(false);
});

it('accepts the native scoped master list contract without a company_id payload field', async () => {
  const nativeType: CatalogComponents['schemas']['ProductTypeListItem'] = type;
  const nativeGroup: CatalogComponents['schemas']['GroupListItem'] = group;
  vi.mocked(companyCall).mockImplementation(async (_service, path) => ({ items: [path.includes('/revisions') ? revision : path.includes('product-types') ? nativeType : nativeGroup] }));
  await expect(companyProductDefaults(company)).resolves.toEqual({ type: nativeType, group: nativeGroup });
});

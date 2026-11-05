import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { companyCall } from '../app/lib/company-api';
import { companyPricingDefaults } from '../app/lib/company-pricing-defaults';
import { COMPANY, ID, PARTY } from './accounting-configuration-fixtures';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn() }));
const plan = { id: ID, company_id: COMPANY, price_level_id: PARTY,
  purpose: 'SALE', currency: 'INR', tax_basis: 'EXCLUSIVE' };
beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

it('verifies the baseline sales plan in company currency', async () => {
  vi.mocked(companyCall).mockResolvedValue({ items: [plan] });
  expect(await companyPricingDefaults(COMPANY, PARTY, 'INR')).toEqual(plan);
  expect(companyCall).toHaveBeenCalledWith('catalog', expect.stringContaining(
    `/v1/companies/${COMPANY}/price-plans?purpose=SALE&currency=INR&price_level_id=${PARTY}`,
  ), expect.objectContaining({ signal: expect.any(AbortSignal) }));
});
it('waits for the trusted provisioner and accepts existing authored plans', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValueOnce({ items: [] }).mockResolvedValue({ items: [plan] });
  const result = companyPricingDefaults(COMPANY, PARTY, 'INR');
  await vi.runAllTimersAsync();
  expect(await result).toEqual(plan);
});
it.each([
  { ...plan, company_id: PARTY }, { ...plan, price_level_id: COMPANY },
  { ...plan, currency: 'USD' }, { ...plan, purpose: 'PURCHASE' },
  { ...plan, tax_basis: null }, { ...plan, id: 'invalid' },
])('rejects an unverified plan: %j', async (value) => {
  vi.mocked(companyCall).mockResolvedValue({ items: [value] });
  await expect(companyPricingDefaults(COMPANY, PARTY, 'INR')).rejects.toMatchObject({ status: 502 });
});
it('keeps pending setup retryable without claiming readiness', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValue({ items: [] });
  const result = expect(companyPricingDefaults(COMPANY, PARTY, 'INR')).rejects.toMatchObject({ status: 503 });
  await vi.runAllTimersAsync();
  await result;
});

import { render } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ReadinessPage from '../app/settings/readiness/page';
import { CompanyReadiness } from '../app/components/CompanyReadiness';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/CompanyReadiness', () => ({ CompanyReadiness: vi.fn(() => null) }));
const company = '01990000-0000-7000-8000-000000000001';
const permissions = ['company.read', 'period.read', 'accounting.finance.read', 'ledger.read'];
beforeEach(async () => {
  vi.mocked(pageContext).mockReset(); vi.mocked(CompanyReadiness).mockClear();
  const session = await sessionFor({ permissions: [] }); session.company = { id: company, name: 'Company A' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('passes active selected-company grants to readiness checks even when aggregate permissions are empty', async () => {
  render(await ReadinessPage());
  expect(vi.mocked(CompanyReadiness).mock.calls[0][0].permissions).toEqual(expect.arrayContaining(permissions));
});
it.each(['other company', 'expired', 'future', 'missing'] as const)('does not fetch checks with aggregate permissions from %s authority', async authority => {
  const { session } = await pageContext(); session.permissions = permissions;
  if (authority === 'other company') session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  if (authority === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (authority === 'future') session.grants![0].valid_from = '2099-01-01';
  if (authority === 'missing') session.grants = [];
  render(await ReadinessPage());
  expect(vi.mocked(CompanyReadiness).mock.calls[0][0].permissions).toEqual([]);
});

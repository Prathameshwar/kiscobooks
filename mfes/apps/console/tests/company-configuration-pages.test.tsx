import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ConfigurationPage from '../app/companies/[companyId]/configuration/page';
import CurrentPage from '../app/settings/company/page';
import { CompanyConfiguration } from '../app/components/CompanyConfiguration';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { companyId, userId } from './access-fixtures';
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/CompanyConfiguration', () => ({ CompanyConfiguration: vi.fn(({ companyId }: { companyId: string }) => <p>Configuration {companyId}</p>) }));
const props = (id = companyId) => ({ params: Promise.resolve({ companyId: id }), searchParams: Promise.resolve({ returnTo: '/companies/manage?q=Re' }) });
beforeEach(async () => {
  vi.clearAllMocks(); const session = await sessionFor({ permissions: ['company.read', 'company.update'] });
  session.company = { id: companyId, name: 'Retail' }; session.grants = [{ scope_type: 'company', scope_id: companyId, permissions: session.permissions, valid_from: '2000-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('resolves the named company and forwards directory context without switching the open company', async () => {
  const data = await pageContext(); data.session.company.id = userId;
  render(await ConfigurationPage(props())); expect(screen.getByText('Configuration ' + companyId)).toBeVisible();
  expect(vi.mocked(CompanyConfiguration).mock.calls[0][0]).toMatchObject({ companyId, returnTo: '/companies/manage?q=Re' });
});
it('normalizes a valid identifier and rejects invalid routes before resolving business context', async () => {
  await ConfigurationPage(props(companyId.toUpperCase())); vi.mocked(pageContext).mockClear();
  await expect(ConfigurationPage(props('not-a-company'))).rejects.toThrow('not found'); expect(pageContext).not.toHaveBeenCalled();
});
it.each(['other_company', 'expired', 'platform_label'])('does not grant configuration through %s', async authority => {
  const data = await pageContext();
  if (authority === 'other_company') data.session.grants![0].scope_id = userId;
  if (authority === 'expired') data.session.grants![0].valid_to = '2020-01-01';
  if (authority === 'platform_label') { data.session.role = 'platform_admin'; data.session.grants = []; }
  render(await ConfigurationPage(props())); expect(screen.getByText('Company read access is required for this company.')).toBeVisible(); expect(CompanyConfiguration).not.toHaveBeenCalled();
});
it('opens selected-company configuration through the settings alias', async () => {
  render(await CurrentPage()); expect(vi.mocked(CompanyConfiguration).mock.calls[0][0]).toMatchObject({ companyId, returnTo: '/settings' });
});
it('offers company selection when none is open without inferring creation from company grants', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' }; data.session.grants![0].permissions.push('company.create');
  render(await CurrentPage()); expect(screen.getByRole('link', { name: 'See the companies you can open' })).toHaveAttribute('href', '/companies'); expect(screen.queryByRole('link', { name: 'Create a company' })).not.toBeInTheDocument();
});
it('offers creation only with an active tenant creation grant', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' }; data.session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: ['company.create'], valid_from: '2000-01-01', valid_to: null }];
  render(await CurrentPage()); expect(screen.getByRole('link', { name: 'Create a company' })).toHaveAttribute('href', '/companies/new');
});
it('refuses the selected-company alias when only another company is readable', async () => {
  const data = await pageContext(); data.session.grants![0].scope_id = userId;
  render(await CurrentPage()); expect(screen.getByText('Company read access is required for this company.')).toBeVisible();
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/accounting/[[...segments]]/page';
import { AccountingConfigurationPage } from '../app/components/AccountingConfigurationPage';
import { pageContext } from '../app/lib/page-context';
import { navigationFor } from '../app/nav';
import { companyContextFor, sessionFor } from './helpers';
import { COMPANY, ID, response } from './accounting-configuration-fixtures';
import { serviceCall } from '../app/lib/service-call';
import { waitFor } from '@testing-library/react';
import { partyCompanyCountry } from '../app/lib/party-company-country';
vi.mock('../app/lib/party-company-country', () => ({ partyCompanyCountry: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
it.each(['parties', 'suppliers'])('reads company country only for authorized %s creation', async (resource) => {
  const { session } = await pageContext();
  session.grants![0].permissions.push('company.read');
  vi.mocked(partyCompanyCountry).mockResolvedValue('US');
  render(await AccountingConfigurationPage({ segments: [resource, 'new'] }));
  expect(partyCompanyCountry).toHaveBeenCalledTimes(1);
  expect(partyCompanyCountry).toHaveBeenCalledWith(COMPANY);
  await userEvent.type(await screen.findByRole('textbox', { name: 'Code' }), 'COUNTRY');
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Company country');
  // "New supplier" fixes the role; "New party" requires one, because it decides the ledger account.
  if (resource === 'parties') await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Party role' }), 'CUSTOMER');
  await userEvent.click(screen.getByRole('button', { name: resource === 'suppliers' ? 'Create supplier' : 'Create party' }));
  await waitFor(() => expect(vi.mocked(serviceCall).mock.calls.some(([, request]) =>
    request.method === 'POST' && (request.body as Record<string, unknown>)?.country_code === 'US',
  )).toBe(true));
});
it.each(['valid', 'other-company', 'expired', 'role-only'])('scopes party directory pricing actions to %s grants', async authority => {
  const { session } = await pageContext();
  const permissions = ['customer_pricing.read', 'customer_pricing.manage', 'company.read'];
  if (authority === 'valid') session.grants![0].permissions.push(...permissions);
  else if (authority === 'role-only') { session.permissions = [...session.permissions, ...permissions]; session.role = 'company_admin'; }
  else session.grants!.push({ scope_type: 'company', scope_id: authority === 'other-company' ? ID : COMPANY, permissions, valid_from: '2000-01-01', valid_to: authority === 'expired' ? '2020-01-01' : null });
  vi.mocked(serviceCall).mockImplementation(async (_, request) => request.path.endsWith('/setup-readiness')
    ? { company_id: COMPANY, features: ['inventory', 'multi_price_levels', 'credit_limits'].map(feature_key => ({ feature_key, state: 'ENABLED' })) } as never
    : response(request.path, request.method, request.body) as never);
  render(await AccountingConfigurationPage({ segments: ['suppliers'] }));
  await userEvent.click(await screen.findByRole('button', { name: /Actions for Retail supplier/ }));
  if (authority === 'valid') {
    expect(screen.getByRole('menuitem', { name: /Manage pricing/ })).toHaveAttribute('aria-disabled', 'true');
    await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Manage credit limits' })).toHaveAttribute('href'));
  } else {
    expect(screen.queryByRole('menuitem', { name: /Manage pricing/ })).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Manage credit limits/ })).toHaveAttribute('aria-disabled', 'true');
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.endsWith('/setup-readiness'))).toBe(false);
  }
});
beforeEach(async () => { vi.clearAllMocks(); const permissions = ['account', 'party', 'group', 'head', 'bank', 'tax', 'policy', 'withholding', 'setup', 'mapping'].flatMap(family => [`accounting.${family}.read`, `accounting.${family}.manage`]); permissions.push('accounting.history.read'); const session = await sessionFor({ permissions }); session.company = { id: COMPANY, name: 'Retail' }; session.grants = [{ scope_type: 'company', scope_id: COMPANY, permissions, valid_from: '2000-01-01', valid_to: null }]; vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() }); vi.mocked(serviceCall).mockImplementation(async (_, request) => response(request.path, request.method, request.body) as never); });
it.each([[], ['accounts'], ['parties', 'new'], ['suppliers'], ['suppliers', 'new'], ['parties', ID], ['accounts', ID, 'edit'], ['parties', ID, 'history'], ['setup'], ['withholding-rates', 'new']])('opens supported route %j', async (...segments) => { render(await AccountingConfigurationPage({ segments })); expect(screen.queryByText(/requested Accounting read\/action permission/)).not.toBeInTheDocument(); });
it('forwards return navigation through the catch-all route', async () => { render(await Page({ params: Promise.resolve({ segments: ['parties', 'new'] }), searchParams: Promise.resolve({ returnTo: '/settings' }) })); expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings'); });
it('opens accounting from Settings with one page title and a supporting section heading', async () => {
  render(await AccountingConfigurationPage({ query: { returnTo: '/settings' } }));
  expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  expect(screen.getByRole('heading', { level: 2, name: 'Supporting configuration' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
});
it.each([['unknown'], ['accounts', 'bad'], ['account-heads', 'new'], ['account-heads', ID, 'edit'], ['parties', ID, 'delete'], ['setup', 'new']])('rejects unsupported route %j before reading context', async (...segments) => { await expect(AccountingConfigurationPage({ segments })).rejects.toThrow('not found'); expect(pageContext).not.toHaveBeenCalled(); });
it.each(['other_company', 'expired', 'role_only'])('does not infer authority from %s', async authority => { const data = await pageContext(); if (authority === 'other_company') data.session.grants![0].scope_id = ID; else if (authority === 'expired') data.session.grants![0].valid_to = '2020-01-01'; else { data.session.role = 'platform_admin'; data.session.grants = []; } render(await AccountingConfigurationPage()); expect(screen.getByText(/requested Accounting read\/action permission/)).toBeVisible(); expect(navigationFor(data.session).flatMap(section => section.items).some(item => item.href === '/accounting')).toBe(false); });
it('offers company selection without inventing tenant company-create authority', async () => { const data = await pageContext(); data.session.company = { name: 'Select a company' }; data.session.grants![0].permissions.push('company.create'); render(await AccountingConfigurationPage()); expect(screen.getByRole('link', { name: 'See the companies you can open' })).toBeVisible(); expect(screen.queryByRole('link', { name: 'Create a company' })).not.toBeInTheDocument(); });
it.each([['parties', 'new'], ['parties', ID, 'edit'], ['parties', ID, 'history']])('requires the action grant for %j', async (...segments) => { const data = await pageContext(); data.session.grants![0].permissions = ['accounting.party.read']; render(await AccountingConfigurationPage({ segments })); expect(screen.getByText(/requested Accounting read\/action permission/)).toBeVisible(); });
it('keeps supporting configuration reachable for a tax-only reader without restoring the old sidebar tree', async () => { const data = await pageContext(); data.session.grants![0].permissions = ['accounting.tax.read']; render(await AccountingConfigurationPage()); expect(screen.getByRole('link', { name: /Account tax profiles/ })).toHaveAttribute('href', '/accounting/account-tax-profiles'); expect(navigationFor(data.session).flatMap(section => section.items).some(item => item.href === '/accounting')).toBe(false); });
it('forwards commercial type assignment into the native membership editor', async () => {
  render(await AccountingConfigurationPage({ segments: ['party-commercial-type-memberships', 'new'], query: { commercial_type_id: ID, returnTo: '/accounting/party-commercial-types/' + ID } }));
  await screen.findByDisplayValue('General reference');
  expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('/configuration/options/party-commercial-types') && request.path.includes('value=' + ID))).toBe(true);
  expect(screen.getByRole('link', { name: 'Back to commercial type details' })).toHaveAttribute('href', '/accounting/party-commercial-types/' + ID);
});
it.each([['exchange-rates', 'finance'], ['charge-policies', 'charges']])('opens %s using its own current company read grant', async (resource, family) => {
  const data = await pageContext(); data.session.grants![0].permissions = ['accounting.' + family + '.read'];
  render(await AccountingConfigurationPage({ segments: [resource] }));
  expect(await screen.findByRole('table')).toBeVisible();
  expect(screen.queryByRole('link', { name: /^New / })).not.toBeInTheDocument();
   const masters = navigationFor(data.session).flatMap(section => section.items).find(item => item.href === '/masters');
   expect(masters).toBeDefined(); expect(masters?.children).toBeUndefined();
});
it.each([['exchange-rates', ID, 'edit'], ['exchange-rates', ID, 'history'], ['charge-policies', ID, 'edit'], ['charge-policies', ID, 'history']])('rejects unsupported financial-master route %j', async (...segments) => { await expect(AccountingConfigurationPage({ segments })).rejects.toThrow('not found'); expect(pageContext).not.toHaveBeenCalled(); });
it('requires the native publication grant for creating posting defaults', async () => {
  render(await AccountingConfigurationPage({ segments: ['posting-mappings', 'new'] }));
  expect(screen.getByText(/requested Accounting read\/action permission/)).toBeVisible();
  expect(serviceCall).not.toHaveBeenCalled();
});
it('uses separate current company grants for child creation on the account view', async () => {
  const data = await pageContext();
  data.session.grants![0].permissions = ['accounting.account.read', 'accounting.bank.read', 'accounting.bank.manage'];
  render(await AccountingConfigurationPage({ segments: ['accounts', ID] }));
  await userEvent.click(await screen.findByRole('button', { name: 'Account actions' }));
  expect(screen.getByRole('menuitem', { name: /Create bank profile/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.queryByRole('menuitem', { name: 'Create account alias' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Edit account' })).not.toBeInTheDocument();
});
it('offers posting creation only with its read, manage and publication grants in this company', async () => {
  const data = await pageContext();
  data.session.grants![0].permissions = ['accounting.account.read', 'accounting.mapping.read', 'accounting.mapping.manage', 'accounting.mapping.publish'];
  render(await AccountingConfigurationPage({ segments: ['accounts', ID] }));
  await userEvent.click(await screen.findByRole('button', { name: 'Account actions' }));
  expect(screen.getByRole('menuitem', { name: /Create posting default/ })).toHaveAttribute('aria-disabled', 'true');
});
it.each(['other-company', 'expired', 'role-only'])('withholds child creation from %s authority', async authority => {
  const data = await pageContext();
  data.session.grants![0].permissions = ['accounting.account.read', 'accounting.bank.read'];
  if (authority === 'role-only') { data.session.role = 'company_admin'; data.session.permissions.push('accounting.bank.manage'); }
  else data.session.grants!.push({ scope_type: 'company', scope_id: authority === 'other-company' ? ID : COMPANY, permissions: ['accounting.bank.manage'], valid_from: '2000-01-01', valid_to: authority === 'expired' ? '2020-01-01' : null });
  render(await AccountingConfigurationPage({ segments: ['accounts', ID] }));
  await userEvent.click(await screen.findByRole('button', { name: 'Account actions' }));
  expect(screen.getByRole('menuitem', { name: 'Manage account bank profiles' })).toHaveAttribute('href');
  expect(screen.queryByRole('menuitem', { name: /Create bank profile/ })).not.toBeInTheDocument();
});

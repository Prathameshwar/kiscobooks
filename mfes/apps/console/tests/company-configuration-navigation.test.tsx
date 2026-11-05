import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import SettingsPage from '../app/settings/page';
import { CompanyDirectory } from '../app/components/CompanyDirectory';
import { CompanyConfiguration } from '../app/components/CompanyConfiguration';
import { pageContext } from '../app/lib/page-context';
import { companyCall } from '../app/lib/company-api';
import { administrationBackLabel, administrationReturn } from '../app/lib/administration-navigation';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';
import { companyId } from './access-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn() }));
async function administrator() {
  const session = await sessionFor({ permissions: ['company.read', 'company.update'] });
  session.company = { id: companyId, name: 'Retail' };
  session.grants = [{ scope_type: 'company', scope_id: companyId, permissions: session.permissions, valid_from: '2000-01-01', valid_to: null }];
  return session;
}
beforeEach(() => vi.clearAllMocks());
it('opens current-company configuration from settings with an explicit settings return', async () => {
  vi.mocked(pageContext).mockResolvedValue({ session: await administrator(), context: companyContextFor() });
  await renderWithProviders(await SettingsPage());
  expect(screen.getByRole('link', { name: 'Company configuration' })).toHaveAttribute('href', '/companies/' + companyId + '/configuration?returnTo=%2Fsettings');
});
it.each(['company', 'expired'])('does not offer company creation in settings through a %s grant', async authority => {
  const session = await administrator(); session.company = { name: 'Select a company' };
  session.permissions.push('company.create'); session.grants![0].permissions.push('company.create');
  if (authority === 'expired') { session.grants![0].scope_type = 'tenant'; session.grants![0].scope_id = null; session.grants![0].valid_to = '2020-01-01'; }
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  await renderWithProviders(await SettingsPage());
  expect(screen.queryByRole('link', { name: 'Create a company' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'See the companies you can open' })).toBeVisible();
});
it('offers configuration through the scoped company kebab while retaining filters', async () => {
  vi.mocked(companyCall).mockResolvedValue({ items: [{ id: companyId, display_name: 'Retail', status: 'active' }], page: { has_more: false, next_cursor: null } });
  await renderWithProviders(<CompanyDirectory session={await administrator()} initialQuery="q=Re" />);
  await userEvent.click(await screen.findByRole('button', { name: /Actions for Retail/ }));
  expect(screen.getByRole('menuitem', { name: 'Configure company' }).getAttribute('href')).toContain('/configuration?returnTo=');
});
it('retains only valid configuration and settings return destinations', () => {
  expect(administrationReturn('companies', '/companies/' + companyId + '/configuration?returnTo=%2Fsettings')).toContain('/configuration?returnTo=%2Fsettings');
});

it('retains the GST settings route with its nested configuration return and rejects external parents', () => {
  const destination = '/companies/' + companyId + '/gst-settings?returnTo=' + encodeURIComponent('/companies/' + companyId + '/configuration?returnTo=%2Fsettings');
  expect(administrationReturn('companies', destination)).toBe(destination);
  expect(administrationBackLabel(destination)).toBe('GST settings');
  expect(administrationReturn('companies', '/companies/' + companyId + '/gst-settings?returnTo=https%3A%2F%2Foutside.invalid')).toBe('/companies/' + companyId + '/gst-settings');
});
it('admits reviewed disable commands through the fixed company BFF', () => {
  expect(allowedCompanyRequest('identity', 'POST', '/v1/companies/' + companyId + '/features/budgets/disable')).toBe(true);
  expect(allowedCompanyRequest('identity', 'DELETE', '/v1/companies/' + companyId + '/features/budgets/disable')).toBe(false);
});

it('returns from company configuration to the filtered accounting page that opened it', async () => {
  vi.mocked(companyCall).mockImplementation(() => new Promise(() => {}));
  await renderWithProviders(<CompanyConfiguration session={await administrator()} companyId={companyId} returnTo="/accounting/withholding-sections?status=ACTIVE" />);
  expect(screen.getAllByRole('link').some(link => link.getAttribute('href') === '/accounting/withholding-sections?status=ACTIVE')).toBe(true);
});

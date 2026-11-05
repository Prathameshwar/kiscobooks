import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import SettingsPage from '../app/settings/page';
import OrganisationPage from '../app/organisation/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
beforeEach(async () => {
  vi.mocked(pageContext).mockReset();
  const session = await sessionFor({ permissions: ['company.read', 'role.read', 'notification.provider.read'] });
  session.company = { id: '01990000-0000-7000-8000-000000000001', name: 'Company A' };
  session.grants = [{ permissions: session.permissions, scope_type: 'company', scope_id: session.company.id!, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it('offers company readiness and scoped access, with no platform references or tenant transport cards', async () => {
  render(await SettingsPage());
  expect(screen.getByRole('heading', { name: 'Company settings' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Company readiness' })).toHaveAttribute('href', '/settings/readiness');
  expect(screen.getByRole('link', { name: 'Roles' })).toHaveAttribute('href', '/roles?returnTo=%2Fsettings');
  // Platform-managed references are not this reader's to use, so they are absent rather than disabled.
  expect(screen.queryByRole('article', { name: 'Countries' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Countries' })).not.toBeInTheDocument();
  for (const name of ['Payment gateway', 'Notifications']) expect(screen.queryByRole('article', { name })).not.toBeInTheDocument();
});
it('shows a company admin only authorized child pages in the organisation hub', async () => {
  render(await OrganisationPage());
  expect(screen.getByRole('link', { name: 'Companies' })).toHaveAttribute('href', '/companies/manage');
  expect(screen.getByRole('link', { name: 'Roles' })).toHaveAttribute('href', '/roles');
  for (const name of ['Users', 'User groups', 'Departments']) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Notifications' })).not.toBeInTheDocument();
});
it('offers tenant notification transport only with an active tenant grant', async () => {
  const data = await pageContext(); data.session.grants![0].scope_type = 'tenant';
  render(await OrganisationPage());
  expect(screen.getByRole('link', { name: 'Notifications' })).toHaveAttribute('href', '/settings/notifications');
  expect(screen.getByText(/Notification providers, sender accounts and recipient policies are tenant-wide/)).toBeVisible();
});
it('requests a company selection instead of pretending settings apply without one', async () => {
  const data = await pageContext(); data.session.company = { name: 'Select a company' };
  render(await SettingsPage());
  expect(screen.queryByRole('link', { name: 'Company readiness' })).not.toBeInTheDocument();
  for (const name of ['Financial years', 'Company configuration', 'Product configuration', 'Accounting configuration']) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
});
it('resolves the session per request and does not render after authentication fails', async () => {
  await SettingsPage(); await SettingsPage(); expect(pageContext).toHaveBeenCalledTimes(2);
  vi.mocked(pageContext).mockRejectedValue(new Error('Sign-in required'));
  await expect(SettingsPage()).rejects.toThrow('Sign-in required');
});
it('links the user directory from organisation administration for tenant people administrators', async () => {
  const data = await pageContext(); data.session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: ['user.read'], valid_from: '2000-01-01', valid_to: null }];
  render(await OrganisationPage()); expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
});
it('links authorized company people from settings without exposing the tenant surface', async () => {
  const data = await pageContext(); data.session.grants![0].permissions = ['user.read'];
  render(await SettingsPage()); expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users?returnTo=%2Fsettings');
});
const configurationPermissions = ['period.read', 'company.read', 'product_configuration.read', 'accounting.party.read'];
const configurationCards = ['Financial years', 'Company configuration', 'Product configuration', 'Accounting configuration'];
it.each(['company', 'tenant'] as const)('offers the configuration cards through an active %s grant with settings return links', async scope => {
  const { session } = await pageContext();
  session.grants = [{ scope_type: scope, scope_id: scope === 'company' ? session.company.id! : null, permissions: configurationPermissions, valid_from: '2020-01-01', valid_to: null }];
  render(await SettingsPage());
  const destinations = [`/companies/${session.company.id}/years`, `/companies/${session.company.id}/configuration`, '/products/configuration', '/accounting'];
  configurationCards.forEach((name, index) => expect(screen.getByRole('link', { name })).toHaveAttribute('href', destinations[index] + '?returnTo=%2Fsettings'));
});
it('offers financial years to a period reader without requiring company configuration access', async () => {
  const { session } = await pageContext(); session.grants![0].permissions = ['period.read'];
  render(await SettingsPage());
  expect(screen.getByRole('link', { name: 'Financial years' })).toBeVisible();
  for (const name of configurationCards.slice(1)) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
});

it.each([false, true])('offers voucher types with scoped read access (manage %s)', async manage => {
  const { session } = await pageContext();
  session.permissions = [];
  session.grants![0].permissions = ['vouchers.read', ...(manage ? ['vouchers.type.manage'] : [])];
  render(await SettingsPage());
  expect(screen.getByRole('link', { name: 'Voucher types' })).toHaveAttribute('href', '/masters/voucher-types');
  expect(screen.getByText(manage ? 'Manage voucher types' : 'View voucher types')).toBeVisible();
  expect(screen.queryByText(/No company settings are available/)).not.toBeInTheDocument();
});
it.each(['other company', 'expired', 'manage only', 'no company'])('withholds the voucher types card for %s access', async authority => {
  const { session } = await pageContext();
  session.permissions = ['vouchers.read', 'vouchers.type.manage'];
  session.grants![0].permissions = ['vouchers.read', 'vouchers.type.manage'];
  if (authority === 'other company') session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  if (authority === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (authority === 'manage only') session.grants![0].permissions = ['vouchers.type.manage'];
  if (authority === 'no company') session.company = { name: 'Select a company' };
  render(await SettingsPage());
  expect(screen.queryByRole('link', { name: 'Voucher types' })).not.toBeInTheDocument();
});

it('offers assignments and permissions from company settings using scoped review authority', async () => {
  const { session } = await pageContext();
  session.permissions = [];
  session.grants![0].permissions = ['role.read', 'role.assign'];
  render(await SettingsPage());
  expect(screen.getByRole('link', { name: 'Roles' })).toHaveAttribute('href', '/roles?returnTo=%2Fsettings');
  expect(screen.getByRole('link', { name: 'Role assignments' })).toHaveAttribute('href', '/assignments?returnTo=%2Fsettings');
  expect(screen.getByRole('link', { name: 'Permissions' })).toHaveAttribute('href', '/permissions?returnTo=%2Fsettings');
});
it.each(['other company', 'expired', 'future', 'department', 'platform', 'missing'] as const)('does not offer configuration through a %s grant or role label', async authority => {
  const { session } = await pageContext(); session.permissions = configurationPermissions; session.role = 'Company Admin';
  session.grants![0].permissions = configurationPermissions;
  if (authority === 'other company') session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  if (authority === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (authority === 'future') session.grants![0].valid_from = '2099-01-01';
  if (authority === 'department' || authority === 'platform') session.grants![0].scope_type = authority;
  if (authority === 'missing') session.grants = [];
  render(await SettingsPage());
  for (const name of configurationCards) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
});

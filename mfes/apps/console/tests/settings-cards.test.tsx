import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import SettingsPage from '../app/settings/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));

const company = '01990000-0000-7000-8000-000000000001';
const reads = ['company.read', 'period.read', 'product_configuration.read', 'accounting.party.read', 'warehouse.read', 'user.read', 'role.read'];
beforeEach(async () => {
  vi.mocked(pageContext).mockReset();
  const session = await sessionFor({ permissions: [] });
  session.company = { id: company, name: 'Company A' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: reads, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});

it('groups accessible cards by company setup, business configuration and people', async () => {
  render(await SettingsPage());
  for (const title of ['Company setup', 'Business configuration', 'People and access']) {
    expect(screen.getByRole('heading', { level: 2, name: title })).toBeVisible();
  }
  expect(within(screen.getByRole('region', { name: 'Company setup' })).getByRole('link', { name: 'Financial years' })).toBeVisible();
  expect(within(screen.getByRole('region', { name: 'Business configuration' })).getByRole('link', { name: 'Warehouse settings' })).toHaveAttribute('href', '/masters/warehouses/settings?returnTo=%2Fsettings');
  expect(within(screen.getByRole('region', { name: 'People and access' })).getByRole('link', { name: 'Roles' })).toBeVisible();
});

it('uses review and view actions for readers instead of suggesting management access', async () => {
  render(await SettingsPage());
  const actions = [['Financial years', 'View financial years'], ['Company configuration', 'View company configuration'], ['Product configuration', 'View product configuration'], ['Users', 'View users'], ['Roles', 'Review roles'], ['Role assignments', 'View role assignments']];
  for (const [title, label] of actions) expect(within(screen.getByRole('link', { name: title })).getByText(label)).toBeVisible();
  expect(screen.queryByText('Manage users')).not.toBeInTheDocument();
});

it('offers management labels only for active authority in this company', async () => {
  const { session } = await pageContext();
  session.grants![0].permissions = [...reads, 'company.update', 'period.manage', 'product_configuration.manage', 'user.invite', 'role.assign'];
  session.grants!.push({ scope_type: 'tenant', scope_id: null, permissions: ['role.manage'], valid_from: '2020-01-01', valid_to: null });
  render(await SettingsPage());
  for (const label of ['Configure company', 'Manage financial years', 'Configure products', 'Manage users', 'Manage roles', 'Manage role assignments']) expect(screen.getByText(label)).toBeVisible();
});

it('preserves a Settings return on every related configuration and access card', async () => {
  render(await SettingsPage());
  for (const title of ['Company configuration', 'Financial years', 'Product configuration', 'Accounting configuration', 'Warehouse settings', 'Users', 'Roles', 'Role assignments', 'Permissions']) {
    const target = new URL(screen.getByRole('link', { name: title }).getAttribute('href')!, 'https://console.invalid');
    expect(target.searchParams.get('returnTo')).toBe('/settings');
  }
  expect(screen.getByRole('link', { name: 'Company readiness' })).toHaveAttribute('href', '/settings/readiness');
});

it('opens the invite page directly when a company user can invite but cannot read users', async () => {
  const { session } = await pageContext(); session.grants![0].permissions = ['user.invite'];
  render(await SettingsPage());
  const card = screen.getByRole('link', { name: 'Users' });
  expect(card).toHaveAttribute('href', '/users/new?returnTo=%2Fsettings');
  expect(within(card).getByText('Invite user')).toBeVisible();
});

it.each(['other company', 'expired', 'future', 'missing'] as const)('does not show company access or empty sections for %s authority', async authority => {
  const { session } = await pageContext();
  session.permissions = [...reads, 'role.assign'];
  if (authority === 'other company') session.grants![0].scope_id = '01990000-0000-7000-8000-000000000002';
  if (authority === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (authority === 'future') session.grants![0].valid_from = '2099-01-01';
  if (authority === 'missing') session.grants = [];
  render(await SettingsPage());
  for (const title of ['Users', 'Roles', 'Role assignments', 'Permissions', 'Company readiness', 'Warehouse settings']) expect(screen.queryByRole('link', { name: title })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
  expect(screen.getByText('No company settings are available with your current access.')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Review my access' })).toHaveAttribute('href', '/my-access');
});

it('does not borrow assignment management from a different company', async () => {
  const { session } = await pageContext();
  session.grants!.push({ scope_type: 'company', scope_id: '01990000-0000-7000-8000-000000000002', permissions: ['role.assign'], valid_from: '2020-01-01', valid_to: null });
  render(await SettingsPage());
  expect(within(screen.getByRole('link', { name: 'Role assignments' })).getByText('View role assignments')).toBeVisible();
  expect(screen.queryByText('Manage role assignments')).not.toBeInTheDocument();
});

it('offers warehouse configuration to a publisher who can read the settings', async () => {
  const { session } = await pageContext(); session.grants![0].permissions = ['warehouse.read', 'warehouse.publish'];
  render(await SettingsPage());
  expect(within(screen.getByRole('link', { name: 'Warehouse settings' })).getByText('Configure warehouses')).toBeVisible();
});

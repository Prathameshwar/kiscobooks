import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import SettingsPage from '../app/settings/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
const catalogs = ['Countries', 'States', 'Currencies', 'Languages', 'Timezones'];
const company = '01990000-0000-7000-8000-000000000001';
beforeEach(async () => {
  const session = await sessionFor({ permissions: ['platform.config.manage'] });
  session.company = { name: 'Select a company' };
  session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: ['platform.config.manage'], valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
it.each(['tenant', 'platform'] as const)('enables all five platform reference shortcuts with active %s authority and no company', async scope => {
  const { session } = await pageContext(); session.grants![0].scope_type = scope;
  render(await SettingsPage());
  const section = screen.getByRole('region', { name: 'Global references' });
  for (const name of catalogs) expect(within(section).getByRole('link', { name })).toHaveAttribute('href', '/platform/references/' + name.toLowerCase());
  expect(within(screen.getByRole('link', { name: 'Timezones' })).getByText('Browse timezones')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Company configuration' })).not.toBeInTheDocument();
});
it('shows an authorised company reader nothing about platform-only references, not even disabled', async () => {
  const { session } = await pageContext(); session.permissions = ['company.read']; session.company = { id: company, name: 'Company A' };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions: ['company.read'], valid_from: '2020-01-01', valid_to: null }];
  render(await SettingsPage());
  expect(screen.queryByRole('region', { name: 'Global references' })).not.toBeInTheDocument();
  expect(screen.queryByText('Platform managed')).not.toBeInTheDocument();
  expect(screen.queryByText('Platform access required')).not.toBeInTheDocument();
  for (const name of catalogs) {
    expect(screen.queryByRole('article', { name })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
  }
  // The company's own settings are untouched by hiding the section.
  expect(screen.getByRole('link', { name: 'Company readiness' })).toBeVisible();
});
it('still offers a platform administrator the five references while a company is open', async () => {
  const { session } = await pageContext(); session.company = { id: company, name: 'Company A' };
  render(await SettingsPage());
  const section = screen.getByRole('region', { name: 'Global references' });
  for (const name of catalogs) expect(within(section).getByRole('link', { name })).toHaveAttribute('href', '/platform/references/' + name.toLowerCase());
  expect(screen.queryByText('Platform managed')).not.toBeInTheDocument();
});
it.each(['expired', 'future', 'company', 'department', 'missing', 'stale effective permission'] as const)('hides references without valid global or company authority (%s)', async reason => {
  const { session } = await pageContext(); session.company = { id: company, name: 'Company A' }; session.role = 'Platform Admin';
  if (reason === 'expired') session.grants![0].valid_to = '2020-01-01';
  if (reason === 'future') session.grants![0].valid_from = '2099-01-01';
  if (reason === 'company' || reason === 'department') { session.grants![0].scope_type = reason; session.grants![0].scope_id = company; }
  if (reason === 'missing') session.grants = [];
  if (reason === 'stale effective permission') session.permissions = [];
  render(await SettingsPage());
  expect(screen.queryByRole('region', { name: 'Global references' })).not.toBeInTheDocument();
});
it('does not expose another company’s reference shortcuts to a company reader', async () => {
  const { session } = await pageContext(); session.permissions = ['company.read']; session.company = { id: company, name: 'Company A' };
  session.grants![0] = { scope_type: 'company', scope_id: '01990000-0000-7000-8000-000000000002', permissions: ['company.read'], valid_from: '2020-01-01', valid_to: null };
  render(await SettingsPage());
  expect(screen.queryByRole('region', { name: 'Global references' })).not.toBeInTheDocument();
});

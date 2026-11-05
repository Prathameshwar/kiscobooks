import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import PlatformPage from '../app/platform/page';
const { session, identity } = vi.hoisted(() => ({ session: vi.fn(), identity: vi.fn() }));
vi.mock('../app/session', () => ({ getSession: session }));
vi.mock('../app/lib/page-context', async () => {
  // Pages resolve the session and the company context through one helper now; the session
  // mock above still decides what that helper returns.
  const { getSession } = await import('../app/session');
  return { pageContext: async () => ({ session: await getSession(),
    context: { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null } }) };
});
vi.mock('../app/identity-session', () => ({ identityFetch: identity }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
beforeEach(() => { session.mockReset(); identity.mockReset(); session.mockResolvedValue({ permissions: ['platform.tenant.read'] }); });
it('offers tenant administrators, their role and permissions with platform access authority', async () => {
  session.mockResolvedValue({ permissions: ['platform.tenant_access.read'] }); render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Tenant administrators' })).toHaveAttribute('href', '/platform/access/administrators');
  expect(screen.getByRole('link', { name: 'Tenant administrator role' })).toHaveAttribute('href', '/platform/access/role');
  expect(screen.getByRole('link', { name: 'Administrator permissions' })).toHaveAttribute('href', '/platform/access/permissions');
});
it('offers platform notifications with their own read grant', async () => {
  session.mockResolvedValue({ permissions: ['platform.notification_provider.read'] }); render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Platform notifications' })).toHaveAttribute('href', '/platform/notifications');
  expect(screen.queryByRole('link', { name: 'Manage tenants' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'View platform history' })).toHaveAttribute('href', '/platform/history');
});
it.each(['recipient.read', 'consent.manage', 'suppression.manage'])('keeps the notification card reachable with only %s', async grant => {
  session.mockResolvedValue({ permissions: ['platform.notification_' + grant] }); render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Platform notifications' })).toHaveAttribute('href', '/platform/notifications');
  expect(screen.queryByRole('link', { name: 'Manage tenants' })).not.toBeInTheDocument();
});
it('offers the approval directory only to account readers', async () => {
  session.mockResolvedValue({ permissions: ['platform.account.read'] }); render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Account approvals' })).toHaveAttribute('href', '/platform/accounts');
  expect(screen.queryByRole('link', { name: 'Manage tenants' })).not.toBeInTheDocument();
});
it('offers tenant management without an unconditional sign-in prompt or fetching the directory', async () => {
  render(await PlatformPage());
  expect(screen.getByRole('heading', { name: 'Platform administration' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Manage tenants' })).toHaveAttribute('href', '/platform/tenants');
  expect(screen.queryByRole('link', { name: 'Sign in again' })).not.toBeInTheDocument();
  expect(identity).not.toHaveBeenCalled();
  expect(screen.getByRole('link', { name: 'View platform history' })).toHaveAttribute('href', '/platform/history');
});
it('does not offer cross-tenant controls without permission', async () => {
  session.mockResolvedValue({ permissions: [] }); render(await PlatformPage());
  expect(screen.getByRole('alert')).toHaveTextContent('permission is required');
  expect(screen.queryByRole('link', { name: 'Manage tenants' })).not.toBeInTheDocument();
});
it('offers configuration and pricing to platform managers', async () => {
  session.mockResolvedValue({ permissions: ['platform.tenant.read', 'platform.config.manage'] }); render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Edit platform details' })).toHaveAttribute('href', '/platform/details');
  expect(screen.getByRole('link', { name: 'Fees and pricing' })).toHaveAttribute('href', '/platform/pricing');
});
it('hides platform editing for directory readers', async () => {
  render(await PlatformPage()); expect(screen.queryByRole('link', { name: 'Edit platform details' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Fees and pricing' })).not.toBeInTheDocument();
});
it('does not offer a circular overview link to a company-less operator', async () => {
  session.mockResolvedValue({ permissions: ['platform.tenant.read'], company: { name: 'Select a company' } });
  render(await PlatformPage());
  expect(screen.queryAllByRole('link', { name: /business overview/i })).toHaveLength(0);
});
it('keeps the overview link when a company is selected', async () => {
  session.mockResolvedValue({ permissions: ['platform.tenant.read'], company: { id: 'company-a', name: 'A' } });
  render(await PlatformPage());
  expect(screen.getByRole('link', { name: 'Back to business overview' })).toHaveAttribute('href', '/');
});

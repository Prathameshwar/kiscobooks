import type { ReactNode } from 'react';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Page from '../app/logs-and-activities/page';
import { pageContext } from '../app/lib/page-context';
import { EMPTY_CONTEXT, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children, activeHref }: { children: ReactNode; activeHref: string }) => <main data-active={activeHref}>{children}</main> }));
vi.mock('../app/components/NoCompany', () => ({ NoCompany: () => <p>Open a company</p> }));

async function scope(permissions: string[], options: { company?: string; grantCompany?: string; expiry?: string; tenant?: boolean } = {}) {
  const session = await sessionFor({ permissions });
  session.company.id = options.company ?? 'company';
  session.grants = [{ scope_type: options.tenant ? 'tenant' : 'company', scope_id: options.grantCompany ?? session.company.id, permissions, valid_from: '2000-01-01', valid_to: options.expiry ?? null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: EMPTY_CONTEXT });
  return session;
}
beforeEach(() => vi.clearAllMocks());

it('offers exactly two accessible destination cards and the business back link', async () => {
  await scope(['audit.read', 'activity.read']);
  render(await Page());
  expect(screen.getByRole('heading', { level: 1, name: 'Logs and activities' })).toBeVisible();
  const audit = screen.getByRole('link', { name: 'Audit logs' });
  const activities = screen.getByRole('link', { name: 'Activities' });
  expect(audit).toHaveAttribute('href', '/audit');
  expect(activities).toHaveAttribute('href', '/activity');
  expect(within(audit).queryByRole('button')).not.toBeInTheDocument();
  expect(within(activities).queryByRole('button')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /back to business overview/i })).toHaveAttribute('href', '/');
  expect(screen.getByRole('main')).toHaveAttribute('data-active', '/logs-and-activities');
});

it.each([
  ['audit.read', 'Audit logs', '/audit', 'Activity read access'],
  ['activity.read', 'Activities', '/activity', 'Audit read access'],
])('allows only the card authorized by %s', async (permission, title, href, denied) => {
  await scope([permission]); render(await Page());
  expect(screen.getByRole('link', { name: title })).toHaveAttribute('href', href);
  expect(screen.getByText(new RegExp(denied))).toBeVisible();
  expect(screen.queryByRole('link', { name: permission === 'audit.read' ? 'Activities' : 'Audit logs' })).not.toBeInTheDocument();
});

it.each(['none', 'other-company', 'expired'])('rejects unauthorized %s access without showing history cards', async mode => {
  await scope(mode === 'none' ? [] : ['audit.read', 'activity.read'], { grantCompany: mode === 'other-company' ? 'other' : 'company', expiry: mode === 'expired' ? '2001-01-01' : undefined });
  render(await Page());
  expect(screen.queryByRole('heading', { name: 'Audit logs' })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Activities' })).not.toBeInTheDocument();
  expect(screen.getByText("You don't have access to this")).toBeVisible();
});

it('admits a valid tenant grant for the current company', async () => {
  await scope(['audit.read', 'activity.read'], { tenant: true }); render(await Page());
  expect(screen.getByRole('link', { name: 'Audit logs' })).toBeVisible();
});

it('requires a selected company even when flat permissions exist', async () => {
  const session = await scope(['audit.read', 'activity.read']); delete session.company.id;
  render(await Page());
  expect(screen.getByText('Open a company')).toBeVisible();
  expect(screen.queryByRole('heading', { name: 'Audit logs' })).not.toBeInTheDocument();
});

it('does not render history when session resolution fails', async () => {
  vi.mocked(pageContext).mockRejectedValue(new Error('Session unavailable'));
  await expect(Page()).rejects.toThrow('Session unavailable');
});

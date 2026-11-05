import { render, screen } from '@testing-library/react';
import { beforeEach, expect, expectTypeOf, it, vi } from 'vitest';
import Page from '../app/activity/page';

const { context, feed } = vi.hoisted(() => ({ context: vi.fn(), feed: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: context }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ActivityFeed', () => ({ ActivityFeed: (props: object) => { feed(props); return <p>Company activity</p>; } }));
vi.mock('../app/components/NoCompany', () => ({ NoCompany: () => <p>Open a company</p> }));
beforeEach(() => feed.mockClear());

it('accepts the props object required by generated Next page validation', () => {
  expectTypeOf<Parameters<typeof Page>[0]>().toEqualTypeOf<{ searchParams?: Promise<{ scope?: string | string[] }> }>();
});

it.each(['company', 'other'])('requires the activity grant for the company currently open: %s', async scope => {
  context.mockResolvedValue({ session: { company: { id: 'company' }, permissions: ['activity.read'], grants: [{ scope_type: 'company', scope_id: scope, valid_from: '2020-01-01', valid_to: null, permissions: ['activity.read'] }] }, context: {} });
  render(await Page({}));
  expect(feed).toHaveBeenCalledTimes(scope === 'company' ? 1 : 0);
});

it('requires a company before mounting the activity loader', async () => {
  context.mockResolvedValue({ session: { company: {}, permissions: ['activity.read'] }, context: {} });
  render(await Page({}));
  expect(screen.getByText('Open a company')).toBeVisible();
  expect(feed).not.toHaveBeenCalled();
});

it.each(['tenant', 'company'])('requires an actual %s grant for organisation activity', async scope => {
  context.mockResolvedValue({ session: { company: { id: 'company' }, permissions: ['activity.read'], grants: [{ scope_type: scope, scope_id: scope === 'company' ? 'company' : null, valid_from: '2020-01-01', valid_to: null, permissions: ['activity.read'] }] }, context: {} });
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation' }) }));
  expect(feed).toHaveBeenCalledTimes(scope === 'tenant' ? 1 : 0);
  if (scope === 'tenant') expect(feed).toHaveBeenCalledWith(expect.objectContaining({ organisation: true, canOrganisation: true }));
});

it('rejects invalid activity scope before mounting a loader', async () => {
  context.mockResolvedValue({ session: { company: { id: 'company' }, permissions: ['activity.read'], grants: [{ scope_type: 'tenant', valid_from: '2020-01-01', valid_to: null, permissions: ['activity.read'] }] }, context: {} });
  render(await Page({ searchParams: Promise.resolve({ scope: ['company', 'organisation'] }) }));
  expect(feed).not.toHaveBeenCalled();
});

it('rejects expired tenant activity authority', async () => {
  context.mockResolvedValue({ session: { company: { id: 'company' }, permissions: ['activity.read'], grants: [{ scope_type: 'tenant', valid_from: '2000-01-01', valid_to: '2001-01-01', permissions: ['activity.read'] }] }, context: {} });
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation' }) }));
  expect(feed).not.toHaveBeenCalled();
});

it('does not grant organisation audit navigation using a company-only audit grant', async () => {
  context.mockResolvedValue({ session: { company: { id: 'company' }, permissions: ['activity.read', 'audit.read'], grants: [
    { scope_type: 'tenant', valid_from: '2000-01-01', valid_to: null, permissions: ['activity.read'] },
    { scope_type: 'company', scope_id: 'company', valid_from: '2000-01-01', valid_to: null, permissions: ['audit.read'] },
  ] }, context: {} });
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation' }) }));
  expect(feed).toHaveBeenCalledWith(expect.objectContaining({ canAudit: false }));
});

it('allows tenant-wide activities without inventing a selected company', async () => {
  context.mockResolvedValue({ session: { company: {}, permissions: ['activity.read'], grants: [{ scope_type: 'tenant', valid_from: '2000-01-01', valid_to: null, permissions: ['activity.read'] }] }, context: {} });
  render(await Page({ searchParams: Promise.resolve({ scope: 'organisation' }) }));
  expect(feed).toHaveBeenCalledWith(expect.objectContaining({ organisation: true, company: '' }));
});

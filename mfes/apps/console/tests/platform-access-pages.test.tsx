import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import PlatformAccessPage from '../app/platform/access/[[...segments]]/page';
import { flattenNavigation, navigationFor } from '../app/nav';
import { sessionFor } from './helpers';
const { context } = vi.hoisted(() => ({ context: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: context }));
vi.mock('../app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/platform/access/PlatformAdministratorDirectory', () => ({
  PlatformAdministratorDirectory: ({ canManage }: { canManage: boolean }) => (
    <p>Administrator directory: {canManage ? 'manager' : 'reader'}</p>
  ),
}));
vi.mock('../app/platform/access/PlatformAdministratorEditor', () => ({
  PlatformAdministratorEditor: () => <p>Administrator editor</p>,
}));
vi.mock('../app/platform/access/PlatformAdministratorDetail', () => ({
  PlatformAdministratorDetail: () => <p>Administrator detail</p>,
}));
vi.mock('../app/platform/access/PlatformAccessOverview', () => ({
  PlatformAccessOverview: () => <p>Access overview</p>,
  PlatformAdministratorRole: ({
    permissionsOnly,
  }: {
    permissionsOnly: boolean;
  }) => (
    <p>{permissionsOnly ? 'Permissions catalogue' : 'Administrator role'}</p>
  ),
}));
const tenant = '01900000-0000-7000-8000-000000000001',
  user = '01900000-0000-7000-8000-000000000002';
async function session(permissions: string[]) {
  return {
    ...(await sessionFor({ permissions })),
    role: 'platform_admin',
    grants: [],
    company: { name: 'No company' },
  };
}
beforeEach(async () => {
  context.mockResolvedValue({
    session: await session([
      'platform.tenant_access.read',
      'platform.tenant_access.manage',
    ]),
    context: {},
  });
});
const page = (segments: string[], query: Record<string, string> = {}) =>
  PlatformAccessPage({
    params: Promise.resolve({ segments }),
    searchParams: Promise.resolve(query),
  });
it('shows platform access navigation without a company or ordinary tenant grants', async () => {
  const links = navigationFor(await session(['platform.tenant_access.read']))
    .flatMap((section) => flattenNavigation(section.items))
    .map((item) => item.href);
  for (const href of [
    '/platform',
    '/platform/access',
    '/platform/access/administrators',
    '/platform/access/role',
    '/platform/access/permissions',
  ])
    expect(links).toContain(href);
  for (const href of ['/users', '/roles', '/permissions'])
    expect(links).not.toContain(href);
});
it('does not grant platform navigation from the account-type label', async () => {
  expect(
    navigationFor(await session([]))
      .flatMap((section) => flattenNavigation(section.items))
      .map((item) => item.href),
  ).not.toContain('/platform/access');
});
it.each([
  ['', 'Access overview'],
  ['administrators', 'Administrator directory: manager'],
  ['role', 'Administrator role'],
  ['permissions', 'Permissions catalogue'],
])('opens the implemented %s page', async (segment, text) => {
  render(await page(segment ? [segment] : []));
  expect(screen.getByText(text)).toBeInTheDocument();
});
it('opens native detail and edit pages for a named tenant', async () => {
  render(await page(['administrators', user], { tenant }));
  expect(screen.getByText('Administrator detail')).toBeInTheDocument();
});
it('allows administrator creation only with explicit management authority', async () => {
  render(await page(['administrators', 'new'], { tenant }));
  expect(screen.getByText('Administrator editor')).toBeInTheDocument();
});
it.each([
  ['administrators', 'new'],
  ['administrators', user, 'edit'],
])(
  'denies direct manager routes to platform readers (%s)',
  async (...segments) => {
    context.mockResolvedValue({
      session: await session(['platform.tenant_access.read']),
      context: {},
    });
    render(await page(segments, { tenant }));
    expect(screen.getByRole('alert')).toHaveTextContent('unavailable');
  },
);
it('denies reads without permission and does not accept missing tenant context', async () => {
  context.mockResolvedValue({ session: await session([]), context: {} });
  render(await page(['administrators']));
  expect(screen.getByRole('alert')).toHaveTextContent('permission is required');
});

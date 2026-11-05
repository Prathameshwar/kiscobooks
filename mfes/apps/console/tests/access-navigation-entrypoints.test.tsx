import { screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrganisationOverview } from '../app/components/OrganisationOverview';
import { AccessDirectory } from '../app/components/AccessDirectory';
import { ConsoleShell } from '../app/components/ConsoleShell';
import { RoleDetail } from '../app/components/RoleDetail';
import { navigationFor, flattenNavigation } from '../app/nav';
import { serviceCall } from '../app/lib/service-call';
import {
  access,
  companyId,
  page,
  roleRecord,
  userRecord,
  roleId,
  userId,
} from './access-fixtures';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  authActionUrl: (path: string) => path,
}));
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/');
  vi.mocked(serviceCall).mockResolvedValue(page([userRecord]));
});

it('focuses the role permission section after its record loads for a permissions shortcut', async () => {
  window.history.replaceState(
    null,
    '',
    '/roles/' + roleId + '#role-permissions',
  );
  vi.mocked(serviceCall).mockImplementation(async (_, request) =>
    request.path === '/v1/permissions'
      ? ({ permissions: ['invoice.read'] } as never)
      : (roleRecord as never),
  );
  await renderWithProviders(<RoleDetail context={access} id={roleId} />);
  const section = await screen.findByRole('region', { name: 'Role permission details' });
  await waitFor(() => expect(section).toHaveFocus());
});

it('offers view-only assignment shortcuts to readers', async () => {
  await renderWithProviders(
    <AccessDirectory
      resource="users"
      context={{
        ...access,
        permissions: ['user.read', 'role.read'],
        tenantPermissions: ['user.read', 'role.read'],
      }}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for Ava Singh/ }),
  );
  expect(
    screen.getByRole('menuitem', { name: 'View role assignments' }),
  ).toHaveAttribute('href', expect.stringContaining('/assignments?'));
  expect(
    screen.queryByRole('menuitem', { name: 'Manage role assignments' }),
  ).not.toBeInTheDocument();
});

it('keeps platform access separate from ordinary tenant users and roles', async () => {
  const session = await sessionFor({
    permissions: ['platform.tenant_access.read', 'platform.tenant.read'],
  });
  session.company = { name: 'Select company' };
  session.grants = [
    {
      scope_type: 'tenant',
      scope_id: null,
      permissions: session.permissions,
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  const destinations = flattenNavigation(
    navigationFor(session).flatMap((section) => section.items),
  ).map((item) => item.href);
  expect(destinations).toContain('/platform/access/administrators');
  expect(destinations).toContain('/platform/access/role');
  expect(destinations).toContain('/platform/access/permissions');
  for (const path of ['/users', '/roles', '/permissions', '/assignments'])
    expect(destinations).not.toContain(path);
});

it('keeps My access available without administrative permissions', async () => {
  const session = await sessionFor({ permissions: [] });
  session.grants = [];
  const destinations = flattenNavigation(
    navigationFor(session).flatMap((section) => section.items),
  ).map((item) => item.href);
  expect(destinations).toContain('/my-access');
  for (const path of ['/users', '/roles', '/permissions', '/assignments'])
    expect(destinations).not.toContain(path);
});
async function administrator(scope: 'tenant' | 'company' = 'tenant') {
  const permissions = [...access.permissions];
  if (scope === 'company')
    permissions.splice(permissions.indexOf('role.manage'), 1);
  const session = await sessionFor({ permissions });
  session.company = { id: companyId, name: 'Retail' };
  session.grants = [
    {
      scope_type: scope,
      scope_id: scope === 'tenant' ? null : companyId,
      permissions,
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  return session;
}

it('provides direct cards for roles, assignments and permissions from organisation administration', async () => {
  await renderWithProviders(
    <OrganisationOverview session={await administrator()} />,
  );
  const roles = screen.getByRole('link', { name: 'Roles' });
  expect(roles).toHaveAttribute('href', '/roles');
  expect(within(roles).getByText('Manage roles')).toBeVisible();
  expect(
    screen.getByRole('link', { name: 'Role assignments' }),
  ).toHaveAttribute('href', '/assignments');
  expect(screen.getByRole('link', { name: 'Permissions' })).toHaveAttribute(
    'href',
    '/permissions',
  );
});

it('offers review and assignment cards to company admins without custom-role management', async () => {
  await renderWithProviders(
    <OrganisationOverview session={await administrator('company')} />,
  );
  expect(
    within(screen.getByRole('link', { name: 'Roles' })).getByText(
      'Review roles',
    ),
  ).toBeVisible();
  expect(screen.getByText('Manage role assignments')).toBeVisible();
  expect(screen.queryByText('Manage roles')).not.toBeInTheDocument();
});

it('groups roles, assignments and permissions under their card hub and highlights it', async () => {
  const session = await administrator();
  const items = navigationFor(session).flatMap((section) => section.items);
  const organisation = items.find((item) => item.href === '/organisation')!;
  const roles = organisation.children!.find((item) => item.href === '/organisation/access')!;
  expect(roles.children?.map((item) => item.href)).toEqual([
    '/roles',
    '/assignments',
    '/permissions',
  ]);
  const destinations = flattenNavigation(items).map((item) => item.href);
  expect(destinations.filter((path) => path === '/permissions')).toHaveLength(
    1,
  );
  await renderWithProviders(
    <ConsoleShell
      session={session}
      context={companyContextFor()}
      activeHref="/permissions"
    >
      <p>Permissions page</p>
    </ConsoleShell>,
  );
  expect(screen.getByRole('link', { name: 'Roles & access' })).toHaveAttribute(
    'aria-current',
    'page',
  );
});

it('opens user assignments from the row menu while preserving the user directory', async () => {
  await renderWithProviders(
    <AccessDirectory
      resource="users"
      context={access}
      initialQuery="status=active"
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for Ava Singh/ }),
  );
  const url = new URL(
    screen
      .getByRole('menuitem', { name: 'Manage role assignments' })
      .getAttribute('href')!,
    'https://console.invalid',
  );
  expect(url.searchParams.get('subject_id')).toBe(userId);
  expect(url.searchParams.get('subject_type')).toBe('user');
  expect(url.searchParams.get('returnTo')).toContain('/users?status=active');
});

it('opens role permissions and filtered assignments from the role row', async () => {
  vi.mocked(serviceCall).mockResolvedValue(page([roleRecord]));
  await renderWithProviders(
    <AccessDirectory resource="roles" context={access} />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: /Actions for Viewer/ }),
  );
  expect(
    screen.getByRole('menuitem', { name: 'View role permissions' }),
  ).toHaveAttribute('href', expect.stringContaining('/roles/' + roleId));
  const url = new URL(
    screen
      .getByRole('menuitem', { name: 'Manage role assignments' })
      .getAttribute('href')!,
    'https://console.invalid',
  );
  expect(url.pathname).toBe('/assignments');
  expect(url.searchParams.get('role_id')).toBe(roleId);
});

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { navigationFor, type NavItem } from '../app/nav';
import { ConsoleShell } from '../app/components/ConsoleShell';
import { AccessNavigation } from '../app/components/AccessCommon';
import { accessContext } from '../app/lib/access-context';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), authActionUrl: (path: string) => 'http://localhost:4310' + path }));
type TreeItem = NavItem & { children?: TreeItem[] };
const flatten = (items: TreeItem[]): TreeItem[] => items.flatMap(item => [item, ...flatten(item.children ?? [])]);
async function administrator() {
  const keys = ['company.read', 'department.read', 'group.read', 'user.read', 'role.read'];
  const session = await sessionFor({ permissions: keys });
  return { ...session, company: { ...session.company, id: '01990000-0000-7000-8000-000000000003' }, grants: [{ scope_type: 'tenant', scope_id: null, permissions: keys, valid_from: '2000-01-01', valid_to: null }] };
}
it('groups the organization masters under their working administration hub', async () => {
  const session = await administrator();
  const items = navigationFor(session).flatMap(section => section.items) as TreeItem[];
  const hub = items.find(item => item.href === '/organisation');
  expect(flatten(hub?.children ?? []).map(item => item.href)).toEqual(expect.arrayContaining(['/companies/manage', '/departments', '/users', '/user-groups', '/roles', '/assignments', '/permissions']));
});
it('exposes permitted tenant and reference destinations in the shared navigation tree', async () => {
  const session = await sessionFor({ permissions: ['platform.tenant.read', 'platform.config.manage'] });
  const hrefs = flatten(navigationFor(session).flatMap(section => section.items)).map(item => item.href);
  expect(hrefs).toContain('/platform/tenants'); expect(hrefs).toContain('/platform/references/countries'); expect(hrefs).toContain('/platform/references/timezones');
});
it('has an explicit directory back destination and organization breadcrumbs', async () => {
  const session = await administrator();
  await renderWithProviders(<AccessNavigation context={accessContext(session)} {...{ resource: 'users' as const }} />);
  expect(screen.getByRole('link', { name: 'Back to administration' })).toHaveAttribute('href', '/organisation');
  expect(within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByText('Users')).toHaveAttribute('aria-current', 'page');
});
it('includes authorized company navigation alongside the access masters', async () => {
  const session = await administrator(); await renderWithProviders(<AccessNavigation context={accessContext(session)} />);
  expect(screen.getByRole('link', { name: 'Companies' })).toHaveAttribute('href', '/companies/manage');
});
it('offers only working account actions and omits missing support destinations', async () => {
  const session = await administrator(), user = userEvent.setup();
  await renderWithProviders(<ConsoleShell session={session} context={companyContextFor()} activeHref="/users"><p>Users</p></ConsoleShell>);
  await user.click(screen.getByRole('button', { name: new RegExp(session.user.name) }));
  expect(screen.queryByRole('menuitem', { name: 'Your profile' })).not.toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: 'Preferences' })).not.toBeInTheDocument();
  for (const path of ['/status', '/docs', '/help', '/feedback']) expect(document.querySelector(`a[href="${path}"]`)).toBeNull();
});

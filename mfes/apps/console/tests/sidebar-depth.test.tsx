import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ConsoleShell } from '../app/components/ConsoleShell';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), authActionUrl: (path: string) => path }));

async function mount(path: string, permissions: string[]) {
  const session = await sessionFor({ permissions });
  session.grants = [{ scope_type: 'tenant', scope_id: null, permissions, valid_from: '2000-01-01', valid_to: null }];
  return renderWithProviders(<ConsoleShell session={session} context={companyContextFor()} activeHref={path}><p>Page content</p></ConsoleShell>);
}

it.each([
  ['/platform/access/administrators/01990000-0000-7000-8000-000000000001', 'platform.tenant_access.read', 'Users, roles and permissions', '/platform/access', 'Tenant administrators'],
  ['/platform/references/states/IN-MH/edit', 'platform.config.manage', 'Reference data', '/platform/references', 'States'],
  ['/platform/notifications/templates', 'platform.notification_template.read', 'Platform notifications', '/platform/notifications', 'Templates'],
  ['/settings/notifications/templates', 'notification.template.read', 'Notifications', '/settings/notifications', 'Templates'],
  ['/permissions', 'role.read', 'Roles & access', '/organisation/access', 'Permissions'],
  ['/roles/01990000-0000-7000-8000-000000000001/edit', 'role.read', 'Roles & access', '/organisation/access', 'Roles'],
])('opens deeper %s pages under their visible card hub', async (path, permission, label, href, hiddenLabel) => {
  const { container } = await mount(path, [permission]);
  const rail = within(container.querySelector('.janso-rail__nav') as HTMLElement);
  expect(container.querySelector('.janso-rail-group .janso-rail-group')).toBeNull();
  expect(rail.getByRole('link', { name: label })).toHaveAttribute('href', href);
  expect(rail.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page');
  expect(rail.queryByRole('link', { name: hiddenLabel })).not.toBeInTheDocument();
  expect(rail.getAllByRole('link', { current: 'page' })).toHaveLength(1);
  expect(rail.queryByRole('button', { name: new RegExp(label + ' menu') })).not.toBeInTheDocument();
});

it('retains deeper authorized destinations in keyboard search', async () => {
  await mount('/platform/access', ['platform.tenant_access.read']);
  await userEvent.keyboard('{Control>}k{/Control}');
  expect(screen.getByRole('option', { name: /Tenant administrators/ })).toBeVisible();
  expect(screen.getByRole('option', { name: /Administrator permissions/ })).toBeVisible();
  expect(screen.queryByRole('option', { name: /Reference data/ })).not.toBeInTheDocument();
});

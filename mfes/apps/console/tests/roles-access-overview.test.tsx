import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import RolesAccessPage from '../app/organisation/access/page';
import { AccessNavigation } from '../app/components/AccessCommon';
import { accessContext } from '../app/lib/access-context';
import { administrationReturn } from '../app/lib/administration-navigation';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

const { pageContext } = vi.hoisted(() => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), authActionUrl: (path: string) => path }));
beforeEach(() => vi.clearAllMocks());

async function administrator(permissions: string[], scope: 'tenant' | 'company' = 'tenant') {
  const session = await sessionFor({ permissions });
  const companyId = '01990000-0000-7000-8000-000000000001';
  session.company = scope === 'company' ? { id: companyId, name: 'Retail' } : { name: 'Select company' };
  session.grants = [{ scope_type: scope, scope_id: scope === 'company' ? companyId : null, permissions, valid_from: '2000-01-01', valid_to: null }];
  return session;
}

it.each(['tenant', 'company'] as const)('opens the real access landing route for %s administrators with scoped actions', async scope => {
  const keys = scope === 'tenant' ? ['role.read', 'role.manage', 'role.assign'] : ['role.read', 'role.assign'];
  const session = await administrator(keys, scope);
  pageContext.mockResolvedValue({ session, context: companyContextFor() });
  render(await RolesAccessPage());
  const main = within(screen.getByRole('main'));
  for (const [label, path] of [['Roles', '/roles'], ['Role assignments', '/assignments'], ['Permissions', '/permissions']]) {
    const card = main.getByRole('link', { name: label });
    expect(card).toHaveClass('janso-action-card');
    const url = new URL(card.getAttribute('href')!, 'https://console.invalid');
    expect(url.pathname).toBe(path);
    expect(url.searchParams.get('returnTo')).toBe('/organisation/access');
  }
  expect(main.getByText(scope === 'tenant' ? 'Manage roles' : 'Review roles')).toBeVisible();
  expect(main.getByText('Manage role assignments')).toBeVisible();
  expect(main.getByRole('link', { name: 'Back to administration' })).toHaveAttribute('href', '/organisation');
});

it.each([{ permissions: [] }, { permissions: ['platform.tenant_access.read'] }])('denies ordinary role cards without role review authority: $permissions', async ({ permissions }) => {
  const session = await administrator(permissions);
  pageContext.mockResolvedValue({ session, context: companyContextFor() });
  render(await RolesAccessPage());
  const main = within(screen.getByRole('main'));
  expect(main.getByRole('alert')).toHaveTextContent('Role read permission is required');
  expect(main.queryByRole('link', { name: 'Roles' })).not.toBeInTheDocument();
});

it.each(['roles', 'assignments', 'permissions'] as const)('returns %s to the validated card hub', async resource => {
  const session = await administrator(['role.read']);
  const back = administrationReturn(resource, '/organisation/access');
  await renderWithProviders(<AccessNavigation context={accessContext(session)} resource={resource} back={back} />);
  expect(screen.getByRole('link', { name: 'Back to roles and access' })).toHaveAttribute('href', '/organisation/access');
  for (const value of ['//evil.invalid/organisation/access', '/organisation/access/new', '/organisation/access?returnTo=//evil.invalid'])
    expect(administrationReturn(resource, value)).toBe('/' + resource);
});

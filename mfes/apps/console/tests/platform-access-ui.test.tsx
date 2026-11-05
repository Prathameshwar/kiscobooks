import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PlatformAdministratorDirectory } from '../app/platform/access/PlatformAdministratorDirectory';
import { PlatformAdministratorDetail } from '../app/platform/access/PlatformAdministratorDetail';
import { PlatformAdministratorEditor } from '../app/platform/access/PlatformAdministratorEditor';
import {
  PlatformAdministratorRole,
  PlatformAccessOverview,
} from '../app/platform/access/PlatformAccessOverview';
import {
  administratorReturn,
  allowedPlatformRequest,
} from './platform-access-test-helpers';

const { call, navigate } = vi.hoisted(() => ({
  call: vi.fn(),
  navigate: vi.fn(),
}));
vi.mock('../app/lib/platform-api', async () => ({
  ...(await vi.importActual('../app/lib/platform-api')),
  platformCall: call,
}));
vi.mock('../app/lib/navigate', async () => ({
  ...(await vi.importActual('../app/lib/navigate')),
  goTo: navigate,
}));
vi.mock('../app/components/PlatformHistory', () => ({
  PlatformHistory: () => <p>Administrative history</p>,
}));
const tenant = '01900000-0000-7000-8000-000000000001',
  user = '01900000-0000-7000-8000-000000000002',
  assignment = '01900000-0000-7000-8000-000000000003';
const time = '2026-10-25T00:00:00Z';
const customer = { id: tenant, name: 'Acme books', status: 'active' };
const detail = {
  id: user,
  display_name: 'Tenant Owner',
  email: 'owner@example.com',
  status: 'active',
  updated_at: time,
  tenant: customer,
  assignment_id: assignment,
  assignment_updated_at: time,
  assignment_active: true,
  valid_from: '2026-01-01',
  valid_to: null,
  last_active_administrator: false,
};
const receipt = {
  tenant_id: tenant,
  administrator_id: user,
  assignment_id: assignment,
  status: 'active',
  assignment_active: true,
  updated_at: time,
  assignment_updated_at: time,
};
beforeEach(() => {
  call.mockReset();
  navigate.mockReset();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/platform/access/administrators');
  call.mockImplementation((path: string, method = 'GET') => {
    if (method === 'POST') return Promise.resolve(receipt);
    if (path.endsWith('/role'))
      return Promise.resolve({
        id: assignment,
        key: 'tenant_admin',
        is_system: true,
        name: 'Tenant administrator',
        description: 'Manage organisation access',
        scope_hint: 'tenant',
        permissions: ['user.read', 'user.invite', 'role.read'],
      });
    if (path.includes('/administrators?'))
      return Promise.resolve({
        items: [detail],
        page: { next_cursor: null, has_more: false },
      });
    if (path.endsWith('/administrators/' + user))
      return Promise.resolve(detail);
    if (path.startsWith('/v1/platform/access/tenants?'))
      return Promise.resolve({
        items: [customer],
        page: { next_cursor: null, has_more: false },
      });
    return Promise.resolve(customer);
  });
});
it('provides real access overview cards and role/permission navigation', () => {
  render(<PlatformAccessOverview />);
  expect(
    screen
      .getAllByRole('link', { name: 'Tenant administrators' })
      .every(
        (link) =>
          link.getAttribute('href') === '/platform/access/administrators',
      ),
  ).toBe(true);
  expect(
    screen.getByRole('link', { name: 'Back to platform administration' }),
  ).toHaveAttribute('href', '/platform');
});
it('reads the fixed role and searches its read-only permissions', async () => {
  render(<PlatformAdministratorRole />);
  expect(await screen.findByText('tenant_admin')).toBeInTheDocument();
  await userEvent.type(
    screen.getByRole('searchbox', { name: 'Search administrator permissions' }),
    'invite',
  );
  await waitFor(() =>
    expect(screen.queryByText('user.read')).not.toBeInTheDocument(),
  );
  expect(screen.getByText('user.invite')).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /save|edit|create/i }),
  ).not.toBeInTheDocument();
});
it('offers tenant selection before requesting administrator data', async () => {
  render(<PlatformAdministratorDirectory tenantId="" canManage />);
  expect(
    screen.getByText('Select a tenant to see and manage its administrators.'),
  ).toBeInTheDocument();
  expect(call).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('combobox', { name: 'Tenant' }));
  await userEvent.click(
    await screen.findByRole('option', { name: /Acme books/ }),
  );
  expect(await screen.findByText('Tenant Owner')).toBeInTheDocument();
  expect(
    screen.getByRole('link', { name: 'Invite administrator' }),
  ).toHaveAttribute('href', expect.stringContaining('tenant=' + tenant));
});
it('opens actual details through the kebab and retains filtered directory state', async () => {
  window.history.replaceState(
    null,
    '',
    '/platform/access/administrators?tenant=' + tenant + '&status=active',
  );
  render(<PlatformAdministratorDirectory tenantId={tenant} canManage />);
  expect(await screen.findByText('Tenant Owner')).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole('button', { name: 'Actions for Tenant Owner' }),
  );
  await userEvent.click(screen.getByRole('menuitem', { name: 'View details' }));
  expect(navigate).toHaveBeenCalledWith(
    expect.stringContaining('/' + user + '?tenant=' + tenant),
  );
  expect(decodeURIComponent(navigate.mock.calls[0][0])).toContain(
    'status=active',
  );
});
it('hides directory mutations for a reader', async () => {
  render(
    <PlatformAdministratorDirectory tenantId={tenant} canManage={false} />,
  );
  expect(await screen.findByText('Tenant Owner')).toBeInTheDocument();
  expect(
    screen.queryByRole('link', { name: 'Invite administrator' }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole('button', { name: 'Actions for Tenant Owner' }),
  );
  expect(
    screen.queryByRole('menuitem', { name: 'Edit administrator' }),
  ).not.toBeInTheDocument();
});
it('validates invitation fields before sending a command and then shows success', async () => {
  render(<PlatformAdministratorEditor tenantId={tenant} />);
  await screen.findByRole('button', { name: 'Send invitation' });
  await userEvent.click(
    screen.getByRole('button', { name: 'Send invitation' }),
  );
  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
  expect(call.mock.calls.filter((args) => args[1] === 'POST')).toHaveLength(0);
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Administrator name' }),
    'New Owner',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Email address' }),
    'new@example.com',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Reason' }),
    'Provide backup access',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Send invitation' }),
  );
  expect(await screen.findByText(/Administrator invited/)).toBeInTheDocument();
  const posted = call.mock.calls.find((args) => args[1] === 'POST');
  expect(posted?.[2]).toEqual({
    display_name: 'New Owner',
    email: 'new@example.com',
    reason: 'Provide backup access',
  });
  expect(posted?.[3]).toMatch(/^[\w-]+$/);
  expect(
    screen.getByRole('link', { name: 'View administrator' }),
  ).toHaveAttribute('href', expect.stringContaining('/' + user));
});
it('retains the exact body and key when an invitation outcome is uncertain', async () => {
  let attempts = 0;
  call.mockImplementation((path: string, method = 'GET') =>
    method === 'POST'
      ? ++attempts === 1
        ? Promise.reject({ status: 503, message: 'Unavailable' })
        : Promise.resolve(receipt)
      : Promise.resolve(customer),
  );
  render(<PlatformAdministratorEditor tenantId={tenant} />);
  await screen.findByRole('button', { name: 'Send invitation' });
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Administrator name' }),
    'Backup',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Email address' }),
    'backup@example.com',
  );
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Reason' }),
    'Backup administrator',
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Send invitation' }),
  );
  expect(
    await screen.findByRole('button', { name: 'Retry same request' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('textbox', { name: 'Administrator name' }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same request' }),
  );
  expect(await screen.findByText(/Administrator invited/)).toBeInTheDocument();
  const requests = call.mock.calls.filter((args) => args[1] === 'POST');
  expect(requests).toHaveLength(2);
  expect(requests[1][2]).toEqual(requests[0][2]);
  expect(requests[1][3]).toEqual(requests[0][3]);
});
it('keeps sign-in email read-only on edit and protects unsaved navigation', async () => {
  render(<PlatformAdministratorEditor tenantId={tenant} userId={user} />);
  await screen.findByDisplayValue('Tenant Owner');
  const save = screen.getByRole('button', { name: 'Save administrator' });
  expect(save.closest('form')?.closest('.janso-grid--split')).not.toBeNull();
  expect(save.closest('.janso-card__footer')?.closest('.janso-card__body')).toBeNull();
  expect(
    screen.getByRole('textbox', { name: 'Email address' }),
  ).toHaveAttribute('readonly');
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Administrator name' }),
    ' edited',
  );
  await userEvent.click(screen.getByRole('link', { name: 'Cancel' }));
  expect(
    screen.getByRole('dialog', { name: 'Discard unsaved changes?' }),
  ).toBeInTheDocument();
});
it('prevents last-administrator removal in detail and presents its role link', async () => {
  call.mockResolvedValue({ ...detail, last_active_administrator: true });
  render(
    <PlatformAdministratorDetail tenantId={tenant} userId={user} canManage />,
  );
  await screen.findByRole('heading', { name: 'Tenant Owner' });
  expect(
    screen.getByRole('button', { name: 'Deactivate administrator access' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Revoke administrator role' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('link', { name: 'Tenant administrator' }),
  ).toHaveAttribute('href', expect.stringContaining('/platform/access/role?tenant=' + tenant));
});
it('confirms suspension with a reason and native concurrency stamps', async () => {
  render(
    <PlatformAdministratorDetail tenantId={tenant} userId={user} canManage />,
  );
  await screen.findByRole('heading', { name: 'Tenant Owner' });
  await userEvent.click(
    screen.getByRole('button', { name: 'Deactivate administrator access' }),
  );
  const dialog = screen.getByRole('dialog', { name: 'Deactivate administrator access?' });
  fireEvent.submit(dialog.querySelector('form') ?? dialog);
  await userEvent.type(
    screen.getByRole('textbox', { name: 'Reason' }),
    'Access review',
  );
  const buttons = screen.getAllByRole('button', {
    name: 'Deactivate administrator access',
  });
  await userEvent.click(buttons.at(-1)!);
  expect(
    await screen.findByText('Administrator access deactivated. Existing records are retained.'),
  ).toBeInTheDocument();
  expect(call.mock.calls.find((args) => args[1] === 'POST')?.[2]).toEqual({
    action: 'suspend',
    reason: 'Access review',
    expected_updated_at: time,
    expected_assignment_updated_at: time,
  });
});
it.each([401, 403, 404, 503])(
  'does not present account actions when detail loading fails (%s)',
  async (status) => {
    call.mockRejectedValue({ status, message: 'Administrator unavailable' });
    render(
      <PlatformAdministratorDetail tenantId={tenant} userId={user} canManage />,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Administrator unavailable',
    );
    expect(
      screen.queryByRole('button', { name: 'Deactivate administrator access' }),
    ).not.toBeInTheDocument();
    if (status === 401)
      expect(
        screen.getByRole('link', { name: 'Sign in again' }),
      ).toBeInTheDocument();
  },
);
it.each([
  '/users',
  'https://evil.test/platform/access/administrators',
  '//evil.test',
  '/platform/access/administrators?tenant=' + tenant + '&role=platform_admin',
  '/platform/access/administrators?tenant=' + tenant + '&tenant=' + tenant,
])('bounds administrator return navigation (%s)', (value) => {
  expect(administratorReturn(value, tenant)).toBe(
    '/platform/access/administrators?tenant=' + tenant,
  );
});
it('allows only the implemented platform API paths and rejects duplicates and unknown fields', () => {
  const root = '/v1/platform/access/tenants/' + tenant + '/administrators';
  expect(allowedPlatformRequest('GET', root + '?q=Owner')).toBe(true);
  expect(allowedPlatformRequest('POST', root)).toBe(true);
  expect(allowedPlatformRequest('POST', root + '/' + user + '/commands')).toBe(
    true,
  );
  for (const path of [
    root + '?q=Aa&q=Bb',
    root + '?permission=user.read',
    root + '/' + user + '/permissions',
    root + '/../users',
  ])
    expect(allowedPlatformRequest('GET', path)).toBe(false);
});

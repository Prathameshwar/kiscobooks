import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccessNavigation } from '../app/components/AccessCommon';
import { AccessDirectory } from '../app/components/AccessDirectory';
import { AssignmentEditor } from '../app/components/AssignmentEditor';
import { PermissionDirectory } from '../app/components/PermissionDirectory';
import { serviceCall } from '../app/lib/service-call';
import { renderWithProviders } from './helpers';
import { access, companyId, page, roleId, roleRecord, userId, userRecord } from './access-fixtures';
import type { AccessContext } from '../app/lib/access-directory';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<object>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
const companyAccess: AccessContext = { ...access, tenantPermissions: [], permissions: ['company.read', 'user.read', 'user.invite', 'role.read', 'role.assign', 'invoice.read'], grants: [{ scope_type: 'company', scope_id: companyId, permissions: ['company.read', 'user.read', 'user.invite', 'role.read', 'role.assign', 'invoice.read'], valid_from: '2000-01-01', valid_to: null }] };
beforeEach(() => { vi.mocked(serviceCall).mockReset().mockImplementation(async (_proxy, request) => {
  if (request.path === '/v1/permissions') return { permissions: ['invoice.read', 'role.manage'] };
  if (request.path === '/v1/roles/' + roleId) return roleRecord;
  if (request.path === '/v1/role-assignments/check') return { allowed: true };
  if (request.path.startsWith('/v1/companies/' + companyId + '/users')) return page([userRecord]);
  if (request.path.startsWith('/v1/session/companies')) return page([{ id: companyId, display_name: 'Acme', code: 'ACME' }]);
  if (request.path.startsWith('/v1/roles?')) return page([roleRecord]);
  return page([]);
}); });

it('makes scoped people administration discoverable without tenant authority', async () => {
  await renderWithProviders(<AccessNavigation context={companyAccess} />);
  expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
});

it('shows held company permissions instead of calling them unheld', async () => {
  await renderWithProviders(<PermissionDirectory context={companyAccess} />);
  expect(await screen.findByText('Held in selected company')).toBeInTheDocument();
  expect(screen.getByText('Not held')).toBeInTheDocument();
});

it('uses a company projection without offering global profile mutation', async () => {
  await renderWithProviders(<AccessDirectory resource="users" context={companyAccess} companyScoped />);
  expect(await screen.findByRole('link', { name: 'Ava Singh' })).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: expect.stringContaining('/v1/companies/' + companyId + '/users?') }), 'access service');
  expect(screen.queryByRole('combobox', { name: 'User type' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Invite user' })).toBeInTheDocument();
});
it('drops unsupported account-type filters in the company directory', async () => {
  await renderWithProviders(<AccessDirectory resource="users" context={companyAccess} companyScoped initialQuery="user_type=platform_admin" />);
  await screen.findByRole('link', { name: 'Ava Singh' });
  expect(screen.queryByRole('button', { name: /Remove filter: user type/ })).not.toBeInTheDocument();
});

it('lets a company administrator select an affiliated subject and checks authority before confirmation', async () => {
  const user = userEvent.setup();
  await renderWithProviders(<AssignmentEditor context={companyAccess} />);
  await user.click(screen.getByRole('combobox', { name: 'Company' }));
  await user.click(await screen.findByRole('option', { name: /Acme/ }));
  await user.click(screen.getByRole('combobox', { name: 'Role' }));
  await user.click(await screen.findByRole('option', { name: /Viewer/ }));
  await user.type(screen.getByRole('combobox', { name: 'User' }), 'Av');
  await user.click(await screen.findByRole('option', { name: /Ava Singh/ }));
  await user.type(screen.getByLabelText('Access reason'), 'Company responsibility');
  await user.click(screen.getByRole('button', { name: 'Review assignment' }));
  expect(await screen.findByRole('dialog', { name: 'Grant role access?' })).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: '/v1/role-assignments/check', body: expect.objectContaining({ subject_id: userId, scope_id: companyId }) }), 'access service');
  expect(serviceCall).not.toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: '/v1/role-assignments', method: 'POST' }), 'access service');
});

it('shows delegation denials before a grant confirmation', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => {
    if (request.path === '/v1/role-assignments/check') throw { status: 403, message: 'You cannot delegate permissions you do not hold.' };
    if (request.path === '/v1/roles/' + roleId) return roleRecord;
    if (request.path.startsWith('/v1/session/companies')) return page([{ id: companyId, display_name: 'Acme' }]);
    if (request.path.startsWith('/v1/roles?')) return page([roleRecord]);
    return page([userRecord]);
  });
  const user = userEvent.setup();
  await renderWithProviders(<AssignmentEditor context={access} />);
  await user.click(screen.getByRole('combobox', { name: 'Role' }));
  await user.click(await screen.findByRole('option', { name: /Viewer/ }));
  await user.type(screen.getByRole('combobox', { name: 'User' }), 'Av');
  await user.click(await screen.findByRole('option', { name: /Ava Singh/ }));
  await user.type(screen.getByLabelText('Access reason'), 'Review authority');
  await user.click(screen.getByRole('button', { name: 'Review assignment' }));
  await waitFor(() => expect(screen.getByText(/cannot delegate/)).toBeInTheDocument());
  expect(screen.queryByRole('dialog', { name: 'Grant role access?' })).not.toBeInTheDocument();
});

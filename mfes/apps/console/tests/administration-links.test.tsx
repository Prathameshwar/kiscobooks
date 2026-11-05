import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { RoleDetail } from '../app/components/RoleDetail';
import { RoleEditor } from '../app/components/RoleEditor';
import { OrganisationDetail } from '../app/components/OrganisationDetail';
import { AssignmentDirectory } from '../app/components/AssignmentDirectory';
import { UserEditor } from '../app/components/UserEditor';
import { serviceCall } from '../app/lib/service-call';
import { renderWithProviders } from './helpers';
import { access, assignment, companyId, page, permissions, roleId, roleRecord, userRecord } from './access-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
const context = { ...access, permissions: [...permissions, 'department.manage'], tenantPermissions: [...permissions, 'department.manage'], grants: [{ ...access.grants![0]!, permissions: [...permissions, 'department.manage'] }] };
const department = { id: roleId, company_id: companyId, parent_id: null, code: 'OPS', name: 'Operations', path: '/' + roleId.replaceAll('-', '') + '/', is_active: true, head_user_id: null, cost_centre_code: null };
beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path === '/v1/permissions') return { permissions };
    if (request.path === '/v1/roles/' + roleId) return roleRecord;
    if (request.path.includes('/role-assignments?')) return page([{ ...assignment, subject_type: 'user_group', subject_id: roleId, subject_label: 'Finance' }]);
    if (request.path === '/v1/companies/' + companyId + '/departments/' + roleId) return department;
    if (request.path === '/v1/users' && request.method === 'POST') return userRecord;
    return page([]);
  });
});
it('returns from role editing to the detail while retaining the filtered directory', async () => {
  const directory = '/roles?q=View&limit=25', detail = '/roles/' + roleId + '?returnTo=' + encodeURIComponent(directory);
  await renderWithProviders(<RoleDetail context={context} id={roleId} returnTo={directory} />);
  const edit = await screen.findByRole('link', { name: 'Edit role' });
  expect(new URL(edit.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe(detail);
});
it('honours the explicit detail destination on an editor direct visit', async () => {
  const detail = '/roles/' + roleId + '?returnTo=' + encodeURIComponent('/roles?q=View');
  await renderWithProviders(<RoleEditor context={context} id={roleId} returnTo={detail} />);
  expect(screen.getByRole('link', { name: 'Back to role details' })).toHaveAttribute('href', detail);
});
it('links assignment roles and permitted group subjects with the assignment filters retained', async () => {
  await renderWithProviders(<AssignmentDirectory context={context} initialQuery={'role_id=' + roleId} />);
  const link = await screen.findByRole('link', { name: 'Finance' });
  expect(new URL(link.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toContain('/assignments?');
  expect(link.getAttribute('href')).toContain('/user-groups/' + roleId);
});
it('returns a child department creation to the originating department detail', async () => {
  const directory = '/departments?q=OP', detail = '/departments/' + roleId + '?returnTo=' + encodeURIComponent(directory);
  await renderWithProviders(<OrganisationDetail resource="departments" context={context} id={roleId} returnTo={directory} />);
  const child = await screen.findByRole('link', { name: 'Add child department' });
  expect(new URL(child.getAttribute('href')!, 'https://console.invalid').searchParams.get('returnTo')).toBe(detail);
});
it('does not offer an unreadable user detail after a creation-only invitation', async () => {
  const keys = ['user.invite'], inviteOnly = { ...access, permissions: keys, tenantPermissions: keys, grants: [{ ...access.grants![0]!, permissions: keys }] };
  const user = userEvent.setup(); await renderWithProviders(<UserEditor context={inviteOnly} />);
  await user.type(screen.getByRole('textbox', { name: 'Email' }), 'ava@example.com');
  await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Ava');
  await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Singh');
  await user.click(screen.getByRole('button', { name: 'Invite user' }));
  expect(await screen.findByText(/User invited/)).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'View user' })).not.toBeInTheDocument();
});

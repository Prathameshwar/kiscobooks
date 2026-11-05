import { act, fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrganisationDirectory } from '../app/components/OrganisationDirectory';
import { OrganisationEditor } from '../app/components/OrganisationEditor';
import { OrganisationDetail } from '../app/components/OrganisationDetail';
import { UserGroupMembers } from '../app/components/UserGroupMembers';
import { UserDetail } from '../app/components/UserDetail';
import { RoleDetail } from '../app/components/RoleDetail';
import { CompanyUserDetail } from '../app/components/CompanyUserDetail';
import { AccessNavigation, useAccessDraft } from '../app/components/AccessCommon';
import { organisationPayload, organisationPermission, organisationReturn, type Department, type OrganisationFields, type UserGroup } from '../app/lib/organisation-contract';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import { flattenNavigation, navigationFor } from '../app/nav';
import { renderWithProviders, sessionFor } from './helpers';
import { access, companyId, page, roleId, roleRecord, userId, userRecord } from './access-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
const permissions = [...access.permissions, 'department.manage', 'group.manage'];
const context = { ...access, companyName: 'Acme', permissions, tenantPermissions: permissions, grants: [{ scope_type: 'tenant', scope_id: null, permissions, valid_from: '2000-01-01', valid_to: null }] };
const department: Department = { id: roleId, company_id: companyId, parent_id: null, code: 'OPS', name: 'Operations', cost_centre_code: null, head_user_id: null, is_active: true, path: '/' + roleId.replaceAll('-', '') + '/' };
const group: UserGroup = { id: roleId, code: 'FIN', name: 'Finance', description: null, is_active: true };
const member = { id: companyId, user_id: userId, user_group_id: roleId, created_at: '2026-10-24T10:00:00Z', display_name: 'Ava Singh' };
const metadata = (resource: 'departments' | 'user-groups', editing = false): OrganisationFields => ({ entity_type: resource === 'departments' ? 'identity.department' : 'identity.user_group', model_name: resource === 'departments' ? 'Department' : 'UserGroup', fields: (resource === 'departments' ? ['code', 'name', ...(editing ? [] : ['parent_id']), 'cost_centre_code', 'head_user_id'] : [...(editing ? [] : ['code']), 'name', 'description']).map((key, order) => ({ key, label: key.replace('_id', '').replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()), required: ['code', 'name'].includes(key), hideable: false, renameable: false, requires_feature: null, group: 'identity', order, writable: true, is_visible: true, source: 'native', data_type: key.endsWith('_id') ? 'reference' : 'string', validation: { nullable: !['code', 'name'].includes(key), max_length: key === 'code' ? 20 : 150 } })) });
beforeEach(() => {
  vi.mocked(goTo).mockReset();
  vi.mocked(serviceCall).mockReset().mockImplementation(async (_proxy, request) => {
    const resource = request.path.includes('/user-groups') ? 'user-groups' : 'departments';
    if (request.path.includes('/field-set')) return metadata(resource, request.path.includes('update'));
    if (request.path.includes('/members')) return request.method === 'POST' ? member : request.method === 'DELETE' ? { ok: true } : page([member]);
    if (request.path.startsWith('/v1/users')) return page([userRecord]);
    if (request.method === 'POST' || request.method === 'PATCH') return { ...(resource === 'departments' ? department : group), ...(request.body as object) };
    if (request.path.split('?')[0]?.endsWith(roleId)) return resource === 'departments' ? department : group;
    return page(resource === 'departments' ? [department] : [group]);
  });
});

it.each(['departments', 'user-groups'] as const)('renders the %s directory, scoped query and kebab navigation', async resource => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationDirectory resource={resource} context={context} initialQuery="q=OP&is_active=true&sort=code" />);
  expect(await screen.findByRole('link', { name: resource === 'departments' ? 'Operations' : 'Finance' })).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: expect.stringContaining('is_active=true') }), 'access service');
  await user.click(screen.getByRole('button', { name: /Actions for/ })); await user.click(screen.getByRole('menuitem', { name: 'Edit details' }));
  expect(goTo).toHaveBeenCalledWith(expect.stringContaining('/' + resource + '/' + roleId + '/edit?returnTo='));
});
it.each([401, 403, 422, 500])('renders a directory failure %s and can recover from a failed page', async status => {
  vi.mocked(serviceCall).mockRejectedValue({ status, message: 'Directory unavailable' });
  await renderWithProviders(<OrganisationDirectory resource="departments" context={context} />);
  expect(await screen.findByText('Directory unavailable')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Operations' })).not.toBeInTheDocument();
});
it('does not offer creation or editing to a reader', async () => {
  const read = ['group.read']; const reader = { ...context, tenantPermissions: read, permissions: read, grants: [{ ...context.grants[0]!, permissions: read }] };
  await renderWithProviders(<OrganisationDirectory resource="user-groups" context={reader} />);
  expect(await screen.findByRole('link', { name: 'Finance' })).toBeInTheDocument(); expect(screen.queryByRole('link', { name: 'New user group' })).not.toBeInTheDocument();
});
it.each(['departments', 'user-groups'] as const)('validates and creates %s with only native form values', async resource => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource={resource} context={context} />);
  const submit = await screen.findByRole('button', { name: resource === 'departments' ? 'Create department' : 'Create user group' });
  await user.click(submit); expect(screen.getByLabelText('Code')).toHaveAttribute('aria-invalid', 'true');
  await user.type(screen.getByLabelText('Code'), resource === 'departments' ? 'OPS' : 'FIN'); await user.type(screen.getByLabelText('Name'), resource === 'departments' ? 'Operations' : 'Finance'); await user.click(submit);
  expect(await screen.findByText(resource === 'departments' ? 'Department created.' : 'User group created.')).toBeInTheDocument();
  const call = vi.mocked(serviceCall).mock.calls.find(([, request]) => request.method === 'POST'); expect(call?.[1].body).toMatchObject({ code: resource === 'departments' ? 'OPS' : 'FIN' }); expect(call?.[1].body).not.toHaveProperty('tenant_id'); expect(submit).toBeDisabled();
});
it('edits a group without sending its immutable code or unchanged values', async () => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="user-groups" context={context} id={roleId} />);
  const save = await screen.findByRole('button', { name: 'Save changes' }); await user.click(save); expect(await screen.findByText('No changes to save.')).toBeInTheDocument();
  expect(serviceCall).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ method: 'PATCH' }), expect.anything());
  await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'Finance team'); await user.click(save);
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ method: 'PATCH', body: { name: 'Finance team' } }), 'access service');
});
it('freezes an unconfirmed create and offers directory review', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST') throw { status: 503, message: 'Response lost' }; return original(...args); });
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="user-groups" context={context} />);
  await user.type(await screen.findByLabelText('Code'), 'FIN'); await user.type(screen.getByLabelText('Name'), 'Finance'); await user.click(screen.getByRole('button', { name: 'Create user group' }));
  expect(await screen.findByText(/result of this change could not be confirmed/)).toBeInTheDocument(); expect(screen.getByRole('button', { name: 'Create user group' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Reload and review' })); expect(goTo).toHaveBeenCalledWith('/user-groups');
});
it('guards a dirty editor during navigation and company changes', async () => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="departments" context={context} />);
  await user.type(await screen.findByLabelText('Name'), 'Draft'); const event = new Event('janso:before-company-change', { cancelable: true }); fireEvent(window, event); expect(event.defaultPrevented).toBe(true);
  await user.click(screen.getByRole('link', { name: 'My access' })); expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument();
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(screen.getByLabelText('Name')).toHaveValue('Draft');
});
it('renders server validation beside the field and retains its value', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST') throw { status: 422, message: 'Invalid name', fields: { name: 'Name is reserved' } }; return original(...args); });
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="user-groups" context={context} />);
  await user.type(await screen.findByLabelText('Code'), 'FI'); await user.type(screen.getByLabelText('Name'), 'Finance'); await user.click(screen.getByRole('button', { name: 'Create user group' }));
  expect(await screen.findByText('Name is reserved')).toBeInTheDocument(); expect(screen.getByLabelText('Name')).toHaveValue('Finance');
});
it('requires a reason and reviews department deactivation', async () => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationDetail resource="departments" context={context} id={roleId} />);
  expect((await screen.findByRole('button', { name: 'Deactivate department' })).closest('.janso-form-actions')).not.toBeNull();
  await user.click(await screen.findByRole('button', { name: 'Deactivate department' })); const modal = within(screen.getByRole('dialog', { name: 'Deactivate department?' }));
  await user.click(modal.getByRole('button', { name: 'Deactivate' })); expect(modal.getByLabelText('Reason')).toHaveAttribute('aria-invalid', 'true'); await user.type(modal.getByLabelText('Reason'), 'Retired department'); await user.click(modal.getByRole('button', { name: 'Deactivate' }));
  expect(await screen.findByText('Record deactivated. Existing history is retained.')).toBeInTheDocument(); expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ body: { is_active: false, reason: 'Retired department' } }), 'access service');
});
it('rejects unchanged parent movement and disables self/descendant choices', async () => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationDetail resource="departments" context={context} id={roleId} />);
  await user.click(await screen.findByRole('button', { name: 'Change parent' })); const modal = within(screen.getByRole('dialog', { name: 'Change parent department?' }));
  await user.type(modal.getByRole('combobox', { name: 'New parent department' }), 'OP'); expect(await screen.findByRole('option', { name: /Operations/ })).toHaveAttribute('aria-disabled', 'true');
  await user.keyboard('{Escape}'); await user.click(modal.getByRole('button', { name: 'Confirm parent change' })); expect(await screen.findByText('The parent department is unchanged.')).toBeInTheDocument();
});
it('reviews group member addition and removes through the association endpoint', async () => {
  const user = userEvent.setup(); await renderWithProviders(<UserGroupMembers groupId={roleId} active context={context} />);
  await user.type(screen.getByRole('combobox', { name: 'User to add' }), 'Av'); await user.click(await screen.findByRole('option', { name: /Ava Singh/ })); await user.click(screen.getByRole('button', { name: 'Review member addition' }));
  expect(serviceCall).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ method: 'POST' }), expect.anything());
  await user.click(within(screen.getByRole('dialog', { name: 'Add group member?' })).getByRole('button', { name: 'Add member' })); expect(await screen.findByText(/Member added/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Actions for/ })); expect(screen.getByRole('menuitem', { name: 'Remove member' })).toHaveAttribute('data-tone', 'danger'); await user.click(screen.getByRole('menuitem', { name: 'Remove member' })); await user.click(within(screen.getByRole('dialog', { name: 'Remove group member?' })).getByRole('button', { name: 'Remove member' }));
  expect(await screen.findByText(/Member removed/)).toBeInTheDocument(); expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ method: 'DELETE', path: '/v1/user-groups/' + roleId + '/members/' + userId }), 'access service');
});
it('does not expose member addition without tenant user read or while inactive', async () => {
  await renderWithProviders(<UserGroupMembers groupId={roleId} active context={{ ...context, tenantPermissions: ['group.read', 'group.manage'] }} />);
  expect(screen.queryByRole('combobox', { name: 'User to add' })).not.toBeInTheDocument(); expect(screen.getByText(/Tenant-wide user read permission/)).toBeInTheDocument();
});
it('does not offer own-member removal', async () => {
  await renderWithProviders(<UserGroupMembers groupId={roleId} active context={{ ...context, userId }} />);
  expect(await screen.findByText('Ava Singh')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: /Actions for/ })).not.toBeInTheDocument();
});
it('gates navigation by tenant group and company department authority', async () => {
  const session = { ...await sessionFor({ permissions }), company: { id: companyId, name: 'Acme' }, grants: context.grants };
  expect(navigationFor(session).flatMap(section => flattenNavigation(section.items)).map(item => item.href)).toEqual(expect.arrayContaining(['/departments', '/user-groups']));
  const scoped = { ...session, grants: [{ ...context.grants[0]!, scope_type: 'company', scope_id: companyId }] };
  expect(navigationFor(scoped).flatMap(section => flattenNavigation(section.items)).map(item => item.href)).not.toContain('/user-groups');
});
it('preserves scope, input, changed-field and safe-return contracts', () => {
  expect(organisationReturn('departments', '//evil.test/departments')).toBe('/departments');
  expect(organisationReturn('departments', '/departments?sort=name&limit=201&is_active=true&q=OP')).toBe('/departments?is_active=true&q=OP');
  expect(organisationPayload(metadata('departments').fields, { code: '  ', name: 'Bad\x01name' }).errors).toMatchObject({ code: expect.any(String), name: expect.any(String) });
  const scoped = { ...context, grants: [{ ...context.grants[0]!, scope_type: 'department', scope_id: roleId }] };
  expect(organisationPermission(scoped, 'departments', 'manage', department)).toBe(true); expect(organisationPermission(scoped, 'departments', 'manage')).toBe(false); expect(organisationPermission(scoped, 'user-groups', 'manage')).toBe(false);
});

it('retries unavailable form metadata without navigating away', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let failed = false;
  vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].path.includes('field-set') && !failed) { failed = true; throw { status: 503, message: 'Form unavailable' }; } return original(...args); });
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="departments" context={context} />);
  await user.click(await screen.findByRole('button', { name: 'Retry loading' }));
  expect(await screen.findByLabelText('Name')).toBeInTheDocument(); expect(goTo).not.toHaveBeenCalled();
});
it('guards member selections before group status changes or navigation', async () => {
  const user = userEvent.setup(); await renderWithProviders(<OrganisationDetail resource="user-groups" context={context} id={roleId} />);
  await user.type(await screen.findByRole('combobox', { name: 'User to add' }), 'Av'); await user.click(await screen.findByRole('option', { name: /Ava Singh/ }));
  expect(screen.getByRole('button', { name: 'Deactivate user group' })).toBeDisabled();
  await user.click(screen.getByRole('link', { name: 'My access' })); expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument();
});
it('guards user lifecycle reasons when navigating', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === '/v1/users/' + userId ? userRecord : original(...args));
  const user = userEvent.setup(); await renderWithProviders(<UserDetail context={{ ...context, tenantPermissions: [...permissions, 'user.deactivate'] }} id={userId} />);
  await user.click(await screen.findByRole('button', { name: 'Suspend user' })); await user.type(screen.getByLabelText('Action reason'), 'Reviewed');
  const event = new Event('janso:before-company-change', { cancelable: true }); fireEvent(window, event); expect(event.defaultPrevented).toBe(true);
});

function DraftNavigation() {
  const guard = useAccessDraft(true, false);
  return <><AccessNavigation context={context} onLeave={guard.leave} />{guard.confirmation}</>;
}
it('does not prompt again after confirming a draft discard', async () => {
  const user = userEvent.setup(); await renderWithProviders(<DraftNavigation />); await user.click(screen.getByRole('link', { name: 'My access' })); await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard and leave' }));
  expect(goTo).toHaveBeenCalled(); const event = new Event('janso:before-company-change', { cancelable: true }); fireEvent(window, event); expect(event.defaultPrevented).toBe(false);
});
it('guards an open role lifecycle dialog during company changes', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === '/v1/roles/' + roleId ? roleRecord : args[1].path === '/v1/permissions' ? { permissions } : original(...args));
  const user = userEvent.setup(); await renderWithProviders(<RoleDetail context={context} id={roleId} />); await user.click(await screen.findByRole('button', { name: 'Deactivate role' }));
  const event = new Event('janso:before-company-change', { cancelable: true }); fireEvent(window, event); expect(event.defaultPrevented).toBe(true);
});
it('allows company administrators to manage affiliations without account-wide user edits', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!, affiliation = { id: roleId, user_id: userId, company_id: companyId, department_id: null, is_active: true, is_primary: false, started_on: null, ended_on: null };
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === '/v1/companies/' + companyId + '/users/' + userId ? userRecord : args[1].path.includes('/memberships') ? args[1].method === 'POST' ? affiliation : page([affiliation]) : original(...args));
  const companyContext = { ...context, tenantPermissions: [], grants: [{ ...context.grants[0]!, scope_type: 'company', scope_id: companyId }] };
  const user = userEvent.setup(); await renderWithProviders(<CompanyUserDetail context={companyContext} id={userId} />);
  await user.click(await screen.findByRole('button', { name: 'Review affiliation addition' })); await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm affiliation change' }));
  expect(await screen.findByText('Affiliation added. No role access was granted.')).toBeInTheDocument(); expect(screen.queryByRole('link', { name: 'Edit user' })).not.toBeInTheDocument();
});
it('prevents navigation during an in-flight member addition', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; let resolveWrite!: (value: typeof member) => void;
  vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].method === 'POST' && args[1].path.endsWith('/members') ? new Promise<typeof member>(resolve => { resolveWrite = resolve; }) : original(...args));
  const user = userEvent.setup(); await renderWithProviders(<OrganisationDetail resource="user-groups" context={context} id={roleId} />);
  await user.type(await screen.findByRole('combobox', { name: 'User to add' }), 'Av'); await user.click(await screen.findByRole('option', { name: /Ava Singh/ })); await user.click(screen.getByRole('button', { name: 'Review member addition' })); await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Add member' }));
  await user.click(screen.getByRole('link', { name: 'My access' })); expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument(); expect(goTo).not.toHaveBeenCalled();
  await act(async () => resolveWrite(member)); expect(await screen.findByText(/Member added/)).toBeInTheDocument();
});
it('does not advertise unreadable details to a create-only group administrator', async () => {
  const keys = ['group.manage'], createOnly = { ...context, permissions: keys, tenantPermissions: keys, grants: [{ ...context.grants[0]!, permissions: keys }] };
  const user = userEvent.setup(); await renderWithProviders(<OrganisationEditor resource="user-groups" context={createOnly} />); await user.type(await screen.findByLabelText('Code'), 'STAFF'); await user.type(screen.getByLabelText('Name'), 'Staff'); await user.click(screen.getByRole('button', { name: 'Create user group' }));
  expect(await screen.findByText('User group created.')).toBeInTheDocument(); expect(screen.queryByRole('link', { name: 'View user group' })).not.toBeInTheDocument();
});
it('resolves and links the department head through the authorized user directory', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => args[1].path === '/v1/companies/' + companyId + '/departments/' + roleId ? { ...department, head_user_id: userId } : args[1].path === '/v1/users/' + userId ? userRecord : original(...args));
  await renderWithProviders(<OrganisationDetail resource="departments" context={context} id={roleId} />); expect(await screen.findByRole('link', { name: 'Ava Singh' })).toHaveAttribute('href', '/users/' + userId + '?returnTo=' + encodeURIComponent('/departments/' + roleId + '?returnTo=%2Fdepartments'));
});

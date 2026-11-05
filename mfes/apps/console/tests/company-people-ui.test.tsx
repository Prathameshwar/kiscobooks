import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyUserInvite } from '../app/components/CompanyUserInvite';
import { CompanyUserDetail } from '../app/components/CompanyUserDetail';
import { MyAccess } from '../app/components/MyAccess';
import { AssignmentEditor } from '../app/components/AssignmentEditor';
import { serviceCall } from '../app/lib/service-call';
import { navigationFor } from '../app/nav';
import { companyAccess } from '../app/lib/access-permissions';
import { goTo } from '../app/lib/navigate';
import { renderWithProviders, sessionFor } from './helpers';
import { access, companyId, page, roleId, roleRecord, userId, userRecord } from './access-fixtures';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<object>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
const context = { ...access, companyName: 'Acme', tenantPermissions: [], grants: [{ scope_type: 'company', scope_id: companyId, permissions: ['user.read', 'user.invite', 'role.read', 'role.assign'], valid_from: '2000-01-01', valid_to: null }] };
beforeEach(() => { vi.mocked(goTo).mockReset(); vi.mocked(serviceCall).mockReset().mockImplementation(async (_proxy, request) => request.method === 'POST' ? { ...userRecord, status: 'invited' } : userRecord); });

it('validates an invitation and submits only the company-specific contract', async () => {
  const user = userEvent.setup(); await renderWithProviders(<CompanyUserInvite context={context} />);
  await user.click(screen.getByRole('button', { name: 'Invite user' }));
  expect(serviceCall).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
  await user.type(screen.getByLabelText('Email'), 'ava@example.com');
  await user.type(screen.getByLabelText('First name'), 'Ava');
  await user.click(screen.getByRole('button', { name: 'Invite user' }));
  expect(await screen.findByText(/No role access was granted/)).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: '/v1/companies/' + companyId + '/users', body: { email: 'ava@example.com', first_name: 'Ava', last_name: null, display_name: null } }), 'access service');
  expect(screen.getByRole('button', { name: 'Invite user' })).toBeDisabled();
  expect(screen.getByRole('link', { name: 'View company user' })).toHaveAttribute('href', '/users/' + userId + '?returnTo=%2Fusers');
});

it('freezes an uncertain invitation and offers directory review', async () => {
  vi.mocked(serviceCall).mockRejectedValue({ status: 503, message: 'Response lost' });
  const user = userEvent.setup(); await renderWithProviders(<CompanyUserInvite context={context} />);
  await user.type(screen.getByLabelText('Email'), 'ava@example.com'); await user.type(screen.getByLabelText('First name'), 'Ava');
  await user.click(screen.getByRole('button', { name: 'Invite user' }));
  await user.click(await screen.findByRole('button', { name: 'Reload and review' }));
  expect(goTo).toHaveBeenCalledWith('/users'); expect(serviceCall).toHaveBeenCalledTimes(1);
});

it('keeps a duplicate-account draft editable and explains recovery', async () => {
  vi.mocked(serviceCall).mockRejectedValue({ status: 409, message: 'This account already exists; ask tenant administration to manage affiliation.' });
  const user = userEvent.setup(); await renderWithProviders(<CompanyUserInvite context={context} />);
  await user.type(screen.getByLabelText('Email'), 'ava@example.com'); await user.type(screen.getByLabelText('First name'), 'Ava');
  await user.click(screen.getByRole('button', { name: 'Invite user' }));
  expect(await screen.findByText(/This account already exists/)).toBeInTheDocument();
  expect(screen.getByLabelText('Email')).toHaveValue('ava@example.com'); expect(screen.getByRole('button', { name: 'Invite user' })).toBeEnabled();
});

it('guards unsaved company invitations when navigating', async () => {
  const user = userEvent.setup(); await renderWithProviders(<CompanyUserInvite context={context} />);
  await user.type(screen.getByLabelText('First name'), 'Draft'); await user.click(screen.getByRole('link', { name: 'My access' }));
  const dialog = within(screen.getByRole('dialog', { name: 'Discard unsaved changes?' }));
  await user.click(dialog.getByRole('button', { name: 'Cancel' })); expect(screen.getByLabelText('First name')).toHaveValue('Draft');
});

it('does not render a form without invite authority at this company', async () => {
  await renderWithProviders(<CompanyUserInvite context={{ ...context, companyId: userId }} />);
  expect(screen.queryByRole('button', { name: 'Invite user' })).not.toBeInTheDocument();
  expect(screen.getByText(/Select a company where/)).toBeInTheDocument();
});

it('shows limited details and authorized assignment links without profile or lifecycle actions', async () => {
  await renderWithProviders(<CompanyUserDetail context={context} id={userId} />);
  expect(await screen.findByRole('heading', { name: 'Ava Singh' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Assign role' })).toHaveAttribute('href', '/assignments/new?subject_id=' + userId + '&returnTo=' + encodeURIComponent('/users/' + userId + '?returnTo=%2Fusers'));
  expect(screen.queryByRole('link', { name: /Edit/ })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: /Suspend|Deactivate/ })).not.toBeInTheDocument();
});

it.each(['self', 'suspended', 'read-only'])('hides company grant creation for %s', async variant => {
  if (variant === 'suspended') vi.mocked(serviceCall).mockResolvedValue({ ...userRecord, status: 'suspended' });
  await renderWithProviders(<CompanyUserDetail context={{ ...context, ...(variant === 'self' ? { userId } : variant === 'read-only' ? { grants: [] } : {}) }} id={userId} />);
  await screen.findByRole('heading', { name: 'Ava Singh' }); expect(screen.queryByRole('link', { name: 'Assign role' })).not.toBeInTheDocument();
});

it('offers self access without administrative permissions or API directory calls', async () => {
  const session = await sessionFor({ permissions: [] }); session.grants = []; session.role = 'tenant user';
  await renderWithProviders(<MyAccess session={session} />);
  expect(screen.getByRole('heading', { name: 'My access' })).toBeInTheDocument(); expect(screen.getByText('No grants available')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Roles' })).not.toBeInTheDocument(); expect(serviceCall).not.toHaveBeenCalled();
  expect(navigationFor(session).flatMap(section => section.items).map(item => item.href)).toContain('/my-access');
});

it('keeps operator authority separate from tenant and company administration', async () => {
  const session = await sessionFor({ permissions: ['platform.tenant.read'] }); session.role = 'platform admin';
  session.grants = [{ scope_type: 'tenant', scope_id: null, permissions: session.permissions, valid_from: '2000-01-01', valid_to: null }];
  await renderWithProviders(<MyAccess session={session} />);
  expect(screen.getByText(/time-bound, audited support/)).toBeInTheDocument();
  const links = navigationFor(session).flatMap(section => section.items).map(item => item.href);
  expect(links).toContain('/platform'); expect(links).not.toContain('/users'); expect(links).not.toContain('/roles');
});

it('shows grant validity and scope without treating a scheduled or expired grant as active', async () => {
  const session = await sessionFor({ permissions: ['invoice.read'] }); session.company = { id: companyId, name: 'Acme' };
  session.grants = [{ scope_type: 'company', scope_id: companyId, permissions: ['invoice.read'], valid_from: '2000-01-01', valid_to: null }, { scope_type: 'department', scope_id: userId, permissions: ['report.read'], valid_from: '2099-01-01', valid_to: null }, { scope_type: 'tenant', scope_id: null, permissions: ['user.read'], valid_from: '2000-01-01', valid_to: '2001-01-01' }];
  await renderWithProviders(<MyAccess session={session} />);
  expect(screen.getByText('Active')).toBeInTheDocument(); expect(screen.getByText('Scheduled')).toBeInTheDocument(); expect(screen.getByText('Expired')).toBeInTheDocument();
  expect(companyAccess({ ...context, grants: session.grants }, 'user.read')).toBe(false);
});

it('preserves a company user deep link and hides unsupported group subjects', async () => {
  await renderWithProviders(<AssignmentEditor context={context} initialSubject={userId} />);
  expect(await screen.findByDisplayValue('Ava Singh')).toBeInTheDocument(); expect(screen.getByRole('combobox', { name: 'Company' })).toHaveValue('Acme');
  expect(screen.queryByRole('option', { name: 'User group' })).not.toBeInTheDocument();
});
it('names the preselected company in the grant confirmation', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_proxy, request) => request.path === '/v1/role-assignments/check' ? { allowed: true } : request.path === '/v1/roles/' + roleId ? roleRecord : request.path.startsWith('/v1/roles?') ? page([roleRecord]) : userRecord);
  const user = userEvent.setup(); await renderWithProviders(<AssignmentEditor context={context} initialSubject={userId} />);
  await screen.findByDisplayValue('Ava Singh'); await user.click(screen.getByRole('combobox', { name: 'Role' }));
  await user.click(await screen.findByRole('option', { name: /Viewer/ })); await user.type(screen.getByLabelText('Access reason'), 'Company responsibility');
  await user.click(screen.getByRole('button', { name: 'Review assignment' }));
  const dialog = within(await screen.findByRole('dialog', { name: 'Grant role access?' }));
  expect(dialog.getByText('Acme')).toBeInTheDocument();
});

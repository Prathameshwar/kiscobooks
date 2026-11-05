import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { UserAffiliations } from '../app/components/UserAffiliations';
import { serviceCall } from '../app/lib/service-call';
import { renderWithProviders } from './helpers';
import { access, companyId, page, roleId, userId } from './access-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
const permissions = [...access.permissions, 'department.manage'];
const context = { ...access, companyName: 'Acme', permissions, tenantPermissions: permissions, grants: [{ scope_type: 'tenant', scope_id: null, permissions, valid_from: '2000-01-01', valid_to: null }] };
const affiliation = { id: roleId, user_id: userId, company_id: companyId, department_id: null, started_on: null, ended_on: null, is_active: true, is_primary: false };
beforeEach(() => {
  vi.mocked(serviceCall).mockReset().mockImplementation(async (_proxy, request) => request.method === 'POST' ? { ...affiliation, ...(request.body as object) } : page([affiliation]));
});
it('lists only the selected company user affiliations', async () => {
  await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="active" />);
  expect(await screen.findByText('Company affiliation')).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: expect.stringContaining('&user_id=' + userId) }), 'access service');
});
it('reviews an affiliation addition and sends no roles or primary flag', async () => {
  const user = userEvent.setup(); await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="invited" />);
  await user.click(screen.getByRole('button', { name: 'Review affiliation addition' })); expect(serviceCall).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ method: 'POST' }), expect.anything());
  await user.click(within(screen.getByRole('dialog', { name: 'Add affiliation?' })).getByRole('button', { name: 'Confirm affiliation change' }));
  expect(await screen.findByText('Affiliation added. No role access was granted.')).toBeInTheDocument();
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ method: 'POST', body: { user_id: userId, department_id: null, started_on: null, is_primary: false } }), 'access service');
});
it.each(['End affiliation', 'Make primary'])('requires a reason for %s', async action => {
  const user = userEvent.setup(); await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="active" />);
  await screen.findByText('Company affiliation'); await user.click(screen.getByRole('button', { name: /Actions for/ })); if (action === 'End affiliation') expect(screen.getByRole('menuitem', { name: action })).toHaveAttribute('data-tone', 'danger'); await user.click(screen.getByRole('menuitem', { name: action }));
  const modal = within(screen.getByRole('dialog')); await user.click(modal.getByRole('button', { name: 'Confirm affiliation change' })); expect(modal.getByLabelText('Affiliation reason')).toHaveAttribute('aria-invalid', 'true');
  await user.type(modal.getByLabelText('Affiliation reason'), 'Reviewed'); await user.click(modal.getByRole('button', { name: 'Confirm affiliation change' }));
  expect(serviceCall).toHaveBeenCalledWith('/api/access', expect.objectContaining({ path: '/v1/memberships/' + roleId + (action === 'End affiliation' ? '/end' : '/make-primary'), body: { reason: 'Reviewed' } }), 'access service');
});
it('does not offer primary activation for an invited user', async () => {
  const user = userEvent.setup(); await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="invited" />); await screen.findByText('Company affiliation'); await user.click(screen.getByRole('button', { name: /Actions for/ })); expect(screen.queryByRole('menuitem', { name: 'Make primary' })).not.toBeInTheDocument();
});
it('freezes an uncertain affiliation write until review', async () => {
  const original = vi.mocked(serviceCall).getMockImplementation()!; vi.mocked(serviceCall).mockImplementation(async (...args) => { if (args[1].method === 'POST') throw { status: 503, message: 'Lost response' }; return original(...args); });
  const user = userEvent.setup(); await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="active" />); await user.click(screen.getByRole('button', { name: 'Review affiliation addition' })); await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm affiliation change' }));
  expect(await screen.findByText(/result is unconfirmed/)).toBeInTheDocument(); await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' })); expect(screen.getByRole('button', { name: 'Review affiliation addition' })).toBeDisabled();
});
it('rejects mismatched company affiliation responses', async () => {
  vi.mocked(serviceCall).mockResolvedValue(page([{ ...affiliation, company_id: roleId }])); await renderWithProviders(<UserAffiliations context={context} userId={userId} userStatus="active" />); expect(await screen.findByText('Unexpected affiliation response.')).toBeInTheDocument();
});
it('makes no request without company read authority', async () => {
  await renderWithProviders(<UserAffiliations context={{ ...context, companyId: undefined }} userId={userId} userStatus="active" />); expect(screen.getByText(/Select a company with department read access/)).toBeInTheDocument(); expect(serviceCall).not.toHaveBeenCalled();
});

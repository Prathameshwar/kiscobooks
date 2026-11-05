import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { fillAdministrator, fillTenant, reachTenantReview, renderTenant, tenantChoices as choices, tenantCreated as created, tenantDetail as detail, tenantId as id } from './tenant-wizard-fixtures';
const { fetcher, navigate } = vi.hoisted(() => ({ fetcher: vi.fn(), navigate: vi.fn() }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
vi.mock('../app/lib/navigate', async original => ({ ...await original<typeof import('../app/lib/navigate')>(), goTo: navigate }));
const writes = () => fetcher.mock.calls.map(call => JSON.parse(call[1].body)).filter(input => input.method === 'POST');
beforeEach(() => {
  sessionStorage.clear(); fetcher.mockReset(); navigate.mockReset();
  fetcher.mockImplementation(async (_url, init) => {
    const input = JSON.parse(init.body);
    return Response.json(input.path.endsWith('tenant-options') ? choices : input.path.includes('/pending-registration') ? { match: null } : input.path.includes('/available') ? { available: null } : input.method === 'POST' ? created : detail);
  });
});

it('uses the shared three-step wizard with only tenant fields on its first step', async () => {
  const { container } = renderTenant({ returnTo: '/platform/tenants?status=active' });
  await screen.findByRole('textbox', { name: 'Tenant name' });
  expect(container.querySelector('.janso-setup')).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Tenant details' })).toBeInTheDocument();
  expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  const progress = within(screen.getByRole('navigation', { name: 'Setup progress' }));
  expect(progress.getByRole('button', { name: /Administrator/ })).toBeDisabled();
  expect(progress.getByRole('button', { name: /Review & create/ })).toBeDisabled();
  expect(screen.queryByRole('textbox', { name: 'Administrator email' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Create tenant' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/platform/tenants?status=active');
  expect(screen.getAllByRole('combobox')).toHaveLength(2);
});
it('validates each tenant field before allowing the administrator step', async () => {
  renderTenant(); await screen.findByRole('textbox', { name: 'Tenant name' });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveFocus());
  fireEvent.change(screen.getByRole('textbox', { name: 'Tenant name' }), { target: { value: 'New Books' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveAttribute('aria-invalid', 'true');
  expect(writes()).toHaveLength(0);
  fireEvent.change(screen.getByRole('combobox', { name: 'State' }), { target: { value: 'IN-MH' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Administrator' })).toHaveFocus();
});
it('clears state when country changes and permits countries without states', async () => {
  fetcher.mockResolvedValue(Response.json({ ...choices, countries: [...choices.countries, { code: 'SG', name: 'Singapore' }] }));
  renderTenant(); await screen.findByRole('textbox', { name: 'Tenant name' });
  fireEvent.change(screen.getByRole('combobox', { name: 'State' }), { target: { value: 'IN-MH' } });
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'SG');
  expect(screen.getByRole('combobox', { name: 'State' })).toHaveValue('');
  expect(screen.getByRole('combobox', { name: 'State' })).toBeDisabled();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'IN');
  expect(screen.getByRole('combobox', { name: 'State' })).toBeEnabled();
});
it('validates administrator identity, email and attestation before checking pending registrations', async () => {
  renderTenant(); await fillTenant();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByRole('textbox', { name: 'Administrator email' })).toHaveAttribute('aria-invalid', 'true');
  expect(fetcher.mock.calls.some(call => JSON.parse(call[1].body).path.includes('pending-registration'))).toBe(false);
  fillAdministrator(); await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Review & create' })).toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});
it('validates an entered password, hides it in review, and retains it when editing the step', async () => {
  renderTenant(); await fillTenant(); fillAdministrator();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Temporary password' }), 'enter');
  fireEvent.change(screen.getByLabelText('Temporary password', { selector: 'input' }), { target: { value: 'short' } });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByLabelText('Temporary password', { selector: 'input' })).toHaveAttribute('aria-invalid', 'true');
  const secret = crypto.randomUUID();
  fireEvent.change(screen.getByLabelText('Temporary password', { selector: 'input' }), { target: { value: secret } });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('heading', { name: 'Review & create', level: 1 });
  expect(screen.queryByText(secret)).not.toBeInTheDocument(); expect(sessionStorage.length).toBe(0);
  await userEvent.click(screen.getByRole('button', { name: 'Edit password' }));
  expect(screen.getByLabelText('Temporary password', { selector: 'input' })).toHaveValue(secret);
});
it('checks pending signup on step two, offers Yes or No and never creates a duplicate tenant', async () => {
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (...args) => JSON.parse(args[1].body).path.includes('pending-registration') ? Response.json({ match: { id, name: 'New Owner', email: 'new@example.invalid', workspace_name: 'Requested Books' } }) : original(...args));
  renderTenant(); await fillTenant(); fillAdministrator();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByRole('dialog', { name: 'Pending account registration found' })).toHaveTextContent('Requested Books');
  await userEvent.click(screen.getByRole('button', { name: 'No, keep draft' }));
  expect(screen.getByRole('textbox', { name: 'Administrator email' })).toHaveValue('new@example.invalid');
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Yes, review account' }));
  expect(navigate).toHaveBeenCalledWith('/platform/accounts/' + id); expect(writes()).toHaveLength(0);
});
it('finds and explicitly selects an existing administrator without resetting their password', async () => {
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (...args) => JSON.parse(args[1].body).path.includes('/available') ? Response.json({ available: { email: 'new@example.invalid', name: 'Existing Owner', username: 'existing-owner' } }) : JSON.parse(args[1].body).method === 'POST' ? Response.json({ ...created, administrator_username: 'existing-owner', administrator_password: null, administrator_mode: 'existing' }) : original(...args));
  renderTenant(); await fillTenant();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Administrator account' }), 'existing');
  fireEvent.change(screen.getByRole('textbox', { name: 'Administrator email' }), { target: { value: 'new@example.invalid' } });
  await userEvent.click(screen.getByRole('button', { name: 'Find available account' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Use this account' }));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('heading', { name: 'Review & create', level: 1 });
  expect(screen.getByText('Keeps the existing password')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  expect(await screen.findByText('The selected administrator keeps their existing password.')).toBeInTheDocument();
  expect(writes()[0].body).toMatchObject({ administrator_mode: 'existing', administrator_password: null, administrator_name: 'Existing Owner' });
});
it('discards stale existing-account lookup results after the email changes', async () => {
  const original = fetcher.getMockImplementation()!; let finish!: (value: Response) => void;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).path.includes('/available') ? new Promise(resolve => { finish = resolve; }) : original(...args));
  renderTenant(); await fillTenant();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Administrator account' }), 'existing');
  fireEvent.change(screen.getByRole('textbox', { name: 'Administrator email' }), { target: { value: 'old@example.invalid' } });
  await userEvent.click(screen.getByRole('button', { name: 'Find available account' }));
  await waitFor(() => expect(finish).toBeDefined());
  fireEvent.change(screen.getByRole('textbox', { name: 'Administrator email' }), { target: { value: 'new@example.invalid' } });
  await act(async () => finish(Response.json({ available: { email: 'old@example.invalid', name: 'Old Owner', username: 'old' } })));
  expect(screen.queryByRole('button', { name: 'Use this account' })).not.toBeInTheDocument();
});
it('supports review Edit links and blocks advancing after a visited step becomes invalid', async () => {
  renderTenant(); await reachTenantReview();
  expect(screen.getByText('New Books', { selector: 'dd span' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Edit tenant name' }));
  expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveValue('New Books');
  fireEvent.change(screen.getByRole('textbox', { name: 'Tenant name' }), { target: { value: '' } });
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getByRole('button', { name: /Review & create/ }));
  expect(screen.getByRole('heading', { level: 1, name: 'Tenant details' })).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveAttribute('aria-invalid', 'true');
});
it.each(['manual', 'queued'])('creates once and keeps private manual access details (%s)', async notificationStatus => {
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST'
    ? Response.json({ ...created, notification_status: notificationStatus }, { status: 201 }) : original(...args));
  renderTenant({ returnTo: '/platform/tenants?status=active' }); await reachTenantReview();
  const button = screen.getByRole('button', { name: 'Create tenant' });
  fireEvent.submit(button.closest('form')!); fireEvent.submit(button.closest('form')!);
  expect(await screen.findByText('Tenant and administrator are ready.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Tenant created' })).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: 'One-time password' })).toHaveValue(created.administrator_password);
  for (const name of ['Copy access link', 'Copy sign-in details', 'Copy password']) expect(screen.getByRole('button', { name })).toBeEnabled();
  expect(screen.getByText(notificationStatus === 'queued' ? /Account-ready email is queued/ : /Automatic email is not configured/)).toBeInTheDocument();
  expect(writes()).toHaveLength(1);
  expect(writes()[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect(writes()[0].body.administrator_password).toMatch(/^[0-9a-f]{32}Aa1!$/);
  expect(screen.getByRole('link', { name: 'Return to directory' })).toHaveAttribute('href', '/platform/tenants?status=active');
});
it('rechecks pending registration before the final write', async () => {
  renderTenant(); await reachTenantReview();
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).path.includes('pending-registration') ? Response.json({ match: { id, name: 'Owner', email: 'new@example.invalid', workspace_name: 'Pending Books' } }) : original(...args));
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  expect(await screen.findByRole('dialog')).toHaveTextContent('Pending Books'); expect(writes()).toHaveLength(0);
});
it('retains command identity and password when retrying a failed create', async () => {
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST' ? Response.json({ error: { message: 'Network unavailable' } }, { status: 503 }) : original(...args));
  renderTenant(); await reachTenantReview();
  for (let index = 0; index < 2; index++) { await userEvent.click(screen.getByRole('button', { name: 'Create tenant' })); await screen.findByText('Network unavailable'); }
  expect(writes()[0].key).toBe(writes()[1].key);
  expect(writes()[0].body.administrator_password).toBe(writes()[1].body.administrator_password);
});
it('routes a server validation error back to its administrator field', async () => {
  renderTenant(); await reachTenantReview();
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((...args) => JSON.parse(args[1].body).method === 'POST' ? Response.json({ error: { message: 'Check the email', fields: { administrator_email: 'Email unavailable' } } }, { status: 422 }) : original(...args));
  await userEvent.click(screen.getByRole('button', { name: 'Create tenant' }));
  expect(await screen.findByRole('textbox', { name: 'Administrator email' })).toHaveValue('new@example.invalid');
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Administrator email' })).toHaveFocus());
  expect(screen.getByText('Email unavailable')).toBeVisible();
});
it('guards breadcrumbs and Cancel against losing an entered draft', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  renderTenant(); await fillTenant();
  await userEvent.click(screen.getByRole('link', { name: 'Platform administration' }));
  expect(confirm).toHaveBeenCalled(); confirm.mockRestore();
});
it('loads and saves tenant edits through the existing single form', async () => {
  renderTenant({ tenantId: id });
  const name = await screen.findByRole('textbox', { name: 'Tenant name' }); expect(name).toHaveValue('Acme Books');
  expect(screen.queryByRole('navigation', { name: 'Setup progress' })).not.toBeInTheDocument();
  fireEvent.change(name, { target: { value: 'Renamed' } }); await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Tenant details updated.')).toBeInTheDocument();
  expect(JSON.parse(fetcher.mock.lastCall![1].body).body).not.toHaveProperty('slug');
});
it.each([401, 403, 404, 500])('handles edit loading failure %i without showing an edit form', async status => {
  fetcher.mockImplementation(async () => Response.json({ error: { message: 'Cannot load tenant' } }, { status })); renderTenant({ tenantId: id });
  expect(await screen.findByText('Cannot load tenant')).toBeInTheDocument(); expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
it('prevents editing a closed tenant', async () => {
  fetcher.mockImplementation(async (_url, init) => Response.json(JSON.parse(init.body).path.endsWith('tenant-options') ? choices : { ...detail, status: 'closed' }));
  renderTenant({ tenantId: id }); expect(await screen.findByText('A closed tenant cannot be changed.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument();
});

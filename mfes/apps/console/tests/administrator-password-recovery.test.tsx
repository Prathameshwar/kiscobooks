import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AdministratorPasswordRecovery } from '../app/platform/access/AdministratorPasswordRecovery';
import { PlatformAdministratorDetail } from '../app/platform/access/PlatformAdministratorDetail';
import { allowedPlatformRequest } from '../app/lib/platform-request';
import type { Administrator } from '../app/lib/platform-access';

const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/platform-api', async () => ({ ...(await vi.importActual('../app/lib/platform-api')), platformCall: call }));
vi.mock('../app/components/PlatformHistory', () => ({ PlatformHistory: () => <p>Audit history</p> }));
const tenant = '01900000-0000-7000-8000-000000000001', id = '01900000-0000-7000-8000-000000000002';
const administrator: Administrator = { id, display_name: 'Tenant Owner', email: 'owner@example.com', status: 'active', updated_at: '2026-10-26T00:00:00Z',
  tenant: { id: tenant, name: 'Acme', status: 'active' }, assignment_id: '01900000-0000-7000-8000-000000000003', assignment_updated_at: '2026-10-26T00:00:00Z',
  assignment_active: true, last_active_administrator: false, valid_from: '2026-01-01', valid_to: null, recovery_deliveries: ['link'] };
const url = 'https://provider.test/if/flow/bill-administrator-recovery/?flow_token=private_recovery_token_that_is_only_in_memory';
const receipt = (delivery = 'link') => ({ tenant_id: tenant, administrator_id: id, delivery, expires_at: new Date(Date.now() + 600_000).toISOString(), recovery_url: delivery === 'link' ? url : null });
beforeEach(() => { call.mockReset(); call.mockImplementation((_path, method) => Promise.resolve(method === 'POST' ? receipt() : administrator)); sessionStorage.clear(); Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } }); });
function show(row = administrator) { return render(<AdministratorPasswordRecovery administrator={row} returnTo="/platform/access/administrators" />); }
async function confirm() {
  await userEvent.click(screen.getByRole('button', { name: 'Reset password' }));
  await userEvent.type(screen.getByRole('textbox', { name: 'Reason' }), 'Administrator requested recovery');
}
it('keeps email disabled until configuration and validates the reason', async () => {
  show(); await userEvent.click(screen.getByRole('button', { name: 'Reset password' }));
  expect(screen.getByRole('option', { name: 'Email recovery link' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  expect(screen.getByText(/Enter a reason with 3/)).toBeInTheDocument();
  expect(call).not.toHaveBeenCalled();
});
it('creates a target-bound expiring link through a keyless call and never saves it', async () => {
  show(); await confirm(); await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  expect(await screen.findByRole('textbox', { name: 'Password recovery link' })).toHaveValue(url);
  const request = call.mock.calls[0];
  expect(request[0]).toBe(`/v1/platform/access/tenants/${tenant}/administrators/${id}/password-recovery`);
  expect(request[2]).toEqual({ delivery: 'link', reason: 'Administrator requested recovery', expected_updated_at: administrator.updated_at, expected_assignment_updated_at: administrator.assignment_updated_at });
  expect(request[3]).toBeUndefined();
  expect(JSON.stringify(sessionStorage)).not.toContain('private_recovery_token');
  await userEvent.click(screen.getByRole('button', { name: 'Copy recovery link' }));
  expect(await screen.findByText(/Recovery link copied/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Hide recovery link' }));
  expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
});
it('shows the local provider’s one-time link, as it does Authentik’s', async () => {
  const local = 'https://bill.example.com/reset?token=A1b2C3d4E5f6G7h8I9j0K-L_mNoPqRsTuVwXyZ01234';
  call.mockImplementation((_path, method) => Promise.resolve(method === 'POST' ? { ...receipt(), recovery_url: local } : administrator));
  show(); await confirm(); await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  expect(await screen.findByRole('textbox', { name: 'Password recovery link' })).toHaveValue(local);
});
it('refuses a link that is neither provider’s shape, and hides it', async () => {
  const evil = 'https://evil.example/reset?token=A1b2C3d4E5f6G7h8I9j0K-L_mNoPqRsTuVwXyZ01234&next=https://evil.example';
  call.mockImplementation((_path, method) => Promise.resolve(method === 'POST' ? { ...receipt(), recovery_url: evil } : administrator));
  show(); await confirm(); await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  await screen.findByRole('alert');
  expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue(evil)).not.toBeInTheDocument();
});
it('requests native email when enabled and does not expose a link', async () => {
  call.mockResolvedValue(receipt('email'));
  show({ ...administrator, recovery_deliveries: ['link', 'email'] }); await confirm();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Delivery' }), 'email');
  await userEvent.click(screen.getByRole('button', { name: 'Email recovery link' }));
  expect(await screen.findByText(/Recovery email requested for owner/)).toBeInTheDocument();
  expect(call.mock.calls[0][2].delivery).toBe('email');
  expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
});
it('locks duplicate submissions and cancellation until the provider responds', async () => {
  let resolve!: (value: unknown) => void;
  call.mockReturnValue(new Promise(value => { resolve = value; }));
  show(); await confirm();
  const button = screen.getByRole('button', { name: 'Create recovery link' });
  fireEvent.click(button); fireEvent.click(button);
  expect(call).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  resolve(receipt()); await screen.findByRole('textbox', { name: 'Password recovery link' });
});
it.each([401, 403, 409, 503])('shows deliberate failure and never automatically retries (%s)', async status => {
  call.mockRejectedValue({ status, code: status === 403 ? 'platform_reauthentication_required' : 'unavailable', message: 'Recovery unavailable' });
  show(); await confirm(); await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Recovery unavailable');
  expect(call).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
  if (status === 401 || status === 403) expect(screen.getByRole('link', { name: 'Sign in again' })).toBeInTheDocument();
  if (status === 503) expect(screen.getByText(/not automatically retried/)).toBeInTheDocument();
});
it('rejects a mismatched target receipt and hides its secret', async () => {
  call.mockResolvedValue({ ...receipt(), administrator_id: tenant });
  show(); await confirm(); await userEvent.click(screen.getByRole('button', { name: 'Create recovery link' }));
  await screen.findByRole('alert'); expect(screen.queryByDisplayValue(url)).not.toBeInTheDocument();
});
it('withholds recovery from readers and locks unavailable accounts', async () => {
  const view = render(<PlatformAdministratorDetail tenantId={tenant} userId={id} canManage={false} />);
  await screen.findByRole('heading', { name: 'Tenant Owner' });
  expect(screen.queryByRole('button', { name: 'Reset password' })).not.toBeInTheDocument(); view.unmount();
  show({ ...administrator, status: 'suspended', recovery_deliveries: [] });
  expect(screen.getByRole('button', { name: 'Reset password' })).toBeDisabled();
});
it('allows the fixed recovery path only for POST without arbitrary query input', () => {
  const path = `/v1/platform/access/tenants/${tenant}/administrators/${id}/password-recovery`;
  expect(allowedPlatformRequest('POST', path)).toBe(true);
  expect(allowedPlatformRequest('GET', path)).toBe(false);
  expect(allowedPlatformRequest('POST', path + '?email=other@example.com')).toBe(false);
});
it('focuses the recovery action when its kebab destination loads asynchronously', async () => {
  window.history.replaceState(null, '', `/platform/access/administrators/${id}?tenant=${tenant}#password-recovery`);
  render(<PlatformAdministratorDetail tenantId={tenant} userId={id} canManage />);
  expect(await screen.findByRole('button', { name: 'Reset password' })).toHaveFocus();
  window.history.replaceState(null, '', '/platform/access/administrators');
});
it('removes an expired recovery link from the page', async () => {
  show(); await confirm();
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] });
  try {
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create recovery link' })); });
    expect(screen.getByRole('textbox', { name: 'Password recovery link' })).toHaveValue(url);
    act(() => vi.advanceTimersByTime(600_001));
    expect(screen.queryByRole('textbox', { name: 'Password recovery link' })).not.toBeInTheDocument();
    expect(screen.getByText(/recovery link has expired/)).toBeInTheDocument();
  } finally { vi.useRealTimers(); }
});

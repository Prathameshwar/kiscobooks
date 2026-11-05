import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { NotificationAdmin } from '../app/components/NotificationAdmin';
import { renderWithProviders } from './helpers';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
const id = '019a0000-0000-7000-8000-000000000001', senderId = '019a0000-0000-7000-8000-000000000002';
const account = { id, key: 'primary', display_name: 'Primary email', provider_key: 'ses', channel: 'email', status: 'active', region: 'us-east-1', credential_ref: 'env:EMAIL', updated_at: '2026-10-22T00:00:00Z', capabilities: null };
const sender = { id: senderId, provider_account_id: id, display_name: 'Billing sender', verification_status: 'verified', sender_type: 'email', external_sender_id: 'billing@example.invalid', is_active: true, updated_at: account.updated_at };
const page = (items: unknown[] = [], next: string | null = null) => ({ items, page: { has_more: !!next, next_cursor: next } });
beforeEach(() => {
  call.mockReset(); call.mockImplementation(async (_owner, path, method = 'GET') => {
    if (method !== 'GET') return { ...account, id, status: 'pending' };
    if (path === 'credential-bindings') return ['env:EMAIL', 'env:CALLBACK'];
    if (path.endsWith('/callback-configuration')) return { url: 'https://example.invalid/notification/v1/callbacks/email/key', signature_scheme: 'SNS RSA', ready: true };
    if (path.startsWith('provider-accounts?')) return page([account], 'opaque cursor');
    if (path.startsWith('provider-accounts/')) return account;
    if (path.startsWith('sender-identities?')) return page([sender]);
    if (path.startsWith('sender-identities/')) return sender;
    if (path.startsWith('jobs/')) return { id, status: 'completed', reason_code: 'verified' };
    return page();
  });
});
async function mount(route: string[], manage = true) {
  await act(async () => { await renderWithProviders(<NotificationAdmin owner="platform" permissions={['platform.notification_provider.read', ...(manage ? ['platform.notification_provider.manage'] : [])]} route={route} />); });
}
it('uses a paged provider table and preserves API filters in the next link', async () => {
  await mount(['providers']);
  expect(screen.getByRole('link', { name: 'Primary email' })).toHaveAttribute('href', '/platform/notifications/providers/' + id);
  expect(screen.getByRole('link', { name: 'Next page' })).toHaveAttribute('href', '/platform/notifications/providers?cursor=opaque+cursor');
  expect(screen.getByRole('form', { name: 'Filter list' })).toHaveAttribute('method', 'get');
});
it.each(['ses', 'twilio', 'meta'])('submits a channel-specific %s account without secret values', async provider => {
  await mount(['providers']); fireEvent.click(screen.getByRole('button', { name: 'Add provider' }));
  fireEvent.change(screen.getByLabelText('Provider'), { target: { value: provider } });
  fireEvent.change(screen.getByLabelText('Account key'), { target: { value: 'new-provider' } });
  fireEvent.change(screen.getByLabelText('Account name'), { target: { value: 'New account' } });
  await waitFor(() => expect(screen.getAllByRole('option', { name: 'env:EMAIL' }).length).toBeGreaterThan(0));
  fireEvent.change(screen.getByLabelText('Credential binding'), { target: { value: 'env:EMAIL' } });
  if (provider === 'ses') fireEvent.change(screen.getByLabelText('AWS region'), { target: { value: 'us-east-1' } });
  else fireEvent.change(screen.getByLabelText('Callback signature binding'), { target: { value: 'env:CALLBACK' } });
  if (provider === 'meta') fireEvent.change(screen.getByLabelText('WhatsApp verification-token binding'), { target: { value: 'env:CALLBACK' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add provider' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', 'provider-accounts', 'POST', expect.objectContaining({ provider_key: provider, channel: ({ ses: 'email', twilio: 'sms', meta: 'whatsapp' } as Record<string, string>)[provider], credential_ref: 'env:EMAIL' }), undefined, expect.any(AbortSignal)));
});
it('keeps a conflicting provider edit open and sends the expected revision', async () => {
  await mount(['providers', id]); fireEvent.click(screen.getByRole('button', { name: 'Edit provider' }));
  await waitFor(() => expect(screen.getByRole('option', { name: 'env:EMAIL' })).toBeInTheDocument());
  call.mockImplementation(async (_owner, _path, method) => { if (method === 'PATCH') throw { status: 409, message: 'Configuration changed' }; return ['env:EMAIL']; });
  fireEvent.submit(screen.getByRole('form', { name: 'Edit provider' }));
  expect(await screen.findByText(/Configuration changed/)).toBeVisible();
  expect(screen.getByRole('dialog', { name: 'Edit provider' })).toBeVisible();
  expect(call).toHaveBeenCalledWith('platform', 'provider-accounts/' + id, 'PATCH', expect.objectContaining({ expected_updated_at: account.updated_at }), undefined, expect.any(AbortSignal));
});
it('retains command identity after a lost provider-validation response', async () => {
  await mount(['providers', id]);
  let writes = 0;
  call.mockImplementation(async (_owner, path, method) => {
    if (method === 'POST') { if (++writes === 1) throw { status: 503, message: 'Response lost' }; return { id }; }
    if (path.startsWith('jobs/')) return { id, status: 'completed', reason_code: 'verified' };
    return account;
  });
  fireEvent.click(screen.getByRole('button', { name: 'Validate provider' })); await screen.findByText('Response lost');
  fireEvent.click(screen.getByRole('button', { name: 'Validate provider' })); await screen.findByText('Validation queued.');
  const requests = call.mock.calls.filter(values => values[1].endsWith('/validate'));
  expect(requests[0][4]).toBe(requests[1][4]); expect(requests[0][3]).toEqual(requests[1][3]);
});
it('read-only provider detail has callbacks and senders but no mutation buttons', async () => {
  await mount(['providers', id], false);
  expect(screen.getByRole('link', { name: 'Manage sender identities' })).toHaveAttribute('href', `/platform/notifications/providers/${id}/senders`);
  expect(screen.queryByRole('button', { name: 'Edit provider' })).not.toBeInTheDocument();
  expect(screen.getByText('SNS RSA')).toBeVisible();
});
it('reports callback copy failures beside the callback URL and copy control', async () => {
  await mount(['providers', id], false);
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('Unavailable')) } });
  const copy = screen.getByRole('button', { name: 'Copy callback URL' });
  const card = copy.closest<HTMLElement>('.janso-card')!;
  fireEvent.click(copy);
  expect(await within(card).findByText('The notification is unavailable. Try again.')).toBeVisible();
});
it('does not describe an active unverified sender as available to routes', async () => {
  call.mockImplementation(async (_owner, path) => path.startsWith('provider-accounts/') ? account : { ...sender, verification_status: 'unverified' });
  await mount(['providers', id, 'senders', senderId]);
  expect(screen.getByText('Not ready for routing')).toBeVisible();
  expect(screen.queryByText('Available to routes')).not.toBeInTheDocument();
});
it('verifies a sender through a provider job', async () => {
  await mount(['providers', id, 'senders', senderId]);
  fireEvent.click(screen.getByRole('button', { name: 'Verify sender' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', `sender-identities/${senderId}/verify`, 'POST', {}, expect.any(String), expect.any(AbortSignal)));
});
it('prevents a mismatched sender detail from being edited or verified', async () => {
  call.mockImplementation(async (_owner, path) => path.startsWith('provider-accounts/') ? account : { ...sender, provider_account_id: senderId });
  await mount(['providers', id, 'senders', senderId]);
  expect(screen.getByText('This sender does not belong to the selected provider.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Edit sender' })).not.toBeInTheDocument();
});

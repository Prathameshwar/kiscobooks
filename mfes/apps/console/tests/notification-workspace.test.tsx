import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { NotificationWorkspace } from '../app/components/NotificationWorkspace';
import { NotificationAdmin } from '../app/components/NotificationAdmin';
import { renderWithProviders } from './helpers';
import { Providers } from '../app/providers';
import { ID, baseResponse, mountNotification } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
beforeEach(() => { call.mockReset(); call.mockImplementation(async (owner, path, method, body) => path === 'channels' ? [{ channel: 'email', is_enabled: true, ready: true, reasons: [] }] : baseResponse(owner, path, method, body)); });
it('keeps the original workspace export connected to the routed administration UI', async () => {
  await act(async () => { await renderWithProviders(<NotificationWorkspace owner="platform" permissions={['platform.notification_provider.read']} />); });
  expect(screen.getByRole('navigation', { name: 'Notification areas' })).toBeVisible();
});
it('denies the entire workspace without notification grants', async () => {
  await mountNotification([], { permissions: [] });
  expect(screen.getByText('Notification access is required for this area.')).toBeVisible(); expect(call).not.toHaveBeenCalled();
});
it.each([401, 403, 422, 500])('retains error status %s and offers a read retry', async status => {
  call.mockRejectedValue({ status, message: 'Could not read current notification configuration' });
  await mountNotification(['channels']);
  expect(screen.getByText('Could not read current notification configuration')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(call.mock.calls.length).toBeGreaterThan(1));
});
it('reports a scoped missing record without presenting it as an outage', async () => {
  call.mockRejectedValue({ status: 404, message: 'not found' });
  await mountNotification(['requests', ID]);
  expect(screen.getByText('This notification record was not found in the current scope.')).toBeVisible();
});
it('aborts and ignores the previous owner response after a realm change', async () => {
  let resolve!: (value: unknown) => void;
  let previousSignal: AbortSignal | undefined;
  call.mockImplementation((owner, _path, _method, _body, _key, signal) => {
    if (owner === 'tenant') { previousSignal = signal; return new Promise(done => { resolve = done; }); }
    return Promise.resolve([{ channel: 'sms', is_enabled: true, ready: true, reasons: [] }]);
  });
  let rendered!: Awaited<ReturnType<typeof renderWithProviders>>;
  await act(async () => { rendered = await renderWithProviders(<NotificationAdmin owner="tenant" permissions={['notification.provider.read']} />); });
  await act(async () => { rendered.rerender(<Providers session={rendered.session}><NotificationAdmin owner="platform" permissions={['platform.notification_provider.read']} /></Providers>); });
  expect(previousSignal?.aborted).toBe(true);
  await act(async () => resolve([{ channel: 'email', is_enabled: true, ready: true, reasons: [] }]));
  expect(screen.getByRole('link', { name: 'sms' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'email' })).not.toBeInTheDocument();
});
it('preserves opaque paging filters in durable navigation', async () => {
  call.mockResolvedValue({ items: [], page: { has_more: true, next_cursor: 'signed opaque' } });
  await mountNotification(['deliveries'], { query: { channel: 'sms', status: 'failed', cursor: 'previous' } });
  expect(Object.fromEntries(new URL(screen.getByRole('link', { name: 'Next page' }).getAttribute('href')!, 'http://test').searchParams)).toEqual({ channel: 'sms', status: 'failed', cursor: 'signed opaque' });
  expect(Object.fromEntries(new URL(screen.getByRole('link', { name: 'First page' }).getAttribute('href')!, 'http://test').searchParams)).toEqual({ channel: 'sms', status: 'failed' });
});
it('returns from a provider record to the filtered page it was opened from', async () => {
  const query = { channel: 'email', status: 'active', cursor: 'signed opaque' };
  const list = await mountNotification(['providers'], { query });
  const link = new URL(screen.getByRole('link', { name: 'Primary transport' }).getAttribute('href')!, 'https://test.invalid');
  expect(link.searchParams.get('back')).toBe('providers?cursor=signed+opaque&status=active&channel=email');
  list.unmount();
  await mountNotification(['providers', ID], { query: Object.fromEntries(link.searchParams) });
  const back = new URL(screen.getByRole('link', { name: 'Back to providers and senders' }).getAttribute('href')!, 'https://test.invalid');
  expect(back.pathname).toBe('/platform/notifications/providers');
  expect(Object.fromEntries(back.searchParams)).toEqual(query);
});
it.each(['https://evil.invalid/providers', '../providers', '/settings/notifications/providers', 'templates?channel=sms', 'providers?destination=private', 'providers?channel=sms&channel=email', '//['])('rejects an unsafe or unrelated return destination %s', async back => {
  await mountNotification(['providers', ID], { query: { back } });
  expect(screen.getByRole('link', { name: 'Back to providers and senders' })).toHaveAttribute('href', '/platform/notifications/providers');
});
it('requires channel prerequisites while allowing a configured disabled channel to be enabled', async () => {
  call.mockResolvedValue([{ channel: 'email', is_enabled: false, ready: false, reasons: ['channel_disabled', 'no_verified_sender'] }]);
  await mountNotification(['channels']); expect(screen.getByRole('button', { name: 'Enable email' })).toBeDisabled();
});
it('connects server field errors to the relevant shared form control', async () => {
  await mountNotification(['providers']); fireEvent.click(screen.getByRole('button', { name: 'Add provider' }));
  fireEvent.change(screen.getByLabelText('Account key'), { target: { value: 'primary' } });
  fireEvent.change(screen.getByLabelText('Account name'), { target: { value: 'Account' } });
  await screen.findByRole('option', { name: 'env:EMAIL' });
  fireEvent.change(screen.getByLabelText('Credential binding'), { target: { value: 'env:EMAIL' } });
  fireEvent.change(screen.getByLabelText('AWS region'), { target: { value: 'bad' } });
  call.mockRejectedValue({ status: 422, message: 'Invalid region', fields: { 'body.region': 'Choose a supported region' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add provider' }));
  await screen.findByText('Choose a supported region');
  expect(screen.getByLabelText('AWS region')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByLabelText('AWS region')).toHaveAccessibleDescription(/Choose a supported region/);
});

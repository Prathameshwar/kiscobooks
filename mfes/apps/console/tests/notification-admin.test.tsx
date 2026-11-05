import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen } from '@testing-library/react';
import { NotificationAdmin } from '../app/components/NotificationAdmin';
import { renderWithProviders } from './helpers';
import { validNotificationRoute, notificationAccess } from '../app/lib/notification-navigation';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
beforeEach(() => { call.mockReset(); call.mockResolvedValue([{ channel: 'email', is_enabled: false, ready: false, reasons: ['channel_disabled'] }]); });
async function mount(props: Partial<React.ComponentProps<typeof NotificationAdmin>> = {}) {
  await act(async () => { await renderWithProviders(<NotificationAdmin owner="platform" permissions={['platform.notification_provider.read']} {...props} />); });
}
it('links platform overview to authorized areas using the existing card layout', async () => {
  await mount();
  expect(screen.getByRole('heading', { name: 'Platform notifications' })).toBeVisible();
  expect(screen.getAllByRole('link', { name: 'Providers and senders' })[0]).toHaveAttribute('href', '/platform/notifications/providers');
  expect(screen.queryByRole('link', { name: 'Templates' })).not.toBeInTheDocument();
  expect(call).toHaveBeenCalledWith('platform', 'channels', 'GET', undefined, undefined, expect.any(AbortSignal));
});
it.each([undefined, '019a0000-0000-7000-8000-000000000001'])('uses Notifications for the tenant workspace with company context %s', async companyId => {
  await mount({ owner: 'tenant', permissions: ['notification.provider.read'], companyId });
  expect(screen.getByRole('heading', { level: 1, name: 'Notifications' })).toBeVisible();
  expect(screen.queryByRole('heading', { name: /Tenant notifications|Organisation notifications/i })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Administration' })).toHaveAttribute('href', '/organisation');
  expect(call).toHaveBeenCalledWith('tenant', 'channels', 'GET', undefined, undefined, expect.any(AbortSignal));
});
it('keeps policy-only users in their permitted section without provider requests', async () => {
  await mount({ permissions: ['platform.notification_consent.manage'] });
  expect(screen.getAllByRole('link', { name: 'Consent' })[0]).toBeVisible(); expect(call).not.toHaveBeenCalled();
  expect(notificationAccess('platform', ['notification.consent.manage'])).toBe(false);
});
it('denies direct visits to an unauthorized area without issuing its API calls', async () => {
  await mount({ route: ['templates'] });
  expect(screen.getByText('Notification access is required for this area.')).toBeVisible(); expect(call).not.toHaveBeenCalled();
});
it('enables a configured disabled channel after confirmation', async () => {
  await mount({ route: ['channels'], permissions: ['platform.notification_provider.read', 'platform.notification_provider.manage'] });
  fireEvent.click(screen.getByRole('button', { name: 'Enable email' }));
  expect(call).not.toHaveBeenCalledWith('platform', 'channel-settings/email', 'PUT', expect.anything(), expect.anything(), expect.anything());
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await screen.findByRole('button', { name: 'Enable email' });
  expect(call).toHaveBeenCalledWith('platform', 'channel-settings/email', 'PUT', { is_enabled: true }, undefined, expect.any(AbortSignal));
});
it('validates deep routes and rejects arbitrary path shapes', () => {
  const id = '019a0000-0000-7000-8000-000000000001';
  expect(validNotificationRoute(['templates', id, 'variants', id, 'versions', id])).toBe(true);
  expect(validNotificationRoute(['providers', id, 'senders'])).toBe(true);
  expect(validNotificationRoute(['providers', 'bad'])).toBe(false);
  expect(validNotificationRoute(['callbacks'])).toBe(false);
});

import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { ID, OTHER, VERSION, WHEN, baseResponse, mountNotification, page, readPermissions } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
const delivery = { id: ID, request_id: OTHER, channel: 'sms', destination_masked: '***1234', status: 'failed', status_reason: 'provider_failure', attempt_count: 1, created_at: WHEN, accepted_at: null, delivered_at: null, completed_at: WHEN, recipient_endpoint_id: OTHER, template_version_id: VERSION, provider_account_id: ID, sender_identity_id: OTHER, routing_rule_id: ID };
const receipt = { id: OTHER, provider_account_id: ID, provider_message_id: 'native-message', attempt_key: ID + ':1', event_type: 'delivered', processing_status: 'unmatched', signature_verified: true, delivery_id: null, received_at: WHEN };
beforeEach(() => { call.mockReset(); call.mockImplementation(async (owner, path, method, body) => {
  if (method === 'POST') return delivery;
  if (path.startsWith('deliveries?') || path.startsWith('reconciliation-cases?')) return page([delivery]);
  if (path.includes('/attempts?')) return page([{ id: OTHER, attempt_number: 1, outcome: 'permanent_failure', started_at: WHEN }]);
  if (path.includes('/events?')) return page([{ id: OTHER, source: 'sms', to_status: 'failed', observed_at: WHEN }]);
  if (path.startsWith('deliveries/')) return delivery;
  if (path.startsWith('provider-events?')) return page([receipt]);
  if (path.startsWith('provider-events/')) return receipt;
  if (path.startsWith('requests/') && path.includes('/outcomes?')) return page([{ id: OTHER, channel: 'email', decision: 'skipped', reason_code: 'no_active_template_assignment', created_at: WHEN }]);
  if (path.startsWith('requests/')) return { id: OTHER, event_key: 'platform.staff.alert', category: 'operational', status: 'completed', source_service: 'identity', source_event_key: 'identity.platform_notification.requested', received_at: WHEN, aggregate_id: ID };
  return baseResponse(owner, path, method, body);
}); });
it('shows per-channel planning reasons and links to filtered delivery history', async () => {
  await mountNotification(['requests', OTHER]);
  expect(screen.getByText('no active template assignment')).toBeVisible();
  expect(screen.getByRole('link', { name: 'View deliveries for this request' })).toHaveAttribute('href', '/platform/notifications/deliveries?request_id=' + OTHER);
});
it('shows attempt and timeline evidence alongside masked recipient and source links', async () => {
  await mountNotification(['deliveries', ID]);
  expect(screen.getByRole('table', { name: 'Delivery attempts' })).toBeVisible();
  expect(screen.getByRole('table', { name: 'Delivery events' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Inspect consent' })).toHaveAttribute('href', '/platform/notifications/consent?recipient_endpoint_id=' + OTHER);
});
it('retains retry identity after a lost response and keeps the confirmation open', async () => {
  await mountNotification(['deliveries', ID]); fireEvent.click(screen.getByRole('button', { name: 'Retry delivery' }));
  let writes = 0;
  call.mockImplementation(async (owner, path, method, body) => {
    if (path.endsWith('/retry')) { if (++writes === 1) throw { status: 503, message: 'Retry response lost' }; return delivery; }
    return baseResponse(owner, path, method, body);
  });
  fireEvent.click(screen.getAllByRole('button', { name: 'Retry delivery' }).at(-1)!);
  await screen.findByText('Retry response lost');
  fireEvent.click(screen.getAllByRole('button', { name: 'Retry delivery' }).at(-1)!);
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Retry delivery' })).not.toBeInTheDocument());
  const attempts = call.mock.calls.filter(args => args[1].endsWith('/retry'));
  expect(attempts[0][4]).toBe(attempts[1][4]);
});
it('does not expose manual retries to readers', async () => {
  await mountNotification(['deliveries', ID], { permissions: readPermissions });
  expect(screen.queryByRole('button', { name: 'Retry delivery' })).not.toBeInTheDocument();
});
it('requires matching verified evidence for an unresolved delivery', async () => {
  call.mockImplementation(async (owner, path, method, body) => path === 'deliveries/' + ID ? { ...delivery, status: 'sending' } : path.startsWith('provider-events?') ? page([receipt, { ...receipt, id: VERSION, signature_verified: false, provider_message_id: 'unverified-message' }]) : baseResponse(owner, path, method, body));
  await mountNotification(['deliveries', ID]);
  expect(screen.queryByRole('button', { name: 'Retry delivery' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Link verified receipt' }));
  await waitFor(() => expect(screen.getByRole('option', { name: /native-message/ })).toBeInTheDocument());
  expect(screen.queryByRole('option', { name: /unverified-message/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Matching provider receipt'), { target: { value: OTHER } });
  fireEvent.submit(screen.getByRole('form', { name: 'Link verified receipt' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', `deliveries/${ID}/reconciliation`, 'POST', { provider_event_id: OTHER }, expect.any(String), expect.any(AbortSignal)));
});
it('separates an in-flight delivery from a settled one by tone, not by wording alone', async () => {
  call.mockImplementation(async (owner, path, method, body) => path === 'deliveries/' + ID ? { ...delivery, status: 'sending' } : baseResponse(owner, path, method, body));
  await mountNotification(['deliveries', ID]);
  // `sending` used to render in the same neutral grey as `cancelled`: an unresolved provider
  // outcome is the one state this screen exists to chase, so it gets the in-flight tone.
  expect(screen.getByText('sending')).toHaveAttribute('data-tone', 'info');
  expect(screen.getByText('The provider outcome is unresolved')).toBeVisible();
});
it('steps through a delivery’s own attempt pages without leaving the record', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.includes('/attempts?')
    ? page([{ id: OTHER, attempt_number: 1, outcome: 'permanent_failure', started_at: WHEN }], 'more attempts')
    : path === 'deliveries/' + ID ? delivery : baseResponse(owner, path, method, body));
  await mountNotification(['deliveries', ID]);
  const pager = screen.getByRole('navigation', { name: 'attempt pages' });
  expect(within(pager).getByText('First page of attempts')).toBeVisible();
  expect(within(pager).queryByRole('button', { name: 'First attempt page' })).not.toBeInTheDocument();
  fireEvent.click(within(pager).getByRole('button', { name: 'Next attempt page' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'First attempt page' })).toBeVisible());
});
it('shows safe receipt references and no raw provider payload', async () => {
  await mountNotification(['receipts', OTHER]);
  expect(screen.getByText('Verified against the registered provider trust configuration')).toBeVisible();
  expect(screen.queryByText('payload_ciphertext')).not.toBeInTheDocument();
});
it('does not infer successful delivery from an empty recovery queue', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('reconciliation-cases?') ? page() : baseResponse(owner, path, method, body));
  await mountNotification(['recovery']);
  expect(screen.getByText('No sending deliveries currently require reconciliation. Other delivery states are listed in delivery history.')).toBeVisible();
  expect(screen.queryByText(/Every delivery has a settled provider outcome/)).not.toBeInTheDocument();
});
it('returns a delivery opened from recovery to the recovery queue', async () => {
  const list = await mountNotification(['recovery']);
  const link = new URL(screen.getByRole('link', { name: '***1234' }).getAttribute('href')!, 'https://test.invalid');
  expect(link.searchParams.get('back')).toBe('recovery?');
  list.unmount();
  await mountNotification(['deliveries', ID], { query: Object.fromEntries(link.searchParams) });
  expect(screen.getByRole('link', { name: 'Back to recovery' })).toHaveAttribute('href', '/platform/notifications/recovery');
});

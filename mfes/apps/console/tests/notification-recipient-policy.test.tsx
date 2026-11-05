import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { ID, WHEN, baseResponse, mountNotification, page } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
const endpoint = { id: ID, subject_id: ID, subject_type: 'platform_recipient', channel: 'email', destination_masked: 's***@example.invalid', verification_status: 'verified', health_status: 'healthy', is_active: true };
beforeEach(() => { call.mockReset(); call.mockImplementation(async (owner, path, method, body) => {
  if (path.startsWith('recipient-endpoints/')) return endpoint;
  if (path.startsWith('recipient-endpoints?')) return page([endpoint]);
  if (path.startsWith('consent-states?')) return page([{ id: ID, recipient_endpoint_id: ID, purpose: 'marketing', state: 'granted', effective_at: WHEN, expires_at: null }]);
  if (path.startsWith('suppressions?')) return page([{ id: ID, channel: 'email', scope_type: 'global', scope_key: '', source: 'manual', reason: 'complaint', valid_from: WHEN, valid_to: null }]);
  return baseResponse(owner, path, method, body);
}); });
it('does not invent a global directory or request endpoints before a reference is provided', async () => {
  await mountNotification(['recipients']); expect(call).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox', { name: 'Subject reference (UUID)' })).toBeVisible();
});
it('opens a masked endpoint and links its policy without fetching raw addresses', async () => {
  await mountNotification(['recipients'], { query: { recipient_endpoint_id: ID } });
  expect(screen.getByText('s***@example.invalid')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Manage consent' })).toHaveAttribute('href', '/platform/notifications/consent?recipient_endpoint_id=' + ID);
  expect(call).toHaveBeenCalledWith('platform', 'recipient-endpoints/' + ID, 'GET', undefined, undefined, expect.any(AbortSignal));
});
it('presents an unsearched lookup as an empty search, not as an error', async () => {
  await mountNotification(['recipients']);
  expect(screen.getByText('Search for a recipient endpoint')).toBeVisible();
  expect(screen.getByText('Recipients come from authorized source records. This view does not create or change their addresses.')).toBeVisible();
});
it('sends a consent-only operator to the endpoint list when no endpoint is chosen', async () => {
  await mountNotification(['consent']);
  expect(screen.getByText('Choose a recipient endpoint')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open recipient endpoints' })).toHaveAttribute('href', '/platform/notifications/recipients');
});
it('uses bounded subject lookup and rejects malformed UUID input locally', async () => {
  await mountNotification(['recipients'], { query: { subject_id: 'malformed' } }); expect(call).not.toHaveBeenCalled();
  expect(screen.getByText('Enter a valid source-issued UUID reference.')).toBeVisible();
});
it('allows consent-only operators without attempting recipient reads', async () => {
  await mountNotification(['consent'], { query: { recipient_endpoint_id: ID }, permissions: ['platform.notification_consent.manage'] });
  expect(screen.getByText('granted')).toBeVisible();
  expect(call.mock.calls.some(args => args[1].startsWith('recipient-endpoints'))).toBe(false);
});
it('retains evidence body and command identity after a lost consent response', async () => {
  await mountNotification(['consent'], { query: { recipient_endpoint_id: ID } });
  fireEvent.click(screen.getByRole('button', { name: 'Record consent evidence' }));
  fireEvent.change(screen.getByLabelText('Evidence reference'), { target: { value: 'evidence-ref' } });
  let attempts = 0;
  call.mockImplementation(async (owner, path, method, body) => {
    if (path === 'consent-events') { if (++attempts === 1) throw { status: 503, message: 'Consent response lost' }; return { id: ID }; }
    return baseResponse(owner, path, method, body);
  });
  fireEvent.submit(screen.getByRole('form', { name: 'Record consent evidence' })); await screen.findByText('Consent response lost');
  fireEvent.submit(screen.getByRole('form', { name: 'Record consent evidence' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Record consent evidence' })).not.toBeInTheDocument());
  const writes = call.mock.calls.filter(args => args[1] === 'consent-events');
  expect(writes[0][3]).toEqual(writes[1][3]); expect(writes[0][4]).toBe(writes[1][4]);
});
it('creates a hashed-destination suppression through the API without putting it into navigation', async () => {
  await mountNotification(['suppressions']); fireEvent.click(screen.getByRole('button', { name: 'Add suppression' }));
  fireEvent.change(screen.getByLabelText('Destination to suppress'), { target: { value: 'test@example.invalid' } });
  fireEvent.change(screen.getByLabelText('Reason code'), { target: { value: 'complaint' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add suppression' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', 'suppressions', 'POST', expect.objectContaining({ destination: 'test@example.invalid', scope_type: 'global', scope_key: '' }), expect.any(String), expect.any(AbortSignal)));
  expect(document.querySelector('a[href*="test%40"]')).toBeNull();
});
it('requires confirmation before ending a suppression', async () => {
  await mountNotification(['suppressions']); fireEvent.click(screen.getByRole('button', { name: 'End suppression' }));
  expect(call.mock.calls.filter(args => args[2] === 'POST')).toHaveLength(0);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Cancel' })); });
  expect(call.mock.calls.filter(args => args[2] === 'POST')).toHaveLength(0);
});

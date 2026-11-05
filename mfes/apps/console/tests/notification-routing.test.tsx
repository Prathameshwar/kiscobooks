import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { ID, OTHER, WHEN, baseResponse, mountNotification, page, readPermissions, template } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
const route = { id: ID, event_key: 'platform.staff.alert', category: 'operational', channel: 'email', provider_account_id: ID, sender_identity_id: OTHER, company_id: template.company_id, priority: 0, weight: 1, max_attempts: 5, timeout_seconds: 20, initial_backoff_seconds: 10, max_backoff_seconds: 100, is_active: true, updated_at: WHEN };
beforeEach(() => { call.mockReset(); call.mockImplementation(async (owner, path, method, body) => path === 'routing-rules/' + ID ? route : path.startsWith('sender-identities?') ? page([{ id: OTHER, display_name: 'Verified sender', provider_account_id: ID, is_active: true, verification_status: 'verified' }]) : baseResponse(owner, path, method, body)); });
it('creates an explicit dated purpose assignment', async () => {
  await mountNotification(['assignments']); fireEvent.click(screen.getByRole('button', { name: 'Assign a purpose' }));
  await waitFor(() => expect(screen.getByRole('option', { name: 'staff-alert' })).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('Template'), { target: { value: ID } });
  fireEvent.submit(screen.getByRole('form', { name: 'Assign a purpose' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', 'use-case-bindings', 'POST', expect.objectContaining({ company_id: template.company_id, template_id: ID, event_key: template.event_key, trigger_key: 'identity.platform_notification.requested', valid_from: expect.any(String), valid_to: null }), undefined, expect.any(AbortSignal)));
});
it('retains a rejected assignment window for correction', async () => {
  await mountNotification(['assignments']); fireEvent.click(screen.getByRole('button', { name: 'Assign a purpose' }));
  await waitFor(() => expect(screen.getByRole('option', { name: 'staff-alert' })).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('Template'), { target: { value: ID } });
  call.mockImplementation(async (owner, path, method, body) => method === 'POST' ? Promise.reject({ status: 409, message: 'Assignment overlaps' }) : baseResponse(owner, path, method, body));
  fireEvent.submit(screen.getByRole('form', { name: 'Assign a purpose' }));
  expect(await screen.findByText(/Assignment overlaps/)).toBeVisible(); expect(screen.getByLabelText('Template')).toHaveValue(ID);
});
it('limits assignment templates to the selected company and resets selection when scope changes', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('templates?') ? page([{ ...template, company_id: ID }, { ...template, id: OTHER, key: 'other-company', company_id: OTHER }]) : baseResponse(owner, path, method, body));
  await mountNotification(['assignments'], { owner: 'tenant', companyId: ID, permissions: ['notification.template.read', 'notification.template.manage'] });
  fireEvent.click(screen.getByRole('button', { name: 'Assign a purpose' }));
  await screen.findByRole('option', { name: 'staff-alert' });
  expect(screen.queryByRole('option', { name: 'other-company' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Template'), { target: { value: ID } });
  fireEvent.change(screen.getByLabelText('Company scope'), { target: { value: template.company_id } });
  expect(screen.getByLabelText('Template')).toHaveValue('');
  expect(screen.queryByRole('option', { name: 'staff-alert' })).not.toBeInTheDocument();
});
it('provides API-supported routing filters and preserves them in cursor navigation', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('routing-rules?') ? page([route], 'next-route') : baseResponse(owner, path, method, body));
  await mountNotification(['routing'], { query: { channel: 'email', event_key: template.event_key, sort: 'priority' } });
  expect(screen.getByRole('form', { name: 'Filter list' })).toBeVisible();
  expect(screen.getByLabelText('Purpose key')).toHaveValue(template.event_key);
  expect(call).toHaveBeenCalledWith('platform', 'routing-rules?limit=50&channel=email&event_key=platform.staff.alert&sort=priority', 'GET', undefined, undefined, expect.any(AbortSignal));
  const next = new URL(screen.getByRole('link', { name: 'Next page' }).getAttribute('href')!, 'https://test.invalid');
  expect(next.pathname).toBe('/platform/notifications/routing');
  expect(Object.fromEntries(next.searchParams)).toEqual({ channel: 'email', event_key: template.event_key, sort: 'priority', cursor: 'next-route' });
});
it('edits all existing route policy values without resetting them to defaults', async () => {
  await mountNotification(['routing', ID]); fireEvent.click(screen.getByRole('button', { name: 'Edit route' }));
  expect(screen.getByLabelText('Maximum attempts per retry cycle')).toHaveValue(5);
  expect(screen.getByLabelText('Initial backoff (seconds)')).toHaveValue(10);
  fireEvent.change(screen.getByLabelText('Maximum backoff (seconds)'), { target: { value: '200' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Edit route' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', 'routing-rules/' + ID, 'PATCH', expect.objectContaining({ expected_updated_at: WHEN, max_attempts: 5, initial_backoff_seconds: 10, max_backoff_seconds: 200 }), undefined, expect.any(AbortSignal)));
});
it('rejects inverted backoff values before a write', async () => {
  await mountNotification(['routing', ID]); fireEvent.click(screen.getByRole('button', { name: 'Edit route' }));
  fireEvent.change(screen.getByLabelText('Maximum backoff (seconds)'), { target: { value: '2' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Edit route' }));
  expect(await screen.findByText('Maximum backoff cannot be shorter than initial backoff.')).toBeVisible();
});
it('uses the effective-policy endpoint and distinguishes readiness from delivery', async () => {
  call.mockImplementation(async (owner, path, method, body) => path === 'effective-policy' ? { ready: false, reasons: ['no_eligible_route'], route_id: null, template_version_id: null } : baseResponse(owner, path, method, body));
  await mountNotification(['routing']); fireEvent.click(screen.getByRole('button', { name: 'Check policy' }));
  await waitFor(() => expect(screen.getByRole('option', { name: 'platform / staff / alert' })).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('Registered purpose'), { target: { value: template.event_key } });
  fireEvent.submit(screen.getByRole('form', { name: 'Check effective policy' }));
  expect(await screen.findByText('no eligible route')).toBeVisible();
  expect(call).toHaveBeenCalledWith('platform', 'effective-policy', 'POST', expect.objectContaining({ event_key: template.event_key, trigger_key: 'identity.platform_notification.requested', company_id: template.company_id }), undefined, expect.any(AbortSignal));
});
it('keeps route mutations absent for read-only actors', async () => {
  await mountNotification(['routing', ID], { permissions: readPermissions });
  expect(screen.queryByRole('button', { name: 'Edit route' })).not.toBeInTheDocument();
});

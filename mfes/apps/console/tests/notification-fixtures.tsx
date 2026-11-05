import { act } from '@testing-library/react';
import { NotificationAdmin, type NotificationAdminProps } from '../app/components/NotificationAdmin';
import { renderWithProviders } from './helpers';
export const ID = '019a0000-0000-7000-8000-000000000001';
export const VARIANT = '019a0000-0000-7000-8000-000000000002';
export const VERSION = '019a0000-0000-7000-8000-000000000003';
export const OTHER = '019a0000-0000-7000-8000-000000000004';
export const WHEN = '2026-10-22T00:00:00Z';
export const page = (items: unknown[] = [], next: string | null = null) => ({ items, page: { has_more: !!next, next_cursor: next } });
export const provider = { id: ID, key: 'primary', display_name: 'Primary transport', channel: 'email', provider_key: 'ses', status: 'active', region: 'us-east-1', credential_ref: 'env:EMAIL', updated_at: WHEN };
export const template = { id: ID, key: 'staff-alert', event_key: 'platform.staff.alert', category: 'operational', default_locale: 'en', is_active: true, company_id: '00000000-0000-0000-0000-000000000000', updated_at: WHEN, description: 'Staff message', variable_schema: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'], additionalProperties: false } };
export const variant = { id: VARIANT, template_id: ID, channel: 'email', locale: 'en', is_active: true };
export const version = { id: VERSION, template_variant_id: VARIANT, version: 1, body_text: 'Hello {{name}}', subject_text: 'An alert', body_html: null, created_at: WHEN, channel_payload: null };
export const channels = [
  { channel: 'email', is_enabled: true, ready: true, reasons: [] },
  { channel: 'sms', is_enabled: false, ready: false, reasons: ['no_verified_sender'] },
];
export const useCases = [{ key: 'platform.staff.alert', owner: 'platform', source: 'identity', category: 'operational', triggers: ['identity.platform_notification.requested'], channels: ['email', 'sms', 'whatsapp'], required_variables: ['name'] }];
export const readPermissions = ['provider', 'template', 'route', 'recipient', 'request', 'delivery'].map(family => `platform.notification_${family}.read`);
export const allPermissions = [...readPermissions, ...['provider', 'template', 'route', 'consent', 'suppression'].map(family => `platform.notification_${family}.manage`), 'platform.notification_delivery.retry'];
export async function baseResponse(_owner: string, path: string, method = 'GET', _body?: unknown): Promise<unknown> {
  if (method !== 'GET') return { id: ID, status: 'pending' };
  if (path === 'channels') return channels;
  if (path === 'use-cases') return useCases;
  if (path === 'credential-bindings') return ['env:EMAIL'];
  if (path.startsWith('templates?')) return page([template]);
  if (path.includes('/variants?')) return page([variant]);
  if (path.startsWith('templates/')) return template;
  if (path.startsWith('variants/') && path.includes('/versions?')) return page([version]);
  if (path.startsWith('variants/') && path.includes('/activations?')) return page();
  if (path.startsWith('variants/')) return variant;
  if (path.startsWith('template-versions/') && path.includes('/bindings?')) return page();
  if (path.startsWith('template-versions/')) return version;
  if (path.startsWith('provider-accounts?')) return page([provider]);
  if (path.startsWith('provider-accounts/')) return provider;
  if (path.startsWith('jobs/')) return { id: ID, status: 'completed', reason_code: 'verified' };
  return page();
}
export async function mountNotification(route: string[], props: Partial<NotificationAdminProps> = {}) {
  let result!: Awaited<ReturnType<typeof renderWithProviders>>;
  await act(async () => { result = await renderWithProviders(<NotificationAdmin owner="platform" permissions={allPermissions} route={route} {...props} />); });
  return result;
}

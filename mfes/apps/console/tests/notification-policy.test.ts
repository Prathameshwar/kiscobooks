import { expect, it } from 'vitest';
import { allowedNotificationRequest as allow } from '../app/lib/notification-request-policy';
const id = '019a0000-0000-7000-8000-000000000001';
it('allows both management realms and declared command paths', () => {
  for (const prefix of ['/v1/', '/v1/platform/']) {
    expect(allow('notification', 'GET', prefix + 'deliveries?limit=50&cursor=opaque')).toBe(true);
    expect(allow('notification', 'GET', prefix + 'provider-events?status=unmatched&limit=50')).toBe(true);
    expect(allow('notification', 'POST', `${prefix}variants/${id}/activate`)).toBe(true);
    expect(allow('notification', 'POST', `${prefix}deliveries/${id}/retry`)).toBe(true);
  }
});
it.each(['/v1/callbacks/email/key', '/internal/send', '/v1/../health', '/v1/%2e%2e/health', '//evil.invalid/v1/templates', '/v1/templates?limit=1&limit=2', '/v1/templates?tenant_id=other', '/v1/templates#fragment'])('denies unsafe or undeclared target %s', path => {
  expect(allow('notification', 'GET', path)).toBe(false);
});
it('denies other services, undeclared methods and queries on commands', () => {
  expect(allow('identity', 'GET', '/v1/templates')).toBe(false);
  expect(allow('notification', 'DELETE', '/v1/templates')).toBe(false);
  expect(allow('notification', 'POST', `/v1/deliveries/${id}/retry?limit=1`)).toBe(false);
});
it('allows bounded policy reads and only the declared policy commands in both realms', () => {
  for (const prefix of ['/v1/', '/v1/platform/']) {
    for (const path of [`recipient-endpoints?subject_id=${id}&limit=50`, `recipient-endpoints/${id}`, `consent-states?recipient_endpoint_id=${id}`, 'suppressions?status=active&limit=50']) {
      expect(allow('notification', 'GET', prefix + path)).toBe(true);
    }
    for (const path of ['consent-events', 'suppressions', `suppressions/${id}/expire`]) {
      expect(allow('notification', 'POST', prefix + path)).toBe(true);
      expect(allow('notification', 'DELETE', prefix + path)).toBe(false);
    }
    expect(allow('notification', 'POST', prefix + 'recipient-endpoints')).toBe(false);
    expect(allow('notification', 'PATCH', `${prefix}recipient-endpoints/${id}`)).toBe(false);
    expect(allow('notification', 'GET', prefix + 'recipient-endpoints?destination=private')).toBe(false);
    expect(allow('notification', 'GET', prefix + 'consent-states?space_id=other')).toBe(false);
    expect(allow('notification', 'POST', prefix + 'consent-events?subject_id=' + id)).toBe(false);
  }
});

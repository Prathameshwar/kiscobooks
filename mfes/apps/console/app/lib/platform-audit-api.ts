import { createAuditClient } from '@janso/api-client';
import { AuditApiError, normalizeChanges } from './audit-api';
import type { AuditDetailLoader, AuditLoader } from './audit-events';
import { sessionFetch } from './session-fetch';

function client() {
  return createAuditClient({ baseUrl: '/api/audit', credentials: 'same-origin', cache: 'no-store', fetch: sessionFetch });
}

export function platformAuditLoader(entityId?: string): AuditLoader {
  return async (params, signal) => {
    const { data, response } = await client().GET('/v1/platform-events', {
      params: { query: { ...params, entity_id: entityId, cursor: params.cursor ?? undefined } }, signal,
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    return { ...data, page: { ...data.page, limit: params.limit ?? 50 } };
  };
}

export function platformAuditDetailLoader(): AuditDetailLoader {
  return async (event, signal) => {
    const { data, response } = await client().GET('/v1/platform-events/{event_id}', {
      params: { path: { event_id: event.id }, query: { occurred_at: event.occurred_at } }, signal,
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    const changes = Object.fromEntries(Object.entries(data.changes ?? {}).map(([key, value]) => [
      key, typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number'
        ? { from: null, to: String(value) } : value,
    ]));
    return { ...data, changes: normalizeChanges(changes), context: null };
  };
}

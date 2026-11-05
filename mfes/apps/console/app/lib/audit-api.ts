import { createAuditClient } from '@janso/api-client';
import { sessionFetch } from './session-fetch';
import type { AuditChange, AuditDetailLoader, AuditEventDetail, AuditListParams, AuditLoader } from './audit-events';

export class AuditApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 401 ? 'Your session has expired. Sign in again.' :
      status === 403 ? 'You do not have access to this audit scope.' :
      status === 422 ? 'The audit query or cursor is no longer valid. Refresh the list.' :
      'Audit is temporarily unavailable. Try again.');
  }
}

function client() {
  // The same-origin server adapter holds credentials; the browser never signs actor context.
  return createAuditClient({ baseUrl: '/api/audit', credentials: 'same-origin', cache: 'no-store', fetch: sessionFetch });
}

function text(value: unknown): string | null {
  if (value == null) return null;
  return typeof value === 'string' ? value : JSON.stringify(value);
}

export function normalizeChanges(input: Record<string, unknown> | null): Record<string, AuditChange> {
  // Historical Notification events used a field list and safe lifecycle values.
  // Expand that retained shape without manufacturing a before value.
  if (Array.isArray(input?.fields) && input.values && typeof input.values === 'object') {
    const values = input.values as Record<string, unknown>;
    input = Object.fromEntries(input.fields.filter((key): key is string => typeof key === 'string').map(key =>
      [key, Object.hasOwn(values, key) ? { to: values[key] } : { changed: true }]));
  }
  return Object.fromEntries(Object.entries(input ?? {}).map(([key, value]) => {
    const change = value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown> : { to: value };
    return [key, {
      from: text(change.from), to: text(change.to),
      ...(!('from' in change) && 'to' in change ? { from_recorded: false } : {}),
      ...('from' in change && !('to' in change) ? { to_recorded: false } : {}),
      ...(!('from' in change) && !('to' in change) ? { changed: true } : {}),
    }];
  }));
}

export function liveAuditLoader(companyId?: string, entityId?: string): AuditLoader {
  return async (params, signal) => {
    const { data, response } = await client().GET('/v1/audit-events', {
      params: { query: { ...params, cursor: params.cursor ?? undefined, company_id: companyId, entity_id: entityId } },
      signal,
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    return { ...data, page: { ...data.page, limit: params.limit ?? 50 } };
  };
}

async function actorName(id: string | null, signal: AbortSignal): Promise<string | null> {
  if (!id) return null;
  try {
    const response = await sessionFetch('/api/audit-actors/' + encodeURIComponent(id), {
      signal,
      credentials: 'same-origin', cache: 'no-store',
    });
    if (!response.ok) return null;
    const result = await response.json() as { name?: unknown };
    return typeof result.name === 'string' ? result.name : null;
  } catch {
    return null;
  }
}

export function liveAuditDetailLoader(): AuditDetailLoader {
  return async (event, signal) => {
    const { data, response } = await client().GET('/v1/audit-events/{event_id}', {
      params: { path: { event_id: event.id }, query: { occurred_at: event.occurred_at, company_id: event.company_id ?? undefined } }, signal,
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    const [actor_name, on_behalf_of_name] = await Promise.all([
      actorName(data.actor_user_id, signal), actorName(data.on_behalf_of_user_id, signal),
    ]);
    return {
      ...data, actor_name, on_behalf_of_name, changes: normalizeChanges(data.changes),
      context: Object.fromEntries(Object.entries(data.context ?? {}).map(([key, value]) => [key, text(value) ?? ''])),
    } satisfies AuditEventDetail;
  };
}

export type AuditExporter = (params: AuditListParams) => Promise<{ count: number; truncated: boolean }>;

export function liveAuditExporter(companyId?: string, entityId?: string): AuditExporter {
  return async (params) => {
    const { cursor: _cursor, sort: _sort, limit: _limit, ...filters } = params;
    const { data, response } = await client().POST('/v1/audit-events/export', {
      params: { query: { ...filters, company_id: companyId, entity_id: entityId } },
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    // Save the server's authorized export response, never the on-screen list page.
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'audit-' + data.export_id + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return { count: data.count, truncated: data.truncated };
  };
}

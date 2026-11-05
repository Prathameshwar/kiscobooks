import { createAuditClient } from '@janso/api-client';
import type { components } from '@janso/api-client/audit';
import { AuditApiError } from './audit-api';
import { sessionFetch } from './session-fetch';

export type ActivityItem = components['schemas']['ActivityItem'];
export type ActivityPage = components['schemas']['ActivityPage'];
export type ActivityLoader = (cursor: string | null, signal: AbortSignal) => Promise<ActivityPage>;

export function activityLoader(company: string | null): ActivityLoader {
  return async (cursor, signal) => {
    const client = createAuditClient({ baseUrl: '/api/audit', credentials: 'same-origin', cache: 'no-store', fetch: sessionFetch });
    const { response, data } = await client.GET('/v1/activity', {
      params: { query: { company_id: company ?? undefined, limit: 50, sort: '-occurred_at', cursor: cursor ?? undefined } }, signal,
    });
    if (!response.ok || !data) throw new AuditApiError(response.status);
    return data;
  };
}

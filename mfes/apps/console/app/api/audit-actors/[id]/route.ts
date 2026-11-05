import type { components } from '@janso/api-client/identity';
import { identityFetch } from '../../../identity-session';

export const dynamic = 'force-dynamic';

/** Identity enforces user.read and tenant scope; names never enter durable Audit evidence. */
export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const reply = (name: string | null, status = 200) => Response.json({ name }, {
    status, headers: { 'Cache-Control': 'no-store' },
  });
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return reply(null, 422);
  try {
    const response = await identityFetch('/v1/users/' + id);
    if (!response.ok) return reply(null);
    const user = await response.json() as components['schemas']['UserDetail'];
    return reply(user.id === id && !user.anonymized_at && user.status === 'active' &&
      typeof user.display_name === 'string' ? user.display_name : null);
  } catch {
    // This optional lookup must not hide the event on permission, session or network failures.
    return reply(null);
  }
}

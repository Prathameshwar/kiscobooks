import { NextRequest } from 'next/server';
import { isSameOrigin } from '../../../lib/request-origin';
import { auditFetch } from '../../../identity-session';

const ALLOWED = new Set(['company_id', 'entity_id', 'entity_type', 'action', 'category', 'occurred_from', 'occurred_to', 'occurred_at', 'limit', 'cursor', 'sort']);

async function proxy(request: NextRequest, context: { params: Promise<{ segments: string[] }> }): Promise<Response> {
  const { segments } = await context.params;
  const path = '/' + segments.join('/');
  if (!/^\/v1\/(audit-events(?:\/(?:security|export|[0-9a-f-]{36}))?|platform-events(?:\/[0-9a-f-]{36})?|activity)$/.test(path)) {
    return Response.json({ error: { code: 'not_found', message: 'Audit endpoint not found' } }, { status: 404 });
  }
  const exporting = path === '/v1/audit-events/export';
  if (request.method !== (exporting ? 'POST' : 'GET')) return new Response(null, { status: 405 });
  if (exporting && !isSameOrigin(request)) {
    return Response.json({ error: { code: 'permission_denied', message: 'Export requires the current site' } }, { status: 403 });
  }
  const query = request.nextUrl.searchParams;
  const keys = [...query.keys()];
  if (keys.length !== new Set(keys).size || keys.some(key => !ALLOWED.has(key))) {
    return Response.json({ error: { code: 'validation_failed', message: 'Invalid audit query' } }, { status: 422 });
  }
  try {
    const response = await auditFetch(path + (query.size ? '?' + query.toString() : ''), request.method);
    return new Response(await response.text(), {
      status: response.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  } catch {
    return Response.json({ error: { code: 'dependency_unavailable', message: 'Audit is unavailable' } },
      { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
}

export const GET = proxy;
export const POST = proxy;

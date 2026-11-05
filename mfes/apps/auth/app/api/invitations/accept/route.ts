import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { validToken } from '../../../lib/refresh-coordinator';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export async function POST(request: NextRequest) {
  const authUrl = process.env.NEXTAUTH_URL;
  const identityUrl = process.env.IDENTITY_URL;
  const secret = process.env.NEXTAUTH_SECRET;
  if (!authUrl || !identityUrl || !secret) return NextResponse.json({ error: 'Service unavailable' }, { status: 503 });
  let authOrigin: string;
  try { authOrigin = new URL(authUrl).origin; new URL(identityUrl); }
  catch { return NextResponse.json({ error: 'Service unavailable' }, { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  if (request.headers.get('origin') !== authOrigin) return new NextResponse(null, { status: 403 });
  const token = await getToken({ req: request, secret, secureCookie: authUrl.startsWith('https://') });
  if (!token || !validToken(token.accessToken)) return new NextResponse(null, { status: 401 });
  const body = await request.json().catch(() => null);
  if (!body || typeof body.tenant !== 'string' || typeof body.invitation !== 'string' ||
      !uuid.test(body.tenant) || !uuid.test(body.invitation)) return new NextResponse(null, { status: 422 });
  try {
    const response = await fetch(new URL(`/v1/tenants/${body.tenant}/invitations/${body.invitation}/accept`, identityUrl), {
      method: 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
      headers: { Authorization: `Bearer ${token.accessToken}` },
    });
    return NextResponse.json({ accepted: response.ok },
      { status: response.status === 204 ? 200 : response.status, headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
}

import { getToken } from 'next-auth/jwt';
import { NextRequest, NextResponse } from 'next/server';
import { validToken } from '../../lib/refresh-coordinator';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export async function POST(request: NextRequest) {
  const authUrl = process.env.NEXTAUTH_URL, identityUrl = process.env.IDENTITY_URL, secret = process.env.NEXTAUTH_SECRET;
  if (!authUrl || !identityUrl || !secret) return new NextResponse(null, { status: 503 });
  let authOrigin: string;
  try { authOrigin = new URL(authUrl).origin; new URL(identityUrl); }
  catch { return new NextResponse(null, { status: 503 }); }
  if (request.headers.get('origin') !== authOrigin) return new NextResponse(null, { status: 403 });
  const body = await request.json().catch(() => null);
  if (!body || typeof body.company !== 'string' || !uuid.test(body.company) ||
      !['challenge', 'complete'].includes(body.action)) return new NextResponse(null, { status: 422 });
  const token = await getToken({ req: request, secret, secureCookie: authUrl.startsWith('https://') });
  if (!token || !validToken(token.accessToken)) return new NextResponse(null, { status: 401 });
  try {
    const response = await fetch(new URL(`/v1/companies/${body.company}/step-up/${body.action}`, identityUrl), {
      method: 'POST', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
      headers: { Authorization: `Bearer ${token.accessToken}`, 'Content-Type': 'application/json' },
      ...(body.action === 'complete' ? { body: JSON.stringify({ challenge_id: body.challenge }) } : {}),
    });
    if (!response.ok) return new NextResponse(null, { status: response.status });
    const value = await response.json();
    if (body.action === 'challenge') return NextResponse.json({ challenge: value.challenge_id }, { headers: { 'Cache-Control': 'no-store' } });
    if (typeof value.proof !== 'string' || value.proof.length < 20 || value.proof.length > 128 ||
        !/^[a-zA-Z0-9_-]+$/.test(value.proof)) return new NextResponse(null, { status: 502 });
    const result = NextResponse.json({ completed: true }, { headers: { 'Cache-Control': 'no-store' } });
    result.cookies.set(`janso-step-up-${body.company.toLowerCase()}`, value.proof, {
      httpOnly: true, secure: authUrl.startsWith('https://'), sameSite: 'lax', path: '/', maxAge: 300,
      ...(process.env.AUTH_COOKIE_DOMAIN ? { domain: process.env.AUTH_COOKIE_DOMAIN } : {}),
    });
    // Selection is a hint: Identity still authorizes this company and verifies its own proof.
    result.cookies.set('janso-company', body.company.toLowerCase(), {
      httpOnly: true, secure: authUrl.startsWith('https://'), sameSite: 'lax', path: '/', maxAge: 8 * 60 * 60,
      ...(process.env.AUTH_COOKIE_DOMAIN ? { domain: process.env.AUTH_COOKIE_DOMAIN } : {}),
    });
    return result;
  } catch { return new NextResponse(null, { status: 503 }); }
}

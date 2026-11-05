import { NextRequest, NextResponse } from 'next/server';
import { safeReturnUrl } from '../lib/auth-options';
import { refreshSession } from '../lib/session-response';

export async function GET(request: NextRequest) {
  const response = await refreshSession(request);
  const returnTo = request.nextUrl.searchParams.get('returnTo');
  let destination: string;
  try { destination = safeReturnUrl(returnTo); }
  catch { return NextResponse.json({ error: 'Authentication unavailable' },
    { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const login = new URL('/login', request.url);
  login.searchParams.set('error', response.status === 503 ? 'SessionUnavailable' : 'SessionExpired');
  if (returnTo) login.searchParams.set('returnTo', destination);
  const target = response.ok ? destination : login.href;
  const redirect = NextResponse.redirect(target);
  for (const cookie of response.headers.getSetCookie()) redirect.headers.append('Set-Cookie', cookie);
  redirect.headers.set('Cache-Control', 'no-store');
  return redirect;
}

import NextAuth from 'next-auth';
import { NextRequest } from 'next/server';
import { authOptions } from './auth-options';

export async function refreshSession(request: NextRequest): Promise<Response> {
  let options;
  try { options = authOptions(); }
  catch { return Response.json({ authenticated: false }, { status: 503 }); }
  const sessionRequest = new NextRequest(request.url, { method: 'GET', headers: request.headers });
  const response: Response = await NextAuth(sessionRequest, { params: { nextauth: ['session'] } }, options);
  const session = await response.json().catch(() => ({}));
  const valid = response.ok && typeof session.expires === 'string' &&
    Number.isFinite(Date.parse(session.expires)) && Date.parse(session.expires) > Date.now();
  const output = Response.json({ authenticated: valid },
    { status: valid ? 200 : session.authError === 'unavailable' || response.status >= 500 ? 503 : 401,
      headers: { 'Cache-Control': 'no-store' } });
  for (const cookie of response.headers.getSetCookie()) output.headers.append('Set-Cookie', cookie);
  return output;
}

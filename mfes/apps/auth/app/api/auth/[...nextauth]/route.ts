import NextAuth from 'next-auth';
import { NextRequest, NextResponse } from 'next/server';
import { authOptions } from '../../../lib/auth-options';

type Context = { params: Promise<{ nextauth: string[] }> };
async function handler(request: NextRequest, context: Context) {
  let options;
  try { options = authOptions(); }
  catch { return NextResponse.json({ error: 'Authentication unavailable' },
    { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const response: Response = await NextAuth(request, context, options);
  const { nextauth } = await context.params;
  // Clear company cookies only after NextAuth confirms deletion of the session cookie.
  if (request.method === 'POST' && nextauth[0] === 'signout' &&
      response.headers.getSetCookie().some((value) => /next-auth\.session-token(?:\.\d+)?=;/.test(value))) {
    for (const cookie of request.cookies.getAll()) {
      if (cookie.name !== 'janso-company' && !/^janso-step-up-[0-9a-f-]{36}$/i.test(cookie.name)) continue;
      const cleared = new NextResponse();
      cleared.cookies.set(cookie.name, '', { httpOnly: true, secure: process.env.NEXTAUTH_URL?.startsWith('https://'),
        sameSite: 'lax', path: '/', maxAge: 0,
        ...(process.env.AUTH_COOKIE_DOMAIN ? { domain: process.env.AUTH_COOKIE_DOMAIN } : {}) });
      for (const value of cleared.headers.getSetCookie()) response.headers.append('Set-Cookie', value);
    }
  }
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
export { handler as GET, handler as POST };

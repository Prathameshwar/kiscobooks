import { NextRequest, NextResponse } from 'next/server';

// Replaces any caller-supplied hint with the actual page URL; it grants no authorization.
export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === '/session-recovery') {
    return NextResponse.next({
      status: request.nextUrl.searchParams.get('reason') === 'access' ? 403 : 503,
      headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' },
    });
  }
  const headers = new Headers(request.headers);
  headers.set('x-janso-return-path', request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.next({ request: { headers } });
}
export const config = { matcher: ['/((?!api/|_next/|favicon.svg).*)'] };

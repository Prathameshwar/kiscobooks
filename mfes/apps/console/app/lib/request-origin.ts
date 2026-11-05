import type { NextRequest } from 'next/server';

/** Bind browser writes to the incoming HTTP authority; Next normalizes loopback URL hosts. */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get('origin');
  const host = request.headers.get('host') ?? request.nextUrl.host;
  return origin !== null && origin === request.nextUrl.protocol + '//' + host;
}
